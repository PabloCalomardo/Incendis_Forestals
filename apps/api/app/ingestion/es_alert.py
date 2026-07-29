import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import IngestionRunStatus, ProvenanceType, VerificationStatus, ZoneKind
from app.domain.models import DataIngestionRun, DataSource, RestrictionZone
from app.infrastructure.object_storage import put_text_object
from app.ingestion.base import ConnectorMetrics
from app.ingestion.spatial import geojson_geometry_to_polygon_wkt


@dataclass(frozen=True)
class EsAlertRecord:
    external_id: str
    title: str
    instruction: str
    restriction_type: str
    sent_at: datetime
    expires_at: datetime
    geometry: dict[str, Any]
    authority: str
    level: str
    area: str | None = None
    url: str | None = None


class EsAlertRegistry:
    name = "es_alert_registry_sync"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def sync(
        self,
        records: list[EsAlertRecord],
        source_generated_at: datetime,
        complete_snapshot: bool,
    ) -> ConnectorMetrics:
        started_at = datetime.now(UTC)
        source_generated_at = self._aware(source_generated_at)
        active = [record for record in records if self._aware(record.expires_at) > source_generated_at]
        normalized: list[tuple[EsAlertRecord, str]] = []
        discarded = len(records) - len(active)
        for record in active:
            geometry_wkt = geojson_geometry_to_polygon_wkt(record.geometry)
            if geometry_wkt is None:
                discarded += 1
                continue
            normalized.append((record, geometry_wkt))

        raw = json.dumps(
            {
                "source_generated_at": source_generated_at,
                "complete_snapshot": complete_snapshot,
                "alerts": [asdict(record) for record in records],
            },
            ensure_ascii=False,
            default=str,
        )
        source = await self._get_or_create_source()
        raw_uri = await asyncio.to_thread(
            put_text_object,
            f"es-alert/{started_at:%Y/%m/%d/%H%M%S}.json",
            raw,
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

        external_ids = [record.external_id for record, _ in normalized]
        if complete_snapshot:
            stale = [
                RestrictionZone.source_id == source.id,
                or_(RestrictionZone.expires_at.is_(None), RestrictionZone.expires_at > source_generated_at),
            ]
            if external_ids:
                stale.append(RestrictionZone.external_id.not_in(external_ids))
            await self.session.execute(update(RestrictionZone).where(*stale).values(expires_at=source_generated_at))

        existing: dict[str, RestrictionZone] = {}
        if external_ids:
            existing_result = await self.session.execute(
                select(RestrictionZone).where(
                    RestrictionZone.source_id == source.id,
                    RestrictionZone.external_id.in_(external_ids),
                )
            )
            existing = {
                record.external_id: record
                for record in existing_result.scalars()
                if record.external_id is not None
            }
        inserted = 0
        updated = 0
        for record, geometry_wkt in normalized:
            metadata = {
                "channel": "es-alert",
                "instruction": record.instruction,
                "authority": record.authority,
                "alert_level": record.level,
                "area": record.area,
                "url": record.url,
                "source_generated_at": source_generated_at.isoformat(),
            }
            deduplication_hash = self._hash(record, metadata)
            current = existing.get(record.external_id)
            values = {
                "observed_at": self._aware(record.sent_at),
                "published_at": self._aware(record.sent_at),
                "received_at": started_at,
                "expires_at": self._aware(record.expires_at),
                "original_metadata": metadata,
                "deduplication_hash": deduplication_hash,
                "geometry": WKTElement(geometry_wkt, srid=4326),
                "name": record.title[:180],
                "restriction_type": record.restriction_type[:120],
            }
            if current is not None:
                for key, value in values.items():
                    setattr(current, key, value)
                current.version += 1
                updated += 1
                continue
            self.session.add(
                RestrictionZone(
                    source_id=source.id,
                    external_id=record.external_id,
                    provenance=ProvenanceType.OFFICIAL,
                    verification_status=VerificationStatus.VERIFIED,
                    confidence=1.0,
                    original_crs="EPSG:4326",
                    zone_kind=ZoneKind.RESTRICTION,
                    **values,
                )
            )
            inserted += 1

        run.status = IngestionRunStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.received_count = len(records)
        run.discarded_count = discarded
        run.persisted_count = inserted + updated
        run.metrics = {
            "complete_snapshot": complete_snapshot,
            "active": len(normalized),
            "inserted": inserted,
            "updated": updated,
        }
        await self.session.commit()
        return ConnectorMetrics(
            received=len(records),
            discarded=discarded,
            persisted=inserted + updated,
            raw_object_uri=raw_uri,
        )

    async def _get_or_create_source(self) -> DataSource:
        result = await self.session.execute(select(DataSource).where(DataSource.name == "ES-Alert"))
        source = result.scalar_one_or_none()
        if source is not None:
            return source
        source = DataSource(
            name="ES-Alert",
            source_type=ProvenanceType.OFFICIAL,
            authority="Sistema Nacional de Proteccion Civil / autoritat emissora",
            base_url="https://www.proteccioncivil.es/coordinacion/redes/ran/public-warning-system",
            license_name="Official emergency information",
            attribution="ES-Alert / Proteccion Civil",
            update_frequency="event driven",
            reliability_score=1.0,
            source_metadata={
                "channel": "cell-broadcast",
                "ingestion": "authenticated snapshot sync",
                "public_feed_available": False,
            },
        )
        self.session.add(source)
        await self.session.flush()
        return source

    def _aware(self, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def _hash(self, record: EsAlertRecord, metadata: dict[str, Any]) -> str:
        stable = json.dumps(
            {"record": asdict(record), "metadata": metadata},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()
