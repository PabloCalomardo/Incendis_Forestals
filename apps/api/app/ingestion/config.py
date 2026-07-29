import json
from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class FirmsConnectorConfig:
    map_key: str
    source: str
    area: str
    day_range: int
    base_url: str
    timeout_seconds: int
    max_retries: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "FirmsConnectorConfig":
        return cls(
            map_key=settings.firms_map_key,
            source=settings.firms_source,
            area=settings.firms_area_spain,
            day_range=settings.firms_day_range,
            base_url=settings.firms_base_url.rstrip("/"),
            timeout_seconds=settings.firms_timeout_seconds,
            max_retries=settings.firms_max_retries,
        )


@dataclass(frozen=True)
class EffisConnectorConfig:
    wfs_url: str
    type_name: str
    area_bbox: str
    timeout_seconds: int
    max_retries: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "EffisConnectorConfig":
        return cls(
            wfs_url=settings.effis_wfs_url,
            type_name=settings.effis_type_name,
            area_bbox=settings.effis_area_bbox,
            timeout_seconds=settings.effis_timeout_seconds,
            max_retries=settings.effis_max_retries,
        )


@dataclass(frozen=True)
class AemetConnectorConfig:
    api_key: str
    base_url: str
    timeout_seconds: int
    max_retries: int
    forecast_municipalities: list[str]
    forecast_locations: dict[str, dict[str, object]]

    @classmethod
    def from_settings(cls, settings: Settings) -> "AemetConnectorConfig":
        municipalities = [item.strip() for item in settings.aemet_forecast_municipalities.split(",") if item.strip()]
        locations = json.loads(settings.aemet_forecast_locations_json or "{}")
        return cls(
            api_key=settings.aemet_api_key,
            base_url=settings.aemet_base_url.rstrip("/"),
            timeout_seconds=settings.aemet_timeout_seconds,
            max_retries=settings.aemet_max_retries,
            forecast_municipalities=municipalities,
            forecast_locations=locations,
        )


@dataclass(frozen=True)
class AemetAlertsConnectorConfig:
    feed_url: str
    timeout_seconds: int
    max_retries: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "AemetAlertsConnectorConfig":
        return cls(
            feed_url=settings.aemet_alerts_feed_url,
            timeout_seconds=settings.aemet_alerts_timeout_seconds,
            max_retries=settings.aemet_alerts_max_retries,
        )


@dataclass(frozen=True)
class IgnConnectorConfig:
    wfs_base_url: str
    transport_typename: str
    area_bbox: str
    feature_limit: int
    max_features: int
    max_pages_per_tile: int
    tile_size_degrees: float
    target_datex_restrictions: bool
    timeout_seconds: int
    max_retries: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "IgnConnectorConfig":
        return cls(
            wfs_base_url=settings.ign_wfs_base_url,
            transport_typename=settings.ign_transport_typename,
            area_bbox=settings.ign_area_bbox,
            feature_limit=settings.ign_feature_limit,
            max_features=settings.ign_max_features,
            max_pages_per_tile=settings.ign_max_pages_per_tile,
            tile_size_degrees=settings.ign_tile_size_degrees,
            target_datex_restrictions=settings.ign_target_datex_restrictions,
            timeout_seconds=settings.ign_timeout_seconds,
            max_retries=settings.ign_max_retries,
        )


@dataclass(frozen=True)
class OsmConnectorConfig:
    overpass_url: str
    area_bbox: str
    timeout_seconds: int
    max_retries: int
    feature_limit: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "OsmConnectorConfig":
        return cls(
            overpass_url=settings.osm_overpass_url,
            area_bbox=settings.osm_area_bbox,
            timeout_seconds=settings.osm_timeout_seconds,
            max_retries=settings.osm_max_retries,
            feature_limit=settings.osm_feature_limit,
        )


@dataclass(frozen=True)
class DatexConnectorConfig:
    feed_urls: list[str]
    timeout_seconds: int
    max_retries: int
    pk_to_xy_url: str
    pk_to_xy_timeout_seconds: int
    pk_sample_step_km: float
    pk_sample_budget: int
    osrm_route_url: str
    osrm_timeout_seconds: int
    overpass_url: str
    overpass_timeout_seconds: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "DatexConnectorConfig":
        return cls(
            feed_urls=[item.strip() for item in settings.datex_feed_urls.split(",") if item.strip()],
            timeout_seconds=settings.datex_timeout_seconds,
            max_retries=settings.datex_max_retries,
            pk_to_xy_url=settings.datex_pk_to_xy_url,
            pk_to_xy_timeout_seconds=settings.datex_pk_to_xy_timeout_seconds,
            pk_sample_step_km=settings.datex_pk_sample_step_km,
            pk_sample_budget=settings.datex_pk_sample_budget,
            osrm_route_url=settings.osrm_route_url,
            osrm_timeout_seconds=settings.osrm_timeout_seconds,
            overpass_url=settings.osm_overpass_url,
            overpass_timeout_seconds=min(settings.osm_timeout_seconds, 4),
        )


@dataclass(frozen=True)
class EtrafficConnectorConfig:
    base_url: str
    public_url: str
    filters_via: list[str]
    timeout_seconds: int
    max_retries: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "EtrafficConnectorConfig":
        return cls(
            base_url=settings.etraffic_base_url.rstrip("/"),
            public_url=settings.etraffic_public_url,
            filters_via=[item.strip() for item in settings.etraffic_filters_via.split(",") if item.strip()],
            timeout_seconds=settings.etraffic_timeout_seconds,
            max_retries=settings.etraffic_max_retries,
        )


@dataclass(frozen=True)
class ProteccioCivilConnectorConfig:
    plans_url: str
    timeout_seconds: int
    max_retries: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "ProteccioCivilConnectorConfig":
        return cls(
            plans_url=settings.proteccio_civil_plans_url,
            timeout_seconds=settings.proteccio_civil_timeout_seconds,
            max_retries=settings.proteccio_civil_max_retries,
        )
