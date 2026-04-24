from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file's location (project root) so the app
# loads correctly regardless of which directory uvicorn/pytest is invoked from.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        env_ignore_empty=True,   # don't let empty shell env vars override .env values
        extra="ignore",
    )

    database_url: str
    anthropic_api_key: str = ""
    mapbox_token: str = ""
    mapbox_daily_limit: int = 200
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_access_token: str = ""
    rwgps_api_key: str = ""
    rwgps_auth_token: str = ""
    claude_model: str = "claude-sonnet-4-6"
    # Optional: path to a downloaded SRTM .tif raster for elevation data.
    # Without this, climb_up_m / climb_down_m will be 0 on all edges.
    # Download N37W123.hgt and N38W123.hgt from USGS EarthExplorer, convert to
    # GeoTIFF (gdal_translate), merge with gdal_merge.py, then set this path.
    srtm_raster_path: str = ""


settings = Settings()
