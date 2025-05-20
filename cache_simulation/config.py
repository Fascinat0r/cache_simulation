"""
Pydantic-конфиг проекта (расширен поддержкой циклического клиента).
"""

import os
from typing import Optional, Literal

import yaml
from pydantic import BaseModel, Field


# ---------- логирование ----------
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


# ---------- симулятор ----------
class SimulatorConfig(BaseModel):
    random_seed: int
    sim_time: float
    arrival_pattern: Literal["poisson", "cyclic"] = "poisson"
    arrival_rate: float
    cyclic_amplitude: float = 0.5
    cyclic_period: float = 86_400.0
    start_time: float = 0.0
    client_prefix: str = "Client"


# ---------- внешний источник ----------
class ExternalSourceConfig(BaseModel):
    min_service: float
    max_service: float
    update_pattern: Literal["poisson", "cyclic"] = "poisson"
    cycle_period: Optional[float] = None
    cycle_amplitude: Optional[float] = None
    peak_phase: Optional[float] = None


# ---------- ресурсы ----------
class ResourcesConfig(BaseModel):
    count: int
    update_rate: float


# ---------- кеш-стратегии ----------
class FixedTTLConfig(BaseModel):
    ttl: float


class AdaptiveTTLConfig(BaseModel):
    theta: float
    recalc_interval: float


class HybridConfig(BaseModel):
    # реактивная часть (адаптивный TTL)
    # предиктивная часть:
    history_window: float  # за какой интервал собираем историю
    analyze_interval: float  # как часто анализировать (FFT)
    profile_bin_size: float  # размер бина для профиля (сек)
    prefetch_interval: float  # интервал фоновой префетч-логики (сек)
    max_periods: int = 3  # сколько самых сильных периодов брать
    k: float  # коэффициент для P_pred


class CacheConfig(BaseModel):
    strategy: Literal["fixed_ttl", "adaptive_ttl", "hybrid_predictive"]
    fixed_ttl: FixedTTLConfig
    adaptive_ttl: AdaptiveTTLConfig
    hybrid: HybridConfig


# ---------- вывод ----------
class OutputConfig(BaseModel):
    path: str


class Settings(BaseModel):
    logging: LoggingConfig
    simulator: SimulatorConfig
    external_source: ExternalSourceConfig
    resources: ResourcesConfig
    cache: CacheConfig
    output: Optional[OutputConfig] = None

    # загрузка из YAML
    @classmethod
    def load(cls, path: str | None = None) -> "Settings":
        yaml_path = path or os.getenv("CONFIG_PATH", "config/default.yaml")
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.parse_obj(data)
