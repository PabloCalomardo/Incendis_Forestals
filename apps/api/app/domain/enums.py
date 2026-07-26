from enum import StrEnum


class ProvenanceType(StrEnum):
    OFFICIAL = "official"
    OBSERVED = "observed"
    ESTIMATED = "estimated"
    UNVERIFIED = "unverified"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    PENDING = "pending"
    REJECTED = "rejected"


class IncidentStatus(StrEnum):
    REPORTED = "reported"
    ACTIVE = "active"
    STABILIZED = "stabilized"
    CONTROLLED = "controlled"
    EXTINGUISHED = "extinguished"
    ARCHIVED = "archived"


class IngestionRunStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class ZoneKind(StrEnum):
    EVACUATION = "evacuation"
    RESTRICTION = "restriction"


class RoadIncidentKind(StrEnum):
    OFFICIAL_CLOSURE = "official_closure"
    INSIDE_PERIMETER = "inside_perimeter"
    SMOKE_PROBABLE = "smoke_probable"
    REDUCED_VISIBILITY = "reduced_visibility"
    INSUFFICIENT_DATA = "insufficient_data"


class UserRole(StrEnum):
    FIREFIGHTER = "firefighter"
    ANALYST = "analyst"
    INCIDENT_COMMANDER = "incident_commander"
    ADMINISTRATOR = "administrator"
