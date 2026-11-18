import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "LAaDT-DSS"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # Database Settings
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "laadt_dss")
    
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

    # Redis / Celery
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # MQTT broker (Phase 3)
    MQTT_HOST: str = os.getenv("MQTT_HOST", "emqx")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))

    # Ollama LLM (Phase 3)
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
    OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "60"))
    # LLM backend selector: "ollama" | "mock"
    LLM_BACKEND: str = os.getenv("LLM_BACKEND", "ollama")
    # Provenance guard (GFP/A1) modu: "block" (ihlalde düzelt/blokla) | "log" | "off"
    # G1 ablasyonu bu bayrakla koşulur (guard-on vs guard-off).
    GUARD_MODE: str = os.getenv("GUARD_MODE", "block")

    # Bina ayak izi (footprint) sağlayıcısı: "stub" | "pmtiles" | "microsoft" | "vida"
    FOOTPRINT_PROVIDER: str = os.getenv("FOOTPRINT_PROVIDER", "stub")
    FOOTPRINT_PARQUET_URI: str = os.getenv("FOOTPRINT_PARQUET_URI", "")
    # PMTiles kaynağı: YEREL dosya yolu VEYA http(s):// URL (byte-range okunur).
    # Varsayılan: VIDA global Google+Microsoft binaları (Source Cooperative, herkese açık,
    # range-request destekli, global). Daha hızlı yerel okuma için container içi mount yolu ver.
    PMTILES_PATH: str = os.getenv(
        "PMTILES_PATH",
        "https://data.source.coop/vida/google-microsoft-open-buildings/pmtiles/go_ms_building_footprints.pmtiles",
    )

    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()
