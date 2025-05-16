# Полный обновлённый модуль: добавлена поддержка adaptive_ttl
import json
import random
from datetime import datetime
from pathlib import Path

import simpy

from cache_simulation.cache import Cache
from cache_simulation.client import Client
from cache_simulation.config import Settings
from cache_simulation.external_source import ExternalSource
from cache_simulation.logger import get_logger
from cache_simulation.metrics import MetricsCollector
from cache_simulation.resources.simple import SimpleResource
from cache_simulation.strategies.fixed_ttl import FixedTTLStrategy
from cache_simulation.strategies.adaptive import AdaptiveTTLStrategy  # ← новинка

logger = get_logger(__name__)


class Simulator:
    """Основной фасад: собирает все компоненты и запускает DES‑модель."""

    def __init__(self, settings: Settings):
        self.config = settings
        self.env = simpy.Environment()
        self.metrics = MetricsCollector()

        # детерминируемость
        random.seed(settings.simulator.random_seed)

        # ---------- ресурсы ----------
        self.resources = [
            SimpleResource(f"r-{i + 1}", update_rate=settings.resources.update_rate)
            for i in range(settings.resources.count)
        ]

        # ---------- внешний источник ----------
        es = settings.external_source
        self.source = ExternalSource(
            env=self.env,
            min_service=es.min_service,
            max_service=es.max_service,
            resources=self.resources,
            metrics=self.metrics,
        )

        # ---------- стратегия кеша ----------
        cache_cfg = settings.cache
        if cache_cfg.strategy == "fixed_ttl":
            strategy = FixedTTLStrategy(cache_cfg.fixed_ttl.ttl)
        elif cache_cfg.strategy == "adaptive_ttl":
            strategy = AdaptiveTTLStrategy(
                env=self.env,
                metrics=self.metrics,
                initial_ttl=cache_cfg.fixed_ttl.ttl,  # reuse поле ttl как старт
                theta=cache_cfg.adaptive_ttl.theta,
                recalc_interval=100.0,                # можно вынести в конфиг
            )
        else:
            raise ValueError(f"Unknown strategy {cache_cfg.strategy}")

        # ---------- кеш ----------
        self.cache = Cache(
            env=self.env,
            source_request_fn=self.source.request,
            strategy=strategy,
            metrics=self.metrics,
        )

        # ---------- генератор клиентов ----------
        sim_cfg = settings.simulator
        self.client_gen = Client(
            env=self.env,
            cache_request_fn=self.cache.request,
            arrival_rate=sim_cfg.arrival_rate,
            start_time=sim_cfg.start_time,
            key_generator=lambda _: random.choice(self.resources),
            name_prefix=sim_cfg.client_prefix,
        )

    # ------------------------------------------------------------------ #
    #   Запуск и экспорт                                                 #
    # ------------------------------------------------------------------ #
    def run(self):
        t_end = self.config.simulator.sim_time
        logger.info(f"Running until t={t_end}")
        self.env.run(until=t_end)

        # собираем финальные метрики
        self.metrics.collect_from(self)

        payload = {
            "settings": self.config.dict(),
            "metrics": self.metrics.summary(),
        }

        out = self.config.output
        if out and out.path:
            fn = Path(out.path)
            fn = fn.with_name(f"{fn.stem}_{datetime.now():%Y%m%d_%H%M%S}{fn.suffix}")
            fn.parent.mkdir(parents=True, exist_ok=True)
            with open(fn.with_suffix(".json"), "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            logger.info(f"Exported results to {fn}")
