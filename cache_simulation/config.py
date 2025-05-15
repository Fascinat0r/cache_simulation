# cache_simulation/config.py

import os
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class FileLogConfig(BaseModel):
    path: str
    max_bytes: int = Field(..., alias="max_bytes")
    backup_count: int
    level: str
    fmt: str = Field(..., alias="format")


class ConsoleLogConfig(BaseModel):
    level: str
    fmt: str = Field(..., alias="format")


class LoggingConfig(BaseModel):
    file: FileLogConfig
    console: ConsoleLogConfig
    date_format: str


class SimulatorConfig(BaseModel):
    sim_time: float
    arrival_rate: float
    start_time: float = 0.0
    client_prefix: str = "Client"


class ExternalSourceConfig(BaseModel):
    min_service: float
    max_service: float
    update_rate: float


class ResourcesConfig(BaseModel):
    count: int


class FixedTTLConfig(BaseModel):
    ttl: float


class AdaptiveTTLConfig(BaseModel):
    theta: float


class HybridConfig(BaseModel):
    k: float
    delta: float


class CacheConfig(BaseModel):
    strategy: str
    fixed_ttl: FixedTTLConfig
    adaptive_ttl: AdaptiveTTLConfig
    hybrid: HybridConfig


class OutputConfig(BaseModel):
    path: str


class Settings(BaseModel):
    logging: LoggingConfig
    simulator: SimulatorConfig
    external_source: ExternalSourceConfig
    resources: ResourcesConfig
    cache: CacheConfig
    output: Optional[OutputConfig] = None

    @classmethod
    def load(cls, path: str = None) -> "Settings":
        yaml_path = path or os.getenv("CONFIG_PATH", "config/default.yaml")
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return cls.parse_obj(data)
