from pathlib import Path


def test_phase_2_migration_contains_spatial_and_temporal_indexes() -> None:
    migration = Path("apps/api/alembic/versions/0002_domain_lineage_model.py").read_text()

    assert "postgresql_using=\"gist\"" in migration
    assert "observed_at" in migration
    assert "published_at" in migration
    assert "received_at" in migration
    assert "ck_smoke_forecasts_not_official" in migration
    assert "ck_risk_forecasts_not_official" in migration
