from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.domain.enums import ProvenanceType, RoadIncidentKind, VerificationStatus
from app.domain.models import DataSource, FireDetection, RoadIncident
from app.services.quality import ConfidenceScorer, ConflictDetector, DetectionGroupingService, TemporalNormalizer


@dataclass
class QualityRecord:
    id: UUID = field(default_factory=uuid4)
    provenance: ProvenanceType = ProvenanceType.OBSERVED
    observed_at: datetime | None = None
    published_at: datetime | None = None
    received_at: datetime | None = None
    original_crs: str = "EPSG:4326"
    geometry: str | None = "POINT(-3.7 40.4)"
    latitude: float = 40.4
    longitude: float = -3.7
    confidence: float | None = None
    deduplication_hash: str | None = "abc"
    original_metadata: dict[str, object] = field(default_factory=lambda: {"raw": True})


def test_temporal_profile_uses_utc_age_and_delay() -> None:
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    record = QualityRecord(
        observed_at=now - timedelta(hours=2),
        published_at=now - timedelta(hours=1),
        received_at=now,
    )

    profile = TemporalNormalizer().profile(record, now=now)

    assert profile.timezone == "UTC"
    assert profile.age_seconds == 7200
    assert profile.delay_seconds == 3600


def test_confidence_is_explainable_and_penalizes_stale_data() -> None:
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    source = DataSource(name="Official", source_type=ProvenanceType.OFFICIAL, reliability_score=0.95)
    fresh = QualityRecord(provenance=ProvenanceType.OFFICIAL, observed_at=now - timedelta(minutes=30), received_at=now)
    stale = QualityRecord(provenance=ProvenanceType.OFFICIAL, observed_at=now - timedelta(days=5), received_at=now)

    fresh_score = ConfidenceScorer().score(fresh, source=source, now=now)
    stale_score = ConfidenceScorer().score(stale, source=source, now=now)

    assert fresh_score.value > stale_score.value
    assert stale_score.penalties["stale_data"] > 0.5
    assert fresh_score.algorithm_version == "confidence-v1"
    assert "source_authority" in fresh_score.factors


def test_estimated_record_does_not_become_official_confidence() -> None:
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)
    source = DataSource(name="Model", source_type=ProvenanceType.ESTIMATED, reliability_score=0.9)
    record = QualityRecord(provenance=ProvenanceType.ESTIMATED, observed_at=now, received_at=now)

    score = ConfidenceScorer().score(record, source=source, now=now)

    assert score.factors["officiality"] == 0.45
    assert score.category in {"medium", "low", "very_low"}


def test_grouping_links_nearby_fire_detections_without_merging_official_incidents() -> None:
    observed_at = datetime(2026, 7, 26, 12, tzinfo=UTC)
    first = FireDetection(
        id=uuid4(),
        provenance=ProvenanceType.OBSERVED,
        observed_at=observed_at,
        received_at=observed_at,
        verification_status=VerificationStatus.PENDING,
        original_metadata={},
        geometry="POINT(-3.7 40.4)",
        latitude=40.4,
        longitude=-3.7,
    )
    second = FireDetection(
        id=uuid4(),
        provenance=ProvenanceType.OBSERVED,
        observed_at=observed_at + timedelta(minutes=10),
        received_at=observed_at,
        verification_status=VerificationStatus.PENDING,
        original_metadata={},
        geometry="POINT(-3.701 40.401)",
        latitude=40.401,
        longitude=-3.701,
    )

    links = DetectionGroupingService().group_candidates([first, second])

    assert len(links) == 1
    assert links[0].distance_meters < 250
    assert "manual incident review" in links[0].explanation


def test_road_conflict_detector_keeps_opposite_statuses_visible() -> None:
    road_segment_id = uuid4()
    first = RoadIncident(
        id=uuid4(),
        road_segment_id=road_segment_id,
        kind=RoadIncidentKind.OFFICIAL_CLOSURE,
        provenance=ProvenanceType.OFFICIAL,
        verification_status=VerificationStatus.PENDING,
        original_metadata={},
    )
    second = RoadIncident(
        id=uuid4(),
        road_segment_id=road_segment_id,
        kind=RoadIncidentKind.INSUFFICIENT_DATA,
        provenance=ProvenanceType.OBSERVED,
        verification_status=VerificationStatus.PENDING,
        original_metadata={},
    )

    conflict = ConflictDetector().road_incident_conflict(first, second)

    assert conflict is not None
    assert conflict["conflict_type"] == "road_status_opposite"
    assert conflict["severity"] == "high"
