# cache_simulation/simulator.py
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
from cache_simulation.resource import Resource
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
            update_rate=es.update_rate,
            metrics=self.metrics
        )

        res_cfg = settings.resources
        self.resources = [
            Resource(f"r-{i + 1}") for i in range(res_cfg.count)
        ]

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
            start_time=sim_cfg.start_time,
            key_generator=lambda _: random.choice(self.resources),
            name_prefix=sim_cfg.client_prefix
        )

    def run(self):
        """
        Запуск симуляции и экспорт единого JSON-файла с настройками и результатами.
        """
        # 1. Запускаем модель
        sim_time = self.config.simulator.sim_time
        logger.info(f"Starting simulation until t={sim_time}")
        self.env.run(until=sim_time)

        # 2. Собираем метрики
        self.metrics.collect_from(self)
        metrics_summary = self.metrics.summary()

        # 3. Формируем единый словарь
        # settings: исходные параметры (Pydantic → dict()),
        # metrics: агрегированные результаты
        payload = {
            "settings": self.config.dict(),
            "metrics": metrics_summary
        }

        # 4. Сохраняем только JSON
        output_cfg = getattr(self.config, "output", None)

        if not output_cfg:
            logger.warning("No output.path in config; skipping export")
            return

        p = Path(output_cfg.path)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        p = p.with_name(f"{p.stem}_{ts}{p.suffix}")
        p.parent.mkdir(parents=True, exist_ok=True)
        json_path = p.with_suffix(".json")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.info(f"Simulation settings and metrics exported to {json_path}")
