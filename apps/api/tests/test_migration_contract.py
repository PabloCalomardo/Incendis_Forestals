from pathlib import Path


def test_phase_2_migration_contains_spatial_and_temporal_indexes() -> None:
    migration = Path("apps/api/alembic/versions/0002_domain_lineage_model.py").read_text()

    assert "postgresql_using=\"gist\"" in migration
    assert "observed_at" in migration
    assert "published_at" in migration
    assert "received_at" in migration
    assert "ck_smoke_forecasts_not_official" in migration
    assert "ck_risk_forecasts_not_official" in migration


def test_osint_migration_supports_nullable_official_geometry_and_review() -> None:
    migration = Path("apps/api/alembic/versions/0004_emergency_osint.py").read_text()

    assert '"emergency_publications"' in migration
    assert '"review_status"' in migration
    assert '"deduplication_hash"' in migration
    assert '"geometry_inference_method"' in migration
    assert 'op.alter_column("incidents", "geometry"' in migration
    assert 'postgresql_using="gist"' in migration
