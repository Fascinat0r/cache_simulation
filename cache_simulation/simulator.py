# cache_simulation/simulator.py

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
from cache_simulation.strategies.hybrid_predictive import HybridPredictiveStrategy

logger = get_logger(__name__)


class Simulator:
    """
    Фасад симулятора: строит окружение, external source, cache с нужной стратегией,
    клиентов и запускает DES.
    """

    def __init__(self, settings: Settings):
        self.cfg = settings
        self.env = simpy.Environment()
        self.metrics = MetricsCollector()

        # фиксируем seed для воспроизводимости
        random.seed(self.cfg.simulator.random_seed)

        # 1) Ресурсы
        self.resources = [
            SimpleResource(f"r-{i + 1}", update_rate=self.cfg.resources.update_rate)
            for i in range(self.cfg.resources.count)
        ]

        # 2) Внешний источник
        es = self.cfg.external_source
        # Если в будущем понадобится циклический update_pattern — можно расширить ExternalSource
        self.source = ExternalSource(
            env=self.env,
            min_service=es.min_service,
            max_service=es.max_service,
            resources=self.resources,
            metrics=self.metrics,
            update_pattern=getattr(es, "update_pattern", "poisson"),
            cycle_period=getattr(es, "cycle_period", None),
            cycle_amplitude=getattr(es, "cycle_amplitude", None),
            peak_phase=getattr(es, "peak_phase", None),
        )

        # 3) Стратегия кеширования
        cache_cfg = self.cfg.cache
        strat_name = cache_cfg.strategy

        if strat_name == "fixed_ttl":
            strategy = FixedTTLStrategy(ttl=cache_cfg.fixed_ttl.ttl)

        elif strat_name == "adaptive_ttl":
            strategy = AdaptiveTTLStrategy(
                env=self.env,
                metrics=self.metrics,
                initial_ttl=cache_cfg.fixed_ttl.ttl,
                theta=cache_cfg.adaptive_ttl.theta,
                recalc_interval=cache_cfg.adaptive_ttl.recalc_interval,
            )

        elif strat_name == "hybrid_predictive":
            # 3.1 базовая (реактивная) часть — адаптивный TTL
            base = AdaptiveTTLStrategy(
                env=self.env,
                metrics=self.metrics,
                initial_ttl=cache_cfg.fixed_ttl.ttl,
                theta=cache_cfg.adaptive_ttl.theta,
                recalc_interval=cache_cfg.adaptive_ttl.recalc_interval,
            )
            # 3.2 полная гибридно-предиктивная
            strategy = HybridPredictiveStrategy(
                env=self.env,
                metrics=self.metrics,
                base_strategy=base,
                history_window=cache_cfg.hybrid.history_window,
                analyze_interval=cache_cfg.hybrid.analyze_interval,
                profile_bin_size=cache_cfg.hybrid.profile_bin_size,
                prefetch_interval=cache_cfg.hybrid.prefetch_interval,
                max_periods=cache_cfg.hybrid.max_periods,
                k=cache_cfg.hybrid.k,
            )
        else:
            raise ValueError(f"Unknown cache.strategy «{strat_name}» in config")

        # 4) Кеш
        self.cache = Cache(
            env=self.env,
            source_request_fn=self.source.request,
            strategy=strategy,
            metrics=self.metrics,
        )

        # 5) Если гибридно-предиктивная — «привязываем» её к каждому ресурсу
        if strat_name == "hybrid_predictive":
            # HybridPredictiveStrategy требует знать cache и ключ
            for res in self.resources:
                strategy.bind_cache(self.cache, res)

        # 6) Клиентский генератор
        self._init_clients()

    def _init_clients(self) -> None:
        scfg = self.cfg.simulator

        # ключ для запроса выбираем случайно из списка ресурсов
        key_fn = lambda _: random.choice(self.resources)

        if scfg.arrival_pattern == "poisson":
            Client(
                env=self.env,
                cache_request_fn=self.cache.request,
                arrival_rate=scfg.arrival_rate,
                start_time=scfg.start_time,
                key_generator=key_fn,
                name_prefix=scfg.client_prefix,
            )
        elif scfg.arrival_pattern == "cyclic":
            CyclicClient(
                env=self.env,
                cache_request_fn=self.cache.request,
                lambda_base=scfg.arrival_rate,
                amplitude=scfg.cyclic_amplitude,
                period=scfg.cyclic_period,
                key_generator=key_fn,
                start_time=scfg.start_time,
                name_prefix=scfg.client_prefix,
            )
        else:
            raise ValueError(f"Unknown simulator.arrival_pattern «{scfg.arrival_pattern}»")

    def run(self) -> None:
        t_end = self.cfg.simulator.sim_time
        logger.info(f"=== Simulation start until t={t_end} ===")

        # Запускаем события до конца
        self.env.run(until=t_end)

        # Собираем итоговые метрики
        self.metrics.collect_from(self)

        # Экспортим результаты
        payload = {
            "settings": self.cfg.dict(),
            "metrics": self.metrics.summary()
        }
        if self.cfg.output and self.cfg.output.path:
            fn = Path(self.cfg.output.path).with_suffix("")
            fn = fn.with_name(f"{fn.stem}_{datetime.now():%Y%m%d_%H%M%S}.json")
            fn.parent.mkdir(parents=True, exist_ok=True)
            with open(fn, "w", encoding="utf-8") as out:
                json.dump(payload, out, indent=2, ensure_ascii=False)
            logger.info(f"[Simulator] Metrics exported to {fn}")
