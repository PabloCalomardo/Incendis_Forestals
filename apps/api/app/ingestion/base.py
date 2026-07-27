from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, TypeVar

RawT = TypeVar("RawT")
NormalizedT = TypeVar("NormalizedT")


@dataclass
class ConnectorMetrics:
    received: int = 0
    discarded: int = 0
    duplicated: int = 0
    persisted: int = 0
    errors: list[str] = field(default_factory=list)
    raw_object_uri: str | None = None


@dataclass
class ConnectorRunResult:
    connector_name: str
    status: str
    started_at: datetime
    finished_at: datetime
    metrics: ConnectorMetrics


class ConnectorError(RuntimeError):
    pass


class ValidationError(ConnectorError):
    pass


class BaseConnector(ABC, Generic[RawT, NormalizedT]):
    name: str

    @abstractmethod
    async def fetch(self) -> RawT:
        raise NotImplementedError

    @abstractmethod
    def validate(self, raw: RawT) -> None:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw: RawT) -> list[NormalizedT]:
        raise NotImplementedError

    @abstractmethod
    def deduplicate(self, records: list[NormalizedT]) -> tuple[list[NormalizedT], int]:
        raise NotImplementedError

    @abstractmethod
    async def persist(self, records: list[NormalizedT], raw: RawT) -> ConnectorMetrics:
        raise NotImplementedError

    @abstractmethod
    async def report_metrics(self, metrics: ConnectorMetrics) -> None:
        raise NotImplementedError
