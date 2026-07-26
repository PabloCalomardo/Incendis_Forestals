import pytest

from app.domain.factories import make_data_source, make_incident, make_model_execution
from app.domain.models import DataSource, Incident, ModelExecution


@pytest.fixture
def data_source() -> DataSource:
    return make_data_source()


@pytest.fixture
def incident(data_source: DataSource) -> Incident:
    return make_incident(data_source)


@pytest.fixture
def model_execution() -> ModelExecution:
    return make_model_execution()
