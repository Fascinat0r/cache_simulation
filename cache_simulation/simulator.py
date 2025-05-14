# cache_simulation/simulator.py

import simpy

from cache_simulation.cache import Cache
from cache_simulation.client import Client
from cache_simulation.config import Settings
from cache_simulation.external_source import ExternalSource
from cache_simulation.logger import get_logger, setup_logging
from cache_simulation.metrics import MetricsCollector
from cache_simulation.strategies.fixed_ttl import FixedTTLStrategy

# from cache_simulation.strategies.adaptive_ttl import AdaptiveTTLStrategy
# from cache_simulation.strategies.hybrid import HybridStrategy

logger = get_logger(__name__)


class Simulator:
    """
    Фасад для настройки и запуска DES-симуляции.
    Использует единый Config для всех параметров.
    """

    def __init__(self, settings: Settings):
        self.config = settings

        # Логирование
        setup_logging(settings)
        logger.info("Simulator initialized with config")

        # Среда SimPy
        self.env = simpy.Environment()

        # Коллектор метрик
        self.metrics = MetricsCollector()

        # Внешний источник
        es = settings.external_source
        self.source = ExternalSource(
            env=self.env,
            min_service=es.min_service,
            max_service=es.max_service,
            update_rate=es.update_rate
        )

        # Стратегия кеша
        cache_cfg = settings.cache
        if cache_cfg.strategy == "fixed_ttl":
            strategy = FixedTTLStrategy(ttl=cache_cfg.fixed_ttl.ttl)
        # elif cache_cfg.strategy == "adaptive_ttl":
        #     strategy = AdaptiveTTLStrategy(theta=cache_cfg.adaptive_ttl.theta)
        # elif cache_cfg.strategy == "hybrid":
        #     strategy = HybridStrategy(k=cache_cfg.hybrid.k, delta=cache_cfg.hybrid.delta)
        else:
            raise ValueError(f"Unknown cache strategy: {cache_cfg.strategy}")

        # Кеш
        self.cache = Cache(
            env=self.env,
            source_request_fn=self.source.request,
            strategy=strategy,
            metrics=self.metrics
        )

        # Генератор клиентов
        sim_cfg = settings.simulator
        self.client_gen = Client(
            env=self.env,
            cache_request_fn=self.cache.request,
            arrival_rate=sim_cfg.arrival_rate,
            key_generator=lambda: None,
            start_time=sim_cfg.start_time,
            name_prefix=sim_cfg.client_prefix
        )

    def run(self):
        """
        Запуск симуляции и экспорт метрик.
        """
        sim_time = self.config.simulator.sim_time
        logger.info(f"Starting simulation until t={sim_time}")
        self.env.run(until=sim_time)
        self.metrics.collect_from(self)
        self.metrics.export(self.config.output.path)
        logger.info("Simulation completed")

        # Сбор и экспорт метрик
        self.metrics.collect_from(self)
        output_path = getattr(self.config, "output", {}).get("path", None)
        if output_path:
            self.metrics.export(output_path)
        else:
            logger.warning("No output path configured; skipping export")
