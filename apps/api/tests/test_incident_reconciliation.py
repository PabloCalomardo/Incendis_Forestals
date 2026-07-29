from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.domain.models import FirePerimeter
from app.ingestion.incident_reconciliation import (
    effis_area_neighborhood_meters,
    effis_group_reasons,
    extract_incident_hashtags,
    firms_perimeter_match,
    is_fire_match,
    merge_case_insensitive_values,
    score_fire_match,
)


def test_groups_simultaneous_adjacent_effis_polygons_in_same_province() -> None:
    reasons = effis_group_reasons(
        distance_meters=900,
        time_delta=timedelta(hours=8),
        first_hashtags=set(),
        second_hashtags=set(),
        first_commune="Municipi A",
        second_commune="Municipi B",
        first_province="Madrid",
        second_province="Madrid",
    )

    assert {"adjacent_1500m", "simultaneous_2d", "same_province"} <= set(reasons)


def test_groups_separate_focus_polygons_when_they_share_a_specific_hashtag() -> None:
    reasons = effis_group_reasons(
        distance_meters=18_000,
        time_delta=timedelta(days=4),
        first_hashtags={"#IFSierraOeste"},
        second_hashtags={"#ifsierraoeste"},
        first_commune="Municipi A",
        second_commune="Municipi B",
        first_province="Madrid",
        second_province="Madrid",
    )

    assert {"shared_hashtag", "nearby_25km", "simultaneous_7d"} <= set(reasons)


def test_scales_effis_neighborhood_with_combined_burnt_area() -> None:
    small_threshold = effis_area_neighborhood_meters(50, 50)
    large_threshold = effis_area_neighborhood_meters(33_000, 67)

    assert small_threshold < 5_000
    assert large_threshold > 23_000
    assert "area_scaled_neighborhood" in effis_group_reasons(
        distance_meters=23_000,
        time_delta=timedelta(days=4),
        first_hashtags=set(),
        second_hashtags=set(),
        first_commune="Municipi A",
        second_commune="Municipi B",
        first_province="Guadalajara",
        second_province="Guadalajara",
        first_area_hectares=33_000,
        second_area_hectares=67,
    )


def test_does_not_use_large_neighborhood_for_two_small_fires() -> None:
    reasons = effis_group_reasons(
        distance_meters=10_000,
        time_delta=timedelta(hours=8),
        first_hashtags=set(),
        second_hashtags=set(),
        first_commune="Municipi A",
        second_commune="Municipi B",
        first_province="Madrid",
        second_province="Madrid",
        first_area_hectares=10,
        second_area_hectares=20,
    )

    assert reasons == []


def test_does_not_group_nearby_fires_without_shared_geographic_context() -> None:
    reasons = effis_group_reasons(
        distance_meters=900,
        time_delta=timedelta(hours=8),
        first_hashtags=set(),
        second_hashtags=set(),
        first_commune="Municipi A",
        second_commune="Municipi B",
        first_province="Madrid",
        second_province="Avila",
    )

    assert reasons == []


def test_extracts_only_incident_specific_fire_hashtags() -> None:
    assert extract_incident_hashtags("Actualització #IFSierraOeste amb #Bomberscat sota el pla #INFOMA26") == {"#IFSierraOeste"}


def test_preserves_secondary_polygon_hashtags_when_merging_effis_groups() -> None:
    assert merge_case_insensitive_values([], ["#IFSierraOeste"], ["#ifsierraoeste", "#IFAlmorox"]) == [
        "#IFAlmorox",
        "#IFSierraOeste",
    ]


def test_firms_distance_query_casts_bound_perimeter_to_geography() -> None:
    perimeter_geometry = select(FirePerimeter.geometry).where(FirePerimeter.external_id == "effis:1").scalar_subquery()
    condition = firms_perimeter_match(perimeter_geometry)
    compiled = str(select(1).where(condition).compile(dialect=postgresql.dialect()))

    assert "CAST((SELECT fire_perimeters.geometry" in compiled
    assert "AS geography" in compiled


def test_matches_effis_fire_by_commune_and_time() -> None:
    score, reasons = score_fire_match(
        commune="Villa del Prado",
        province="Madrid",
        canonical_hashtags=set(),
        canonical_locations=set(),
        candidate_text="Incendi forestal a Villa del Prado",
        candidate_locations={"Villa del Prado"},
        candidate_hashtags={"#IFSierraOeste"},
        spatial_match=False,
        time_delta=timedelta(hours=8),
    )

    assert score >= 60
    assert {"commune_location", "time_3d"} <= set(reasons)


def test_matches_updates_by_shared_hashtag_without_requiring_geometry() -> None:
    score, reasons = score_fire_match(
        commune="Robledo de Chavela",
        province="Madrid",
        canonical_hashtags={"#IFSierraOeste"},
        canonical_locations=set(),
        candidate_text="Continuen les tasques d'extinció al sector nord",
        candidate_locations=set(),
        candidate_hashtags={"#ifsierraoeste"},
        spatial_match=False,
        time_delta=timedelta(days=2),
    )

    assert score >= 100
    assert "shared_hashtag" in reasons


def test_matches_geocoded_municipality_intersecting_effis_perimeter() -> None:
    score, reasons = score_fire_match(
        commune="Nules",
        province="Castelló",
        canonical_hashtags=set(),
        canonical_locations=set(),
        candidate_text="Efectius treballen al flanc esquerre de #IFLaValldUixó",
        candidate_locations={"Artana"},
        candidate_hashtags={"#IFLaValldUixó"},
        spatial_match=True,
        spatial_distance_meters=0,
        time_delta=timedelta(days=2),
    )

    assert score >= 60
    assert "spatial_intersection" in reasons
    assert is_fire_match(score, reasons) is True


def test_does_not_match_on_province_and_time_alone() -> None:
    score, _ = score_fire_match(
        commune="Robledo de Chavela",
        province="Madrid",
        canonical_hashtags=set(),
        canonical_locations=set(),
        candidate_text="Alerta genèrica per risc a Madrid",
        candidate_locations=set(),
        candidate_hashtags=set(),
        spatial_match=False,
        time_delta=timedelta(hours=2),
    )

    assert score < 60


def test_rejects_a_municipality_mentioned_inside_a_broad_list_without_spatial_evidence() -> None:
    score, reasons = score_fire_match(
        commune="Sant Quirze Safaja",
        province="Barcelona",
        canonical_hashtags=set(),
        canonical_locations=set(),
        candidate_text="Relació general de zones: Sant Quirze Safaja i molts altres municipis",
        candidate_locations=set(),
        candidate_hashtags=set(),
        spatial_match=False,
        time_delta=timedelta(hours=2),
    )

    assert score >= 60
    assert is_fire_match(score, reasons) is False


def test_accepts_a_named_municipality_with_a_specific_fire_hashtag() -> None:
    score, reasons = score_fire_match(
        commune="Fresnedillas de la Oliva",
        province="Madrid",
        canonical_hashtags=set(),
        canonical_locations=set(),
        candidate_text="Incendi forestal a Fresnedillas de la Oliva #IFSierraOeste",
        candidate_locations=set(),
        candidate_hashtags={"#IFSierraOeste"},
        spatial_match=False,
        time_delta=timedelta(hours=2),
    )

    assert is_fire_match(score, reasons) is True
