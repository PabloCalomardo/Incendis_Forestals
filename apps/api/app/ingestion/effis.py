import asyncio
import hashlib
import io
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import PurePosixPath
from typing import Any, cast

import httpx
import shapefile
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import IncidentStatus, IngestionRunStatus, ProvenanceType, VerificationStatus
from app.domain.models import DataIngestionRun, DataSource, FirePerimeter, Incident
from app.infrastructure.object_storage import put_binary_object
from app.ingestion.base import BaseConnector, ConnectorMetrics, ConnectorRunResult, ValidationError
from app.ingestion.config import EffisConnectorConfig
from app.ingestion.incident_reconciliation import reconcile_recent_fires
from app.ingestion.spatial import geojson_geometry_to_polygon_wkt, geometry_hash_payload


@dataclass(frozen=True)
class EffisBurntArea:
    external_id: str
    geometry_wkt: str
    area_hectares: float | None
    fire_date: datetime | None
    final_date: datetime | None
    last_update: datetime | None
    country: str | None
    province: str | None
    commune: str | None
    metadata: dict[str, object]
    deduplication_hash: str

    @property
    def observed_at(self) -> datetime | None:
        return self.fire_date or self.final_date or self.last_update


class EffisBurntAreasConnector(BaseConnector[bytes, EffisBurntArea]):
    name = "effis_burnt_areas"

    def __init__(
        self,
        session: AsyncSession,
        config: EffisConnectorConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.session = session
        self.config = config or EffisConnectorConfig.from_settings(get_settings())
        self.http_client = http_client

    async def fetch(self) -> bytes:
        params = {
            "service": "WFS",
            "version": "1.1.0",
            "request": "GetFeature",
            "typeName": self.config.type_name,
            "outputFormat": "SHAPEZIP",
        }
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                if self.http_client is not None:
                    response = await self.http_client.get(
                        self.config.wfs_url,
                        params=params,
                        timeout=self.config.timeout_seconds,
                    )
                else:
                    async with httpx.AsyncClient() as client:
                        response = await client.get(
                            self.config.wfs_url,
                            params=params,
                            timeout=self.config.timeout_seconds,
                        )
                response.raise_for_status()
                return response.content
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
                if attempt < self.config.max_retries:
                    await asyncio.sleep(min(2 ** (attempt - 1), 8))
        raise ValidationError(f"EFFIS SHAPEZIP fetch failed: {last_error}")

    def validate(self, raw: bytes) -> None:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                extensions = {PurePosixPath(name).suffix.lower() for name in archive.namelist()}
        except (zipfile.BadZipFile, OSError) as exc:
            raise ValidationError("EFFIS response is not a valid SHAPEZIP") from exc
        missing = {".shp", ".shx", ".dbf"} - extensions
        if missing:
            raise ValidationError(f"EFFIS SHAPEZIP is missing required files: {sorted(missing)}")

    def normalize(self, raw: bytes) -> list[EffisBurntArea]:
        west, south, east, north = self._bbox()
        records: list[EffisBurntArea] = []
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = self._shapefile_members(archive)
            encoding = "utf-8"
            if ".cpg" in members:
                encoding = archive.read(members[".cpg"]).decode("ascii", errors="ignore").strip() or encoding
            reader = shapefile.Reader(
                shp=io.BytesIO(archive.read(members[".shp"])),
                shx=io.BytesIO(archive.read(members[".shx"])),
                dbf=io.BytesIO(archive.read(members[".dbf"])),
                encoding=encoding,
                encodingErrors="replace",
            )
            for shape_record in reader.iterShapeRecords():
                shape_bbox = shape_record.shape.bbox
                if len(shape_bbox) < 4 or not self._bbox_intersects(shape_bbox, (west, south, east, north)):
                    continue
                geometry = dict(shape_record.shape.__geo_interface__)
                geometry_wkt = geojson_geometry_to_polygon_wkt(geometry)
                if geometry_wkt is None:
                    continue
                attributes = {str(key): self._json_value(value) for key, value in shape_record.record.as_dict().items()}
                fields = {key.upper(): value for key, value in attributes.items()}
                country = self._text(fields.get("COUNTRY"))
                if country and country.casefold() not in {"spain", "espana", "españa", "es"}:
                    continue
                raw_id = fields.get("ID")
                if raw_id in (None, ""):
                    continue
                fire_date = self._date(fields.get("FIREDATE"))
                final_date = self._date(fields.get("FINALDATE"))
                last_update = self._date(fields.get("LASTUPDATE"))
                external_id = f"effis:{raw_id}"
                stable = "|".join([external_id, last_update.isoformat() if last_update else "", geometry_hash_payload(geometry)])
                metadata: dict[str, object] = {
                    **{key.lower(): value for key, value in attributes.items()},
                    "shapefile_attributes": attributes,
                    "operational_extinction_status_available": False,
                    "operational_extinction_status_note": "EFFIS no publica les tasques operatives d'extincio.",
                }
                records.append(
                    EffisBurntArea(
                        external_id=external_id,
                        geometry_wkt=geometry_wkt,
                        area_hectares=self._float(fields.get("AREA_HA")),
                        fire_date=fire_date,
                        final_date=final_date,
                        last_update=last_update,
                        country=country,
                        province=self._text(fields.get("PROVINCE")),
                        commune=self._text(fields.get("COMMUNE")),
                        metadata=metadata,
                        deduplication_hash=hashlib.sha256(stable.encode("utf-8")).hexdigest(),
                    )
                )
        return records

    def deduplicate(self, records: list[EffisBurntArea]) -> tuple[list[EffisBurntArea], int]:
        latest: dict[str, EffisBurntArea] = {}
        duplicates = 0
        for record in records:
            current = latest.get(record.external_id)
            if current is None:
                latest[record.external_id] = record
                continue
            duplicates += 1
            if (record.last_update or datetime.min.replace(tzinfo=UTC)) > (current.last_update or datetime.min.replace(tzinfo=UTC)):
                latest[record.external_id] = record
        return list(latest.values()), duplicates

    async def persist(
        self,
        records: list[EffisBurntArea],
        raw: bytes,
        started_at: datetime | None = None,
    ) -> ConnectorMetrics:
        now = started_at or datetime.now(UTC)
        source = await self._get_or_create_source()
        raw_uri = await asyncio.to_thread(
            put_binary_object,
            f"effis/{now:%Y/%m/%d/%H%M%S}.zip",
            raw,
            "application/zip",
        )
        run = DataIngestionRun(
            source_id=source.id,
            connector_name=self.name,
            status=IngestionRunStatus.STARTED,
            started_at=now,
            raw_object_uri=raw_uri,
        )
        self.session.add(run)
        await self.session.flush()

        incident_external_ids = [f"{record.external_id}:incident" for record in records]
        incident_result = await self.session.execute(
            select(Incident).where(
                Incident.source_id == source.id,
                Incident.external_id.in_(incident_external_ids),
            )
        )
        incidents = {incident.external_id: incident for incident in incident_result.scalars() if incident.external_id is not None}
        for record in records:
            external_id = f"{record.external_id}:incident"
            incident = self._update_incident(incidents.get(external_id), source, record, now)
            if external_id not in incidents:
                incidents[external_id] = incident
                self.session.add(incident)
        await self.session.flush()

        perimeter_external_ids = [record.external_id for record in records]
        perimeter_result = await self.session.execute(
            select(FirePerimeter).where(
                FirePerimeter.source_id == source.id,
                FirePerimeter.external_id.in_(perimeter_external_ids),
            )
        )
        perimeters = {perimeter.external_id: perimeter for perimeter in perimeter_result.scalars() if perimeter.external_id is not None}
        persisted = 0
        duplicates = 0
        for record in records:
            incident = incidents[f"{record.external_id}:incident"]
            perimeter = perimeters.get(record.external_id)
            if perimeter is not None and perimeter.deduplication_hash == record.deduplication_hash:
                duplicates += 1
                continue
            if perimeter is None:
                perimeter = FirePerimeter(
                    source_id=source.id,
                    external_id=record.external_id,
                    provenance=ProvenanceType.OFFICIAL,
                    verification_status=VerificationStatus.PARTIAL,
                    original_crs="EPSG:4326",
                    perimeter_kind="effis_official_burnt_area",
                )
                self.session.add(perimeter)
            else:
                perimeter.version += 1
            perimeter.provenance = ProvenanceType.OFFICIAL
            perimeter.verification_status = VerificationStatus.PARTIAL
            perimeter.perimeter_kind = "effis_official_burnt_area"
            perimeter.incident_id = incident.id
            perimeter.observed_at = record.observed_at
            perimeter.published_at = record.last_update
            perimeter.received_at = now
            perimeter.confidence = 0.85
            perimeter.original_metadata = record.metadata
            perimeter.deduplication_hash = record.deduplication_hash
            perimeter.geometry = cast(Any, WKTElement(record.geometry_wkt, srid=4326))
            perimeter.area_hectares = record.area_hectares
            persisted += 1

        await self.session.flush()
        reconciliation = await reconcile_recent_fires(self.session)

        run.status = IngestionRunStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.received_count = len(records)
        run.duplicate_count = duplicates
        run.persisted_count = persisted
        run.metrics = {
            "type_name": self.config.type_name,
            "format": "SHAPEZIP",
            "full_history": True,
            "reconciliation": reconciliation,
        }
        await self.session.commit()
        return ConnectorMetrics(
            received=len(records),
            duplicated=duplicates,
            persisted=persisted,
            raw_object_uri=raw_uri,
        )

    async def record_failure(
        self,
        started_at: datetime,
        error: Exception,
        raw: bytes | None = None,
    ) -> ConnectorMetrics:
        raw_uri = None
        if raw:
            raw_uri = await asyncio.to_thread(
                put_binary_object,
                f"effis/dead-letter/{started_at:%Y/%m/%d/%H%M%S}.zip",
                raw,
                "application/zip",
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
                metrics={"type_name": self.config.type_name, "format": "SHAPEZIP"},
            )
        )
        await self.session.commit()
        return ConnectorMetrics(errors=[str(error)], raw_object_uri=raw_uri)

    async def report_metrics(self, metrics: ConnectorMetrics) -> None:
        return None

    async def execute(self) -> ConnectorRunResult:
        started_at = datetime.now(UTC)
        raw: bytes | None = None
        try:
            raw = await self.fetch()
            return await self.execute_raw(raw, started_at)
        except Exception as exc:
            await self.session.rollback()
            metrics = await self.record_failure(started_at, exc, raw)
            return ConnectorRunResult(self.name, "failed", started_at, datetime.now(UTC), metrics)

    async def execute_raw(self, raw: bytes, started_at: datetime | None = None) -> ConnectorRunResult:
        run_started_at = started_at or datetime.now(UTC)
        try:
            self.validate(raw)
            records, payload_duplicates = self.deduplicate(self.normalize(raw))
            if not records:
                raise ValidationError("EFFIS SHAPEZIP contains no perimeters inside the configured area")
            metrics = await self.persist(records, raw, run_started_at)
            metrics.duplicated += payload_duplicates
            return ConnectorRunResult(self.name, "completed", run_started_at, datetime.now(UTC), metrics)
        except Exception as exc:
            await self.session.rollback()
            metrics = await self.record_failure(run_started_at, exc, raw)
            return ConnectorRunResult(self.name, "failed", run_started_at, datetime.now(UTC), metrics)

    async def _get_or_create_source(self) -> DataSource:
        result = await self.session.execute(select(DataSource).where(DataSource.name == "EFFIS"))
        source = result.scalar_one_or_none()
        if source is not None:
            source.source_type = ProvenanceType.OFFICIAL
            source.source_metadata = {
                **source.source_metadata,
                "wfs_url": self.config.wfs_url,
                "type_name": self.config.type_name,
                "format": "SHAPEZIP",
                "product": "Rapid Damage Assessment - Burnt Areas",
                "operational_source": False,
            }
            return source
        source = DataSource(
            name="EFFIS",
            source_type=ProvenanceType.OFFICIAL,
            authority="Copernicus Emergency Management Service / JRC",
            base_url="https://forest-fire.emergency.copernicus.eu/",
            license_name="Creative Commons Attribution 4.0",
            attribution="European Forest Fire Information System (EFFIS), European Commission",
            update_frequency="daily",
            expected_delay_seconds=86400,
            reliability_score=0.85,
            source_metadata={
                "wfs_url": self.config.wfs_url,
                "type_name": self.config.type_name,
                "format": "SHAPEZIP",
                "product": "Rapid Damage Assessment - Burnt Areas",
                "operational_source": False,
            },
        )
        self.session.add(source)
        await self.session.flush()
        return source

    def _update_incident(
        self,
        incident: Incident | None,
        source: DataSource,
        record: EffisBurntArea,
        now: datetime,
    ) -> Incident:
        external_id = f"{record.external_id}:incident"
        place = record.commune or record.province or record.country or "zona no identificada"
        title = f"Area cremada EFFIS - {place}"
        summary = "Perimetre publicat per EFFIS. No informa de l'estat ni de les tasques operatives d'extincio."
        if incident is None:
            incident = Incident(
                source_id=source.id,
                external_id=external_id,
                provenance=ProvenanceType.OFFICIAL,
                verification_status=VerificationStatus.PARTIAL,
                original_crs="EPSG:4326",
                status=IncidentStatus.REPORTED,
                title=title,
                summary=summary,
                observed_at=record.observed_at,
                received_at=now,
                confidence=0.85,
                original_metadata=record.metadata,
                deduplication_hash=record.deduplication_hash,
                geometry=WKTElement(record.geometry_wkt, srid=4326),
            )
        incident.title = title
        incident.summary = summary
        incident.provenance = ProvenanceType.OFFICIAL
        incident.verification_status = VerificationStatus.PARTIAL
        incident.observed_at = record.observed_at
        incident.received_at = now
        incident.confidence = 0.85
        previous_metadata = incident.original_metadata if isinstance(incident.original_metadata, dict) else {}
        reconciliation_keys = {
            "osint",
            "canonical_fire",
            "canonical_source",
            "hashtags",
            "affected_locations",
            "merged_incident_ids",
            "reconciliation_matches",
            "evidence_sources",
        }
        incident.original_metadata = {
            **record.metadata,
            **{key: value for key, value in previous_metadata.items() if key in reconciliation_keys},
        }
        incident.deduplication_hash = record.deduplication_hash
        incident.geometry = cast(Any, WKTElement(record.geometry_wkt, srid=4326))
        return incident

    def _shapefile_members(self, archive: zipfile.ZipFile) -> dict[str, str]:
        names = {name.lower(): name for name in archive.namelist()}
        members: dict[str, str] = {}
        for lower_name in names:
            if not lower_name.endswith(".shp"):
                continue
            base = lower_name[:-4]
            candidate = {extension: names[f"{base}{extension}"] for extension in (".shp", ".shx", ".dbf") if f"{base}{extension}" in names}
            if {".shp", ".shx", ".dbf"}.issubset(candidate):
                members = candidate
                cpg_name = names.get(f"{base}.cpg")
                if cpg_name:
                    members[".cpg"] = cpg_name
                break
        missing = {".shp", ".shx", ".dbf"} - members.keys()
        if missing:
            raise ValidationError(f"EFFIS SHAPEZIP is missing required files: {sorted(missing)}")
        return members

    def _bbox(self) -> tuple[float, float, float, float]:
        try:
            west, south, east, north = (float(value.strip()) for value in self.config.area_bbox.split(","))
        except ValueError as exc:
            raise ValidationError("EFFIS_AREA_BBOX must be west,south,east,north") from exc
        if west >= east or south >= north:
            raise ValidationError("EFFIS_AREA_BBOX bounds are invalid")
        return west, south, east, north

    @staticmethod
    def _bbox_intersects(shape_bbox: list[float], area_bbox: tuple[float, float, float, float]) -> bool:
        west, south, east, north = area_bbox
        shape_west, shape_south, shape_east, shape_north = shape_bbox
        return not (shape_east < west or shape_west > east or shape_north < south or shape_south > north)

    @staticmethod
    def _json_value(value: object) -> object:
        if isinstance(value, date | datetime):
            return value.isoformat()
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    @staticmethod
    def _date(value: object) -> datetime | None:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = datetime.combine(value, datetime.min.time())
        elif value not in (None, ""):
            try:
                parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _float(value: object) -> float | None:
        try:
            return float(cast(Any, value)) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _text(value: object) -> str | None:
        return str(value).strip() if value not in (None, "") else None
