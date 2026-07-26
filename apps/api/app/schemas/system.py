from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, bool]


class VersionResponse(BaseModel):
    name: str
    version: str
    environment: str
