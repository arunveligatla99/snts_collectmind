"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    oauth2_issuer_url: str = Field(default="http://mock-issuer:8088")
    oauth2_audience: str = Field(default="collectmind-api")
    oauth2_jwks_cache_ttl_seconds: int = Field(default=300)
    oauth2_clock_skew_seconds: int = Field(default=60)

    postgres_dsn: str = Field(default="postgresql://collectmind:localdev@postgres-timescale:5432/collectmind")
    redis_url: str = Field(default="redis://redis:6379/0")
    kafka_bootstrap_servers: str = Field(default="kafka:9092")

    otlp_endpoint: str = Field(default="http://tempo:4317")
    log_level: str = Field(default="INFO")

    time_acceleration_factor: float = Field(default=1.0)

    slm_profile: str = Field(default="cpu")

    service_name: str = Field(default="collectmind-orchestration-api")

    # Feature 002: operator-issuer for the break-glass surface (ADR-0007 Part 4).
    # Distinct issuer + audience from the tenant-issuer; verified by the same
    # PyJWT + JWKS pipeline parameterized over issuer URL + audience.
    operator_issuer_url: str = Field(default="http://operator-issuer:8088")
    operator_issuer_audience: str = Field(default="collectmind-operator")


def load_settings() -> Settings:
    return Settings()
