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
      - если запись есть и strategy.is_valid -> HIT (с небольшой задержкой)
      - иначе -> MISS (или STALE), консолидированный fetch к source_request_fn,
        обновление записи, и уведомление всех ожидающих.
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

        # Для того, чтобы отличать первичный stale от повторных
        self._stale_seen = set()
        # Для консолидации одновременных запросов на один ключ
        self._inflight: Dict[Any, simpy.events.Event] = {}

        # Задержка на попадание в кэш (несравнимо малая)
        self._hit_delay = 1e-3

    def __len__(self):
        return len(self._store)

    def request(self, key: Any):
        """
        Процесс одного клиентского запроса к кэшу.
        Возвращает (value, version).
        """

        def _proc():
            start = self.env.now
            entry = self._store.get(key)
            now = start
            cache_size = len(self._store)

            # --- HIT ---
            if entry and self._strategy.is_valid(entry, now):
                age = now - entry.timestamp

                # Разделяем корректный и некорректный hit
                if entry.version == key.version:
                    # корректный hit
                    self._metrics.record_entry_age_on_hit(age)
                    self._metrics.record_correct_hit(now - start)
                    call_type = "hit_correct"
                    self._metrics.record_event(now, call_type, key, cache_size)
                    logger.debug(
                        f"t={now:.2f}: CACHE HIT_CORRECT key={key} v={entry.version}"
                    )
                else:
                    # неправильный hit (старые данные)
                    self._metrics.record_entry_age_on_hit(age)
                    self._metrics.record_incorrect_hit(now - start)
                    call_type = "hit_incorrect"
                    self._metrics.record_event(now, call_type, key, cache_size)
                    logger.debug(
                        f"t={now:.2f}: CACHE HIT_INCORRECT key={key} cached={entry.version} "
                        f"actual={key.version}"
                    )

                self._strategy.on_access(entry, now)

                # Добавляем небольшую задержку на чтение из кэша
                yield self.env.timeout(self._hit_delay)

                finish = self.env.now
                self._metrics.record_cache_call(key, start, finish, call_type, entry.version)
                return entry.value, entry.version

            # --- STALE or MISS ---
            if entry:
                age = now - entry.timestamp
                if key not in self._stale_seen:
                    # первый stale
                    self._stale_seen.add(key)
                    self._metrics.record_entry_age_on_stale(age)
                    self._metrics.record_stale_initial()
                    self._metrics.record_event(now, "stale_initial", key, cache_size)
                    logger.debug(f"t={now:.2f}: CACHE STALE_INITIAL key={key}, age={age:.2f}")
                else:
                    # повторный stale
                    self._metrics.record_entry_age_on_stale(age)
                    self._metrics.record_stale_repeat()
                    self._metrics.record_event(now, "stale_repeat", key, cache_size)
                    logger.debug(f"t={now:.2f}: CACHE STALE_REPEAT key={key}, age={age:.2f}")

            # логируем сам факт miss
            self._metrics.record_event(now, "miss", key, cache_size)
            logger.debug(f"t={now:.2f}: CACHE MISS key={key}")

            # --- Консолидация запросов на внешний источник ---
            if key in self._inflight:
                # Ждём завершения уже запущенного fetch
                fetch_evt = self._inflight[key]
            else:
                # Запускаем один fetch и сохраняем его
                old_version = entry.version if entry else None
                fetch_evt = self.env.process(self._do_fetch(key, old_version))
                self._inflight[key] = fetch_evt

            # Ожидаем результата fetch-а
            value, version = yield fetch_evt

            # Первый завершивший очистит inflight
            if self._inflight.get(key) is fetch_evt:
                del self._inflight[key]

            # Учитываем время ожидания и записываем cache_call
            finish = self.env.now
            wait = finish - start
            self._metrics.record_miss(wait)
            self._metrics.record_cache_call(key, start, finish, "miss", version)

            return value, version

        return self.env.process(_proc())

    def _do_fetch(self, key: Any, old_version: Any):
        """
        Фоновый процесс единого fetch-а для данного ключа.
        """
        # Запрашиваем у внешнего источника
        value, version = yield from self._call_source(key)

        finish = self.env.now
        # Обновляем метрики по апдейтам
        if old_version is None or version != old_version:
            self._metrics.record_cache_update()
        else:
            self._metrics.record_redundant_miss()

        # Перезаписываем CacheEntry
        entry = CacheEntry(value=value, version=version, timestamp=finish)
        self._store[key] = entry
        # Сбрасываем stale-флаг
        self._stale_seen.discard(key)

        logger.info(f"t={finish:.2f}: CACHE UPDATE key={key} -> version={version}")
        self._strategy.on_update(entry, finish)

        return value, version

    def _call_source(self, key: Any):
        """
        Обёртка над симуляцией внешнего запроса.
        """
        result = yield self._source_fn(key)
        return result
