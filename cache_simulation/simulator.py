"""
Фасад симулятора: создаёт окружение, клиентов, кеш, источник и запускает DES.
"""

import json
import random
from datetime import datetime
from pathlib import Path

import simpy

from cache_simulation.cache import Cache
from cache_simulation.client import Client, CyclicClient
from cache_simulation.config import Settings
from cache_simulation.external_source import ExternalSource
from cache_simulation.logger import get_logger
from cache_simulation.metrics import MetricsCollector
from cache_simulation.resources.simple import SimpleResource
from cache_simulation.strategies.adaptive import AdaptiveTTLStrategy
from cache_simulation.strategies.fixed_ttl import FixedTTLStrategy

logger = get_logger(__name__)


class Simulator:
    def __init__(self, settings: Settings):
        self.cfg = settings
        self.env = simpy.Environment()
        self.metrics = MetricsCollector()

        random.seed(self.cfg.simulator.random_seed)

        # ---------- ресурсы ----------
        self.resources = [
            SimpleResource(f"r-{i + 1}", update_rate=self.cfg.resources.update_rate)
            for i in range(self.cfg.resources.count)
        ]

        # ---------- внешний источник ----------
        es = self.cfg.external_source
        self.source = ExternalSource(
            self.env, es.min_service, es.max_service, self.resources, self.metrics
        )

        # ---------- стратегия кеширования ----------
        cache_cfg = self.cfg.cache
        if cache_cfg.strategy == "fixed_ttl":
            strategy = FixedTTLStrategy(cache_cfg.fixed_ttl.ttl)
        elif cache_cfg.strategy == "adaptive_ttl":
            strategy = AdaptiveTTLStrategy(
                env=self.env,
                metrics=self.metrics,
                initial_ttl=cache_cfg.fixed_ttl.ttl,
                theta=cache_cfg.adaptive_ttl.theta,
                recalc_interval=cache_cfg.adaptive_ttl.recalc_interval,
            )
        else:
            raise ValueError(f"Unknown strategy {cache_cfg.strategy}")

        self.cache = Cache(
            env=self.env,
            source_request_fn=self.source.request,
            strategy=strategy,
            metrics=self.metrics,
        )

        # ---------- генератор клиентов ----------
        self._init_clients()

    # ------------------------------------------------------------------ #
    def _init_clients(self):
        scfg = self.cfg.simulator
        if scfg.arrival_pattern == "poisson":
            Client(
                env=self.env,
                cache_request_fn=self.cache.request,
                arrival_rate=scfg.arrival_rate,
                start_time=scfg.start_time,
                key_generator=lambda _: random.choice(self.resources),
                name_prefix=scfg.client_prefix,
            )
        elif scfg.arrival_pattern == "cyclic":
            CyclicClient(
                env=self.env,
                cache_request_fn=self.cache.request,
                lambda_base=scfg.arrival_rate,
                amplitude=scfg.cyclic_amplitude,
                period=scfg.cyclic_period,
                start_time=scfg.start_time,
                key_generator=lambda _: random.choice(self.resources),
                name_prefix=scfg.client_prefix,
            )
        else:
            raise ValueError(f"Unknown arrival_pattern {scfg.arrival_pattern}")

    # ------------------------------------------------------------------ #
    def run(self):
        t_end = self.cfg.simulator.sim_time
        logger.info(f"=== Simulation start, until t={t_end} ===")
        self.env.run(until=t_end)

        self.metrics.collect_from(self)

        payload = {"settings": self.cfg.dict(), "metrics": self.metrics.summary()}
        if self.cfg.output and self.cfg.output.path:
            fn = Path(self.cfg.output.path).with_suffix("")
            fn = fn.with_name(f"{fn.stem}_{datetime.now():%Y%m%d_%H%M%S}.json")
            fn.parent.mkdir(parents=True, exist_ok=True)
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            logger.info(f"Metrics exported to {fn}")
