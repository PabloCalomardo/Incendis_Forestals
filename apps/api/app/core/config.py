from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    project_name: str = "wildfire-intelligence-platform"
    environment: str = "development"
    log_level: str = "INFO"
    api_version: str = "0.1.0"
    api_cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql+asyncpg://wildfire:change-me-local@postgres:5432/wildfire"
    redis_url: str = "redis://redis:6379/0"
    minio_endpoint: str = "http://minio:9000"
    minio_bucket_raw: str = "raw-ingestion"
    s3_access_key_id: str = Field(default="", repr=False)
    s3_secret_access_key: str = Field(default="", repr=False)
    s3_region: str = "eu-west-1"
    internal_api_token: str = Field(default="change-me-local-internal-token", repr=False)

    firms_map_key: str = Field(default="", repr=False)
    firms_source: str = "VIIRS_NOAA20_NRT"
    firms_area_spain: str = "-10.0,35.5,4.5,44.5"
    firms_day_range: int = 1
    firms_base_url: str = "https://firms.modaps.eosdis.nasa.gov"
    firms_timeout_seconds: int = 30
    firms_max_retries: int = 3

    aemet_api_key: str = Field(default="", repr=False)
    aemet_base_url: str = "https://opendata.aemet.es/opendata"
    aemet_timeout_seconds: int = 30
    aemet_max_retries: int = 3
    aemet_forecast_municipalities: str = "28079"
    aemet_forecast_locations_json: str = '{"28079":{"name":"Madrid","latitude":40.4168,"longitude":-3.7038}}'

    ign_wfs_base_url: str = "https://api-features.idee.es"
    ign_transport_typename: str = "roadlink"
    ign_area_bbox: str = "-10.0,35.5,4.5,44.5"
    ign_feature_limit: int = 1000
    ign_max_features: int = 250000
    ign_max_pages_per_tile: int = 3
    ign_tile_size_degrees: float = 1.0
    ign_target_datex_restrictions: bool = True
    ign_timeout_seconds: int = 30
    ign_max_retries: int = 3

    osm_overpass_url: str = "https://overpass-api.de/api/interpreter"
    osm_area_bbox: str = "-3.75,40.38,-3.65,40.45"
    osm_timeout_seconds: int = 60
    osm_max_retries: int = 2
    osm_feature_limit: int = 100
    osrm_route_url: str = "https://router.project-osrm.org/route/v1/driving"
    osrm_timeout_seconds: int = 4

    datex_feed_urls: str = (
        "https://nap.dgt.es/dataset/77be854a-6911-47dc-ba4c-b13067a50552/"
        "resource/1d36ea74-593d-4e45-acfa-fb8db5a460bc/download/datex2_v37.xml,"
        "https://infocar.dgt.es/datex2/sct/SituationPublication/all/content.xml,"
        "https://infocar.dgt.es/datex2/dt-gv/SituationPublication/all/content.xml"
    )
    datex_timeout_seconds: int = 30
    datex_max_retries: int = 3
    datex_pk_to_xy_url: str = "https://gis.dgt.es/server/rest/services/Geoprocesos/PKaXYcgt/GPServer/PKaXY_CGT/execute"
    datex_pk_to_xy_timeout_seconds: int = 8
    datex_pk_sample_step_km: float = 4.0
    datex_pk_sample_budget: int = 80
    etraffic_base_url: str = "https://etraffic.dgt.es/etrafficWEB/api"
    etraffic_public_url: str = "https://etraffic.dgt.es/etrafficWEB/"
    etraffic_filters_via: str = (
        "Carreteras cortadas,Tráfico lento,Circulación restringida,Desvíos y embolsamientos,Otras vialidades"
    )
    etraffic_timeout_seconds: int = 30
    etraffic_max_retries: int = 3
    mobility_map_url: str = "http://mapamovilidad.dgt.es/"

    proteccio_civil_plans_url: str = (
        "https://analisi.transparenciacatalunya.cat/api/v3/views/wj9c-j6vf/query.json?accessType=DOWNLOAD"
    )
    proteccio_civil_timeout_seconds: int = 30
    proteccio_civil_max_retries: int = 3

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
