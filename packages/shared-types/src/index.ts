export type ProvenanceType = "official" | "observed" | "estimated" | "unverified";

export type VerificationStatus = "verified" | "partial" | "pending" | "rejected";

export type IncidentStatus =
  | "reported"
  | "active"
  | "stabilized"
  | "controlled"
  | "extinguished"
  | "archived";

export type IngestionRunStatus = "started" | "completed" | "failed" | "partial" | "cancelled";

export type VersionResponse = {
  name: string;
  version: string;
  environment: string;
};

export type HealthResponse = {
  status: "ok";
};

export type ReadyResponse = {
  status: "ready" | "not_ready";
  checks: Record<string, boolean>;
};

export type ApiStatus = {
  ok: boolean;
  version?: string;
};
