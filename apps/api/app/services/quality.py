from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ProvenanceType, RoadIncidentKind
from app.domain.models import (
    ConfidenceAssessment,
    DataConflict,
    DataSource,
    FireDetection,
    Incident,
    ObservationLink,
    RoadIncident,
    RoadSegment,
    WeatherForecast,
    WeatherObservation,
)

ALGORITHM_VERSION = "confidence-v1"


@dataclass(frozen=True)
class TemporalProfile:
    observed_at: datetime | None
    published_at: datetime | None
    received_at: datetime | None
    calculated_at: datetime
    age_seconds: int | None
    delay_seconds: int | None
    timezone: str


@dataclass(frozen=True)
class SpatialQuality:
    original_crs: str
    normalized_crs: str
    is_valid: bool
    repaired: bool
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConfidenceResult:
    value: float
    category: str
    factors: dict[str, float]
    penalties: dict[str, float]
    warnings: list[str]
    calculated_at: datetime
    algorithm_version: str = ALGORITHM_VERSION


@dataclass(frozen=True)
class DetectionLinkCandidate:
    first_id: UUID
    second_id: UUID
    distance_meters: float
    minutes_apart: float
    explanation: str


class TemporalNormalizer:
    def profile(self, record: Any, now: datetime | None = None) -> TemporalProfile:
        calculated_at = now or datetime.now(UTC)
        observed_at = self._utc(getattr(record, "observed_at", None))
        published_at = self._utc(getattr(record, "published_at", None))
        received_at = self._utc(getattr(record, "received_at", None))
        age_seconds = int((calculated_at - observed_at).total_seconds()) if observed_at else None
        if published_at and received_at:
            delay_seconds = max(0, int((received_at - published_at).total_seconds()))
        elif observed_at and received_at:
            delay_seconds = max(0, int((received_at - observed_at).total_seconds()))
        else:
            delay_seconds = None
        return TemporalProfile(
            observed_at=observed_at,
            published_at=published_at,
            received_at=received_at,
            calculated_at=calculated_at,
            age_seconds=age_seconds,
            delay_seconds=delay_seconds,
            timezone="UTC",
        )

    def _utc(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class SpatialNormalizer:
    def quality(self, record: Any) -> SpatialQuality:
        original_crs = str(getattr(record, "original_crs", "EPSG:4326") or "EPSG:4326")
        warnings: list[str] = []
        is_valid = True
        if original_crs.upper() != "EPSG:4326":
            warnings.append("geometry normalized to EPSG:4326 expected downstream")
        if getattr(record, "geometry", None) is None:
            is_valid = False
            warnings.append("missing geometry")
        if hasattr(record, "latitude") and hasattr(record, "longitude"):
            latitude = record.latitude
            longitude = record.longitude
            if latitude is None or longitude is None or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                is_valid = False
                warnings.append("coordinates outside valid lon/lat bounds")
        return SpatialQuality(
            original_crs=original_crs,
            normalized_crs="EPSG:4326",
            is_valid=is_valid,
            repaired=False,
            warnings=warnings,
        )


class ConfidenceScorer:
    def __init__(self) -> None:
        self.temporal = TemporalNormalizer()
        self.spatial = SpatialNormalizer()

    def score(self, record: Any, source: DataSource | None = None, now: datetime | None = None) -> ConfidenceResult:
        calculated_at = now or datetime.now(UTC)
        temporal = self.temporal.profile(record, calculated_at)
        spatial = self.spatial.quality(record)
        provenance = getattr(record, "provenance", ProvenanceType.UNVERIFIED)
        source_score = float(getattr(source, "reliability_score", None) or 0.5)
        factors = {
            "source_authority": source_score,
            "officiality": self._officiality_score(provenance),
            "freshness": self._freshness_score(temporal.age_seconds),
            "delay": self._delay_score(temporal.delay_seconds),
            "geometry_quality": 1.0 if spatial.is_valid else 0.0,
            "input_availability": self._input_availability(record),
            "coherence": self._coherence(record),
        }
        penalties = {
            "stale_data": 1.0 - factors["freshness"],
            "delayed_publication": 1.0 - factors["delay"],
            "invalid_geometry": 0.35 if not spatial.is_valid else 0.0,
            "unverified_source": 0.15 if provenance == ProvenanceType.UNVERIFIED else 0.0,
        }
        weighted = (
            factors["source_authority"] * 0.2
            + factors["officiality"] * 0.2
            + factors["freshness"] * 0.2
            + factors["delay"] * 0.1
            + factors["geometry_quality"] * 0.15
            + factors["input_availability"] * 0.1
            + factors["coherence"] * 0.05
        )
        provenance_cap = self._provenance_cap(provenance)
        value = max(0.0, min(provenance_cap, weighted - penalties["invalid_geometry"] - penalties["unverified_source"]))
        warnings = list(spatial.warnings)
        if penalties["stale_data"] > 0.4:
            warnings.append("data is stale")
        if penalties["delayed_publication"] > 0.4:
            warnings.append("data arrived with high delay")
        return ConfidenceResult(
            value=round(value, 4),
            category=self._category(value),
            factors={key: round(item, 4) for key, item in factors.items()},
            penalties={key: round(item, 4) for key, item in penalties.items()},
            warnings=warnings,
            calculated_at=calculated_at,
        )

    def _officiality_score(self, provenance: ProvenanceType) -> float:
        return {
            ProvenanceType.OFFICIAL: 1.0,
            ProvenanceType.OBSERVED: 0.65,
            ProvenanceType.ESTIMATED: 0.45,
            ProvenanceType.UNVERIFIED: 0.25,
        }[provenance]

    def _freshness_score(self, age_seconds: int | None) -> float:
        if age_seconds is None:
            return 0.45
        age_hours = max(0.0, age_seconds / 3600)
        if age_hours <= 1:
            return 1.0
        if age_hours <= 6:
            return 0.85
        if age_hours <= 24:
            return 0.65
        if age_hours <= 72:
            return 0.35
        return 0.15

    def _delay_score(self, delay_seconds: int | None) -> float:
        if delay_seconds is None:
            return 0.75
        delay_hours = max(0.0, delay_seconds / 3600)
        if delay_hours <= 1:
            return 1.0
        if delay_hours <= 6:
            return 0.75
        if delay_hours <= 24:
            return 0.45
        return 0.2

    def _input_availability(self, record: Any) -> float:
        values = [
            getattr(record, name, None)
            for name in (
                "observed_at",
                "received_at",
                "deduplication_hash",
                "original_metadata",
                "geometry",
            )
        ]
        present = sum(1 for value in values if value not in (None, {}, ""))
        return present / len(values)

    def _coherence(self, record: Any) -> float:
        confidence = getattr(record, "confidence", None)
        if confidence is not None and not (0 <= confidence <= 1):
            return 0.0
        return 1.0

    def _category(self, value: float) -> str:
        if value >= 0.8:
            return "high"
        if value >= 0.55:
            return "medium"
        if value >= 0.3:
            return "low"
        return "very_low"

    def _provenance_cap(self, provenance: ProvenanceType) -> float:
        return {
            ProvenanceType.OFFICIAL: 1.0,
            ProvenanceType.OBSERVED: 0.88,
            ProvenanceType.ESTIMATED: 0.79,
            ProvenanceType.UNVERIFIED: 0.55,
        }[provenance]


class DetectionGroupingService:
    def group_candidates(
        self,
        detections: list[FireDetection],
        max_distance_meters: float = 2500,
        max_minutes_apart: float = 180,
    ) -> list[DetectionLinkCandidate]:
        candidates: list[DetectionLinkCandidate] = []
        ordered = sorted(detections, key=lambda item: (item.observed_at or datetime.min.replace(tzinfo=UTC), str(item.id)))
        for index, first in enumerate(ordered):
            for second in ordered[index + 1 :]:
                if first.observed_at is None or second.observed_at is None:
                    continue
                minutes = abs((second.observed_at - first.observed_at).total_seconds()) / 60
                if minutes > max_minutes_apart:
                    continue
                distance = haversine_meters(first.latitude, first.longitude, second.latitude, second.longitude)
                if distance <= max_distance_meters:
                    candidates.append(
                        DetectionLinkCandidate(
                            first_id=first.id,
                            second_id=second.id,
                            distance_meters=round(distance, 2),
                            minutes_apart=round(minutes, 2),
                            explanation="nearby satellite detections grouped for manual incident review",
                        )
                    )
        return candidates


class ConflictDetector:
    def road_incident_conflict(self, first: RoadIncident, second: RoadIncident) -> dict[str, Any] | None:
        if first.road_segment_id != second.road_segment_id or first.id == second.id:
            return None
        opposite = {
            RoadIncidentKind.OFFICIAL_CLOSURE,
            RoadIncidentKind.INSUFFICIENT_DATA,
        }
        if {first.kind, second.kind} == opposite:
            return {
                "conflict_type": "road_status_opposite",
                "severity": "high",
                "explanation": "same road segment has official closure and insufficient-data status simultaneously",
                "evidence": {"first_kind": first.kind.value, "second_kind": second.kind.value},
            }
        return None


class QualityPersistenceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.scorer = ConfidenceScorer()
        self.grouping = DetectionGroupingService()
        self.conflicts = ConflictDetector()

    async def run(self, limit: int = 200) -> dict[str, int]:
        assessed = 0
        linked = 0
        conflicts = 0
        for resource_type, model in RESOURCE_MODELS.items():
            result = await self.session.execute(select(model).order_by(desc(model.created_at)).limit(limit))
            for record in result.scalars():
                source = await self._source_for(record)
                score = self.scorer.score(record, source=source)
                self.session.add(
                    ConfidenceAssessment(
                        resource_type=resource_type,
                        resource_id=record.id,
                        algorithm_version=score.algorithm_version,
                        calculated_at=score.calculated_at,
                        confidence=score.value,
                        category=score.category,
                        factors=score.factors,
                        penalties=score.penalties,
                        warnings=score.warnings,
                    )
                )
                assessed += 1

        detection_result = await self.session.execute(select(FireDetection).order_by(desc(FireDetection.observed_at)).limit(limit))
        detection_links = self.grouping.group_candidates(list(detection_result.scalars()))
        for link in detection_links:
            if await self._link_exists("fire_detection", link.first_id, "fire_detection", link.second_id):
                continue
            self.session.add(
                ObservationLink(
                    resource_type="fire_detection",
                    resource_id=link.first_id,
                    related_resource_type="fire_detection",
                    related_resource_id=link.second_id,
                    relation_kind="nearby_fire_detection",
                    confidence=0.7,
                    explanation=link.explanation,
                    evidence={"distance_meters": link.distance_meters, "minutes_apart": link.minutes_apart},
                )
            )
            linked += 1

        road_result = await self.session.execute(select(RoadIncident).order_by(desc(RoadIncident.observed_at)).limit(limit))
        road_incidents = list(road_result.scalars())
        for index, first in enumerate(road_incidents):
            for second in road_incidents[index + 1 :]:
                conflict = self.conflicts.road_incident_conflict(first, second)
                if conflict is None:
                    continue
                if await self._conflict_exists("road_incident", first.id, "road_incident", second.id, conflict["conflict_type"]):
                    continue
                self.session.add(
                    DataConflict(
                        conflict_type=conflict["conflict_type"],
                        resource_type="road_incident",
                        resource_id=first.id,
                        conflicting_resource_type="road_incident",
                        conflicting_resource_id=second.id,
                        severity=conflict["severity"],
                        detected_at=datetime.now(UTC),
                        explanation=conflict["explanation"],
                        evidence=conflict["evidence"],
                    )
                )
                conflicts += 1

        await self.session.commit()
        return {"assessed": assessed, "linked": linked, "conflicts": conflicts}

    async def trace(self, resource_type: str, resource_id: UUID) -> dict[str, Any] | None:
        model = RESOURCE_MODELS.get(resource_type)
        if model is None:
            return None
        record = await self.session.get(model, resource_id)
        if record is None:
            return None
        source = await self._source_for(record)
        assessments = await self.session.execute(
            select(ConfidenceAssessment)
            .where(
                and_(
                    ConfidenceAssessment.resource_type == resource_type,
                    ConfidenceAssessment.resource_id == resource_id,
                )
            )
            .order_by(desc(ConfidenceAssessment.calculated_at))
            .limit(5)
        )
        conflicts = await self.session.execute(
            select(DataConflict)
            .where(
                or_(
                    and_(DataConflict.resource_type == resource_type, DataConflict.resource_id == resource_id),
                    and_(
                        DataConflict.conflicting_resource_type == resource_type,
                        DataConflict.conflicting_resource_id == resource_id,
                    ),
                )
            )
            .order_by(desc(DataConflict.detected_at))
            .limit(10)
        )
        links = await self.session.execute(
            select(ObservationLink)
            .where(
                or_(
                    and_(ObservationLink.resource_type == resource_type, ObservationLink.resource_id == resource_id),
                    and_(
                        ObservationLink.related_resource_type == resource_type,
                        ObservationLink.related_resource_id == resource_id,
                    ),
                )
            )
            .order_by(desc(ObservationLink.created_at))
            .limit(10)
        )
        temporal = TemporalNormalizer().profile(record)
        return {
            "resource": {
                "type": resource_type,
                "id": str(resource_id),
                "provenance": getattr(record, "provenance", None),
                "verification_status": getattr(record, "verification_status", None),
                "external_id": getattr(record, "external_id", None),
                "deduplication_hash": getattr(record, "deduplication_hash", None),
                "original_metadata": getattr(record, "original_metadata", {}),
            },
            "source": {
                "id": str(source.id) if source else None,
                "name": source.name if source else None,
                "authority": source.authority if source else None,
                "reliability_score": source.reliability_score if source else None,
            },
            "temporal": temporal.__dict__,
            "confidence": [
                {
                    "value": item.confidence,
                    "category": item.category,
                    "factors": item.factors,
                    "penalties": item.penalties,
                    "warnings": item.warnings,
                    "calculated_at": item.calculated_at,
                    "algorithm_version": item.algorithm_version,
                }
                for item in assessments.scalars()
            ],
            "conflicts": [
                {
                    "type": item.conflict_type,
                    "severity": item.severity,
                    "explanation": item.explanation,
                    "evidence": item.evidence,
                    "detected_at": item.detected_at,
                }
                for item in conflicts.scalars()
            ],
            "links": [
                {
                    "resource_type": item.resource_type,
                    "resource_id": str(item.resource_id),
                    "related_resource_type": item.related_resource_type,
                    "related_resource_id": str(item.related_resource_id),
                    "relation_kind": item.relation_kind,
                    "confidence": item.confidence,
                    "explanation": item.explanation,
                    "evidence": item.evidence,
                }
                for item in links.scalars()
            ],
        }

    async def _source_for(self, record: Any) -> DataSource | None:
        source_id = getattr(record, "source_id", None)
        if source_id is None:
            return None
        return await self.session.get(DataSource, source_id)

    async def _link_exists(self, resource_type: str, resource_id: UUID, related_type: str, related_id: UUID) -> bool:
        result = await self.session.execute(
            select(ObservationLink.id).where(
                and_(
                    ObservationLink.resource_type == resource_type,
                    ObservationLink.resource_id == resource_id,
                    ObservationLink.related_resource_type == related_type,
                    ObservationLink.related_resource_id == related_id,
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def _conflict_exists(
        self,
        resource_type: str,
        resource_id: UUID,
        conflicting_type: str,
        conflicting_id: UUID,
        conflict_type: str,
    ) -> bool:
        result = await self.session.execute(
            select(DataConflict.id).where(
                and_(
                    DataConflict.resource_type == resource_type,
                    DataConflict.resource_id == resource_id,
                    DataConflict.conflicting_resource_type == conflicting_type,
                    DataConflict.conflicting_resource_id == conflicting_id,
                    DataConflict.conflict_type == conflict_type,
                )
            )
        )
        return result.scalar_one_or_none() is not None


RESOURCE_MODELS: dict[str, Any] = {
    "fire_detection": FireDetection,
    "incident": Incident,
    "road_segment": RoadSegment,
    "road_incident": RoadIncident,
    "weather_observation": WeatherObservation,
    "weather_forecast": WeatherForecast,
}


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    return 2 * radius * asin(sqrt(a))
