import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import IngestionRunStatus, ProvenanceType, VerificationStatus
from app.domain.models import DataIngestionRun, DataSource, WeatherForecast, WeatherObservation
from app.infrastructure.object_storage import put_text_object
from app.ingestion.base import BaseConnector, ConnectorMetrics, ConnectorRunResult, ValidationError
from app.ingestion.config import AemetConnectorConfig
from app.ingestion.spatial import point_wkt


@dataclass(frozen=True)
class AemetRawPayload:
    observations: str
    forecasts: dict[str, str]


@dataclass(frozen=True)
class AemetWeatherRecord:
    kind: str
    external_id: str
    observed_at: datetime | None
    forecast_for: datetime | None
    latitude: float
    longitude: float
    station_id: str | None
    municipality_id: str | None
    wind_speed_kph: float | None
    wind_direction_degrees: float | None
    wind_gust_kph: float | None
    temperature_celsius: float | None
    humidity_percent: float | None
    precipitation_mm: float | None
    horizon_hours: int | None
    raw: dict[str, Any]
    deduplication_hash: str


class AemetConnector(BaseConnector[AemetRawPayload, AemetWeatherRecord]):
    name = "aemet_opendata"

    def __init__(
        self,
        session: AsyncSession,
        config: AemetConnectorConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.session = session
        self.config = config or AemetConnectorConfig.from_settings(get_settings())
        self.http_client = http_client

    async def fetch(self) -> AemetRawPayload:
        if not self.config.api_key:
            raise ValidationError("AEMET_API_KEY is required to execute AEMET connector")
        observations = await self._fetch_dataset("/api/observacion/convencional/todas")
        forecasts: dict[str, str] = {}
        for municipality in self.config.forecast_municipalities:
            forecasts[municipality] = await self._fetch_dataset(
                f"/api/prediccion/especifica/municipio/horaria/{municipality}"
            )
        return AemetRawPayload(observations=observations, forecasts=forecasts)

    def validate(self, raw: AemetRawPayload) -> None:
        observations = json.loads(raw.observations)
        if not isinstance(observations, list):
            raise ValidationError("AEMET observations response must be a JSON array")
        for municipality, payload in raw.forecasts.items():
            forecast = json.loads(payload)
            if not isinstance(forecast, list):
                raise ValidationError(f"AEMET forecast for {municipality} must be a JSON array")

    def normalize(self, raw: AemetRawPayload) -> list[AemetWeatherRecord]:
        records: list[AemetWeatherRecord] = []
        for row in json.loads(raw.observations):
            if not isinstance(row, dict):
                continue
            latitude = self._coordinate(row.get("lat"))
            longitude = self._coordinate(row.get("lon"))
            observed_at = self._datetime(row.get("fint"))
            if latitude is None or longitude is None or observed_at is None:
                continue
            external_id = f"obs:{row.get('idema', '')}:{observed_at.isoformat()}"
            records.append(
                AemetWeatherRecord(
                    kind="observation",
                    external_id=external_id,
                    observed_at=observed_at,
                    forecast_for=None,
                    latitude=latitude,
                    longitude=longitude,
                    station_id=self._str(row.get("idema")),
                    municipality_id=None,
                    wind_speed_kph=self._float(row.get("vv")),
                    wind_direction_degrees=self._float(row.get("dv")),
                    wind_gust_kph=self._float(row.get("vmax")),
                    temperature_celsius=self._float(row.get("ta")),
                    humidity_percent=self._float(row.get("hr")),
                    precipitation_mm=self._float(row.get("prec")),
                    horizon_hours=None,
                    raw=row,
                    deduplication_hash=self._hash(external_id, row),
                )
            )
        for municipality, payload in raw.forecasts.items():
            records.extend(self._normalize_forecast(municipality, json.loads(payload)))
        return records

    def deduplicate(self, records: list[AemetWeatherRecord]) -> tuple[list[AemetWeatherRecord], int]:
        seen: set[str] = set()
        unique: list[AemetWeatherRecord] = []
        duplicates = 0
        for record in records:
            if record.deduplication_hash in seen:
                duplicates += 1
                continue
            seen.add(record.deduplication_hash)
            unique.append(record)
        return unique, duplicates

    async def persist(self, records: list[AemetWeatherRecord], raw: AemetRawPayload) -> ConnectorMetrics:
        started_at = datetime.now(UTC)
        source = await self._get_or_create_source()
        raw_uri = await asyncio.to_thread(
            put_text_object,
            f"aemet/{started_at:%Y/%m/%d/%H%M%S}.json",
            json.dumps({"observations": raw.observations, "forecasts": raw.forecasts}, ensure_ascii=False),
            "application/json",
        )
        run = DataIngestionRun(
            source_id=source.id,
            connector_name=self.name,
            status=IngestionRunStatus.STARTED,
            started_at=started_at,
            raw_object_uri=raw_uri,
        )
        self.session.add(run)
        await self.session.flush()

        existing = await self._existing_hashes([record.deduplication_hash for record in records])
        persisted = 0
        duplicates = 0
        for record in records:
            if record.deduplication_hash in existing:
                duplicates += 1
                continue
            geometry = WKTElement(point_wkt(record.longitude, record.latitude), srid=4326)
            if record.kind == "observation":
                self.session.add(
                    WeatherObservation(
                        source_id=source.id,
                        external_id=record.external_id,
                        provenance=ProvenanceType.OBSERVED,
                        observed_at=record.observed_at,
                        received_at=started_at,
                        verification_status=VerificationStatus.PENDING,
                        original_metadata=record.raw,
                        deduplication_hash=record.deduplication_hash,
                        geometry=geometry,
                        original_crs="EPSG:4326",
                        station_id=record.station_id,
                        wind_speed_kph=record.wind_speed_kph,
                        wind_direction_degrees=record.wind_direction_degrees,
                        wind_gust_kph=record.wind_gust_kph,
                        temperature_celsius=record.temperature_celsius,
                        humidity_percent=record.humidity_percent,
                        precipitation_mm=record.precipitation_mm,
                    )
                )
            else:
                self.session.add(
                    WeatherForecast(
                        source_id=source.id,
                        external_id=record.external_id,
                        provenance=ProvenanceType.OFFICIAL,
                        observed_at=record.observed_at,
                        published_at=record.observed_at,
                        received_at=started_at,
                        verification_status=VerificationStatus.PENDING,
                        original_metadata=record.raw,
                        deduplication_hash=record.deduplication_hash,
                        geometry=geometry,
                        original_crs="EPSG:4326",
                        forecast_for=record.forecast_for or started_at,
                        horizon_hours=record.horizon_hours or 0,
                        resolution="municipality-hourly",
                        wind_speed_kph=record.wind_speed_kph,
                        wind_direction_degrees=record.wind_direction_degrees,
                        wind_gust_kph=record.wind_gust_kph,
                        temperature_celsius=record.temperature_celsius,
                        humidity_percent=record.humidity_percent,
                        precipitation_mm=record.precipitation_mm,
                    )
                )
            persisted += 1

        run.status = IngestionRunStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.received_count = len(records)
        run.duplicate_count = duplicates
        run.persisted_count = persisted
        run.metrics = {"forecast_municipalities": self.config.forecast_municipalities}
        await self.session.commit()
        return ConnectorMetrics(received=len(records), duplicated=duplicates, persisted=persisted, raw_object_uri=raw_uri)

    async def report_metrics(self, metrics: ConnectorMetrics) -> None:
        return None

    async def execute(self) -> ConnectorRunResult:
        started_at = datetime.now(UTC)
        raw: AemetRawPayload | None = None
        try:
            raw = await self.fetch()
            self.validate(raw)
            normalized = self.normalize(raw)
            unique, payload_duplicates = self.deduplicate(normalized)
            metrics = await self.persist(unique, raw)
            metrics.duplicated += payload_duplicates
            await self.report_metrics(metrics)
            return ConnectorRunResult(self.name, "completed", started_at, datetime.now(UTC), metrics)
        except Exception as exc:
            metrics = await self.record_failure(started_at, exc, raw)
            await self.report_metrics(metrics)
            return ConnectorRunResult(self.name, "failed", started_at, datetime.now(UTC), metrics)

    async def record_failure(
        self,
        started_at: datetime,
        error: Exception,
        raw: AemetRawPayload | None = None,
    ) -> ConnectorMetrics:
        raw_uri = None
        if raw is not None:
            raw_uri = await asyncio.to_thread(
                put_text_object,
                f"aemet/dead-letter/{started_at:%Y/%m/%d/%H%M%S}.json",
                json.dumps({"observations": raw.observations, "forecasts": raw.forecasts}, ensure_ascii=False),
                "application/json",
            )
        source = await self._get_or_create_source()
        self.session.add(
            DataIngestionRun(
                source_id=source.id,
                connector_name=self.name,
                status=IngestionRunStatus.FAILED,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                raw_object_uri=raw_uri,
                error_summary={"error": str(error), "type": error.__class__.__name__},
            )
        )
        await self.session.commit()
        return ConnectorMetrics(errors=[str(error)], raw_object_uri=raw_uri)

    async def _fetch_dataset(self, path: str) -> str:
        metadata = await self._get_json(path)
        data_url = metadata.get("datos")
        if not isinstance(data_url, str):
            raise ValidationError(f"AEMET response for {path} missing datos URL")
        response = await self._request("GET", data_url, params=None)
        response.raise_for_status()
        return response.text

    async def _get_json(self, path: str) -> dict[str, Any]:
        response = await self._request("GET", f"{self.config.base_url}{path}", params={"api_key": self.config.api_key})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValidationError(f"AEMET metadata response for {path} must be an object")
        return payload

    async def _request(self, method: str, url: str, params: dict[str, str] | None) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                if self.http_client is not None:
                    return await self.http_client.request(method, url, params=params, timeout=self.config.timeout_seconds)
                async with httpx.AsyncClient() as client:
                    return await client.request(method, url, params=params, timeout=self.config.timeout_seconds)
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
        raise ValidationError(f"AEMET fetch failed: {last_error}")

    async def _get_or_create_source(self) -> DataSource:
        result = await self.session.execute(select(DataSource).where(DataSource.name == "AEMET OpenData"))
        source = result.scalar_one_or_none()
        if source is not None:
            return source
        source = DataSource(
            name="AEMET OpenData",
            source_type=ProvenanceType.OFFICIAL,
            authority="Agencia Estatal de Meteorologia",
            base_url=self.config.base_url,
            license_name="AEMET reutilizacion",
            attribution="AEMET",
            update_frequency="hourly/daily depending product",
            reliability_score=0.9,
            source_metadata={"products": ["observacion.convencional.todas", "prediccion.municipio.horaria"]},
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def _existing_hashes(self, hashes: list[str]) -> set[str]:
        if not hashes:
            return set()
        obs = await self.session.execute(
            select(WeatherObservation.deduplication_hash).where(WeatherObservation.deduplication_hash.in_(hashes))
        )
        forecasts = await self.session.execute(
            select(WeatherForecast.deduplication_hash).where(WeatherForecast.deduplication_hash.in_(hashes))
        )
        return {item for item in obs.scalars() if item is not None} | {item for item in forecasts.scalars() if item is not None}

    def _normalize_forecast(self, municipality: str, payload: list[Any]) -> list[AemetWeatherRecord]:
        location = self.config.forecast_locations.get(municipality, {})
        latitude = self._float(location.get("latitude"))
        longitude = self._float(location.get("longitude"))
        if latitude is None or longitude is None:
            return []
        records: list[AemetWeatherRecord] = []
        root = payload[0] if payload and isinstance(payload[0], dict) else {}
        issued_at = self._datetime(root.get("elaborado"))
        days = root.get("prediccion", {}).get("dia", []) if isinstance(root.get("prediccion"), dict) else []
        for day in days if isinstance(days, list) else []:
            if not isinstance(day, dict):
                continue
            date_value = self._datetime(day.get("fecha"))
            temperatures = day.get("temperatura", [])
            precipitation = day.get("precipitacion", [])
            humidity = day.get("humedadRelativa", [])
            winds = day.get("vientoAndRachaMax", [])
            for period in self._periods(temperatures, precipitation, humidity, winds):
                forecast_for = self._forecast_datetime(date_value, period.get("periodo"))
                if forecast_for is None:
                    continue
                external_id = f"forecast:{municipality}:{forecast_for.isoformat()}"
                records.append(
                    AemetWeatherRecord(
                        kind="forecast",
                        external_id=external_id,
                        observed_at=issued_at,
                        forecast_for=forecast_for,
                        latitude=latitude,
                        longitude=longitude,
                        station_id=None,
                        municipality_id=municipality,
                        wind_speed_kph=self._float(period.get("velocidad")),
                        wind_direction_degrees=self._wind_direction(period.get("direccion")),
                        wind_gust_kph=self._float(period.get("rachaMax")),
                        temperature_celsius=self._float(period.get("temperatura")),
                        humidity_percent=self._float(period.get("humedadRelativa")),
                        precipitation_mm=self._float(period.get("precipitacion")),
                        horizon_hours=self._horizon_hours(issued_at, forecast_for),
                        raw={"municipality": municipality, "period": period, "source": root},
                        deduplication_hash=self._hash(external_id, period),
                    )
                )
        return records

    def _periods(self, *collections: Any) -> list[dict[str, Any]]:
        by_period: dict[str, dict[str, Any]] = {}
        names = ["temperatura", "precipitacion", "humedadRelativa", "viento"]
        for name, collection in zip(names, collections, strict=True):
            if not isinstance(collection, list):
                continue
            for item in collection:
                if not isinstance(item, dict):
                    continue
                period = str(item.get("periodo", ""))
                by_period.setdefault(period, {"periodo": period})
                if name == "viento":
                    by_period[period].update(item)
                else:
                    by_period[period][name] = item.get("value")
        return list(by_period.values())

    def _forecast_datetime(self, date_value: datetime | None, period: Any) -> datetime | None:
        if date_value is None:
            return None
        try:
            hour = int(str(period)[:2])
        except ValueError:
            hour = 0
        return date_value.replace(hour=hour, minute=0, second=0, microsecond=0)

    def _horizon_hours(self, issued_at: datetime | None, forecast_for: datetime) -> int:
        if issued_at is None:
            return 0
        delta: timedelta = forecast_for - issued_at
        return max(0, int(delta.total_seconds() // 3600))

    def _coordinate(self, value: Any) -> float | None:
        text = self._str(value)
        if text is None:
            return None
        try:
            return float(text)
        except ValueError:
            pass
        if len(text) < 2:
            return None
        hemisphere = text[-1].upper()
        digits = text[:-1]
        if hemisphere in {"N", "S"} and len(digits) >= 4:
            degrees = int(digits[:2])
            minutes = int(digits[2:4])
            seconds = int(digits[4:] or 0)
        elif hemisphere in {"E", "W"} and len(digits) >= 5:
            degrees = int(digits[:3])
            minutes = int(digits[3:5])
            seconds = int(digits[5:] or 0)
        else:
            return None
        decimal = degrees + minutes / 60 + seconds / 3600
        return -decimal if hemisphere in {"S", "W"} else decimal

    def _datetime(self, value: Any) -> datetime | None:
        text = self._str(value)
        if text is None:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None

    def _float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace(",", "."))
        except ValueError:
            return None

    def _str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _wind_direction(self, value: Any) -> float | None:
        text = self._str(value)
        if text is None:
            return None
        mapping = {"N": 0.0, "NE": 45.0, "E": 90.0, "SE": 135.0, "S": 180.0, "SW": 225.0, "W": 270.0, "NW": 315.0}
        return mapping.get(text.upper(), self._float(text))

    def _hash(self, external_id: str, payload: dict[str, Any]) -> str:
        stable = f"{external_id}|{json.dumps(payload, sort_keys=True, default=str)}"
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()
