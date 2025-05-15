# cache_simulation/cache.py

from typing import Any, Dict, Callable

import simpy

from cache_simulation.logger import get_logger
from cache_simulation.metrics import MetricsCollector
from cache_simulation.strategies.base import CacheStrategy

logger = get_logger(__name__)


class CacheEntry:
    """
    Запись кеша.
    Attributes:
        value: результат последнего запроса.
        version: версия данных внешнего источника.
        timestamp: время (env.now) последнего обновления.
    """
    __slots__ = ("value", "version", "timestamp")

    def __init__(self, value: Any, version: int, timestamp: float):
        self.value = value
        self.version = version
        self.timestamp = timestamp


class Cache:
    """
    Слой кеширования с инвалидацией по стратегии и сбором метрик.
    При запросе:
      - если запись есть и strategy.is_valid -> HIT
      - иначе -> MISS, запрос к source_request_fn, обновление записи, strategy.on_update
    """

    def __init__(
            self,
            env: simpy.Environment,
            source_request_fn: Callable[[Any], simpy.Event],
            strategy: CacheStrategy,
            metrics: MetricsCollector
    ):
        self.env = env
        self._source_fn = source_request_fn
        self._strategy = strategy
        self._metrics = metrics
        self._store: Dict[Any, CacheEntry] = {}

    def __len__(self):
        return len(self._store)

    def request(self, key: Any):
        def _proc():
            start = self.env.now
            entry = self._store.get(key)

            now = self.env.now
            cache_size = len(self._store)
            if entry and self._strategy.is_valid(entry, now):
                # HIT
                age = now - entry.timestamp
                self._metrics.record_entry_age_on_hit(age)
                self._metrics.record_event(now, "hit", key, cache_size)
                wait = now - start
                logger.debug(f"t={self.env.now:.2f}: CACHE HIT key={key}, wait={wait:.2f}")
                self._strategy.on_access(entry, start)
                self._metrics.record_hit(wait)
                return entry.value, entry.version

            # MISS (или stale)
            if entry:
                age = now - entry.timestamp
                self._metrics.record_entry_age_on_stale(age)
                self._metrics.record_event(now, "stale", key, cache_size)
                logger.debug(f"t={now:.2f}: CACHE STALE key={key}, age={age:.2f}")
                self._metrics.record_stale()

            logger.debug(f"t={self.env.now:.2f}: CACHE MISS key={key}")
            self._metrics.record_source_call()

            value, version = yield from self._call_source(key)
            # до вызова сохраним старую версию (или None)
            old_version = entry.version if entry else None
            value, version = yield from self._call_source(key)

            wait = self.env.now - start
            self._metrics.record_miss(wait)

            # новая или та же версия?

            if old_version is None or version != old_version:
                # действительно обновили данные
                self._metrics.record_cache_update()
            else:
                # промах, но версия не сменилась
                self._metrics.record_redundant_miss()

            entry = CacheEntry(value=value, version=version, timestamp=self.env.now)
            self._store[key] = entry
            logger.info(f"t={self.env.now:.2f}: CACHE UPDATE key={key} -> version={version}")
            self._strategy.on_update(entry, self.env.now)

            return value, version

        return self.env.process(_proc())

    def _call_source(self, key: Any):
        result = yield self._source_fn(key)
        return result
