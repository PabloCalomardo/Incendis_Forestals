from pathlib import Path


def test_required_top_level_paths_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    required_paths = [
        "apps/web",
        "apps/api",
        "workers/ingestion",
        "workers/geospatial",
        "workers/predictions",
        "packages/shared-types",
        "packages/config",
        "packages/ui",
        "infrastructure/docker",
        "infrastructure/monitoring",
        "docs",
        "tests",
        "docker-compose.yml",
        ".env.example",
        "Makefile",
    ]

    for relative_path in required_paths:
        assert (root / relative_path).exists(), relative_path
