# cache_simulation/cache.py

from typing import Any, Dict, Callable, Optional

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

        # Основное хранилище и вспомогательные структуры
        self._store: Dict[Any, CacheEntry] = {}
        self._stale_seen: set = set()
        self._inflight: Dict[Any, simpy.events.Event] = {}

        # Константы
        self._hit_delay = 1e-3

    def __len__(self) -> int:
        return len(self._store)

    def request(self, key: Any, *, is_prefetch: bool = False):
        """
        Возвращает процесс SimPy, который выполнит запрос:
        - при hit: отдаст результат с минимальной задержкой,
        - при miss/stale или prefetch: консолидирует fetch к источнику.
        """
        return self.env.process(self._handle_request(key, is_prefetch))

    # ------------------------------------------------------------------------- #
    #                               Основной процесс                           #
    # ------------------------------------------------------------------------- #
    def _handle_request(self, key: Any, is_prefetch: bool):
        start = self.env.now
        entry = self._store.get(key)
        cache_size = len(self._store)

        # 1) Предиктивный prefetch — сразу в MISS-ветку
        if is_prefetch:
            self._metrics.record_event(start, "prefetch_attempt", key, cache_size)
        else:
            # 2) Попытка HIT
            if entry and self._strategy.is_valid(entry, start):
                return (yield from self._serve_hit(entry, key, start, cache_size))

            # 3) Отметка stale-состояния перед MISS
            if entry:
                self._mark_stale(entry, key, start, cache_size)

            # 4) Нативный MISS
            self._metrics.record_event(start, "miss", key, cache_size)
            logger.debug(f"t={start:.2f}: CACHE MISS key={key}")

        # 5) Консолидация и выполнение fetch-а
        value, version = yield from self._execute_fetch(key, entry, start)

        return value, version

    # ------------------------------------------------------------------------- #
    #                               Обслуживание HIT                           #
    # ------------------------------------------------------------------------- #
    def _serve_hit(self, entry: CacheEntry, key: Any, start: float, cache_size: int):
        """
        Обработать корректный или некорректный hit,
        записать метрики, выполнить лёгкую задержку и вернуть результат.
        """
        now = self.env.now
        age = now - entry.timestamp

        if entry.version == key.version:
            self._metrics.record_entry_age_on_hit(age)
            self._metrics.record_correct_hit(now - start)
            call_type = "hit_correct"
            logger.debug(f"t={now:.2f}: CACHE HIT_CORRECT key={key} v={entry.version}")
        else:
            self._metrics.record_entry_age_on_hit(age)
            self._metrics.record_incorrect_hit(now - start)
            call_type = "hit_incorrect"
            logger.debug(
                f"t={now:.2f}: CACHE HIT_INCORRECT key={key} "
                f"cached={entry.version} actual={key.version}"
            )

        self._metrics.record_event(now, call_type, key, cache_size)
        self._strategy.on_access(entry, now)

        # небольшая симуляционная задержка на чтение
        yield self.env.timeout(self._hit_delay)

        finish = self.env.now
        self._metrics.record_cache_call(key, start, finish, call_type, entry.version)
        return entry.value, entry.version

    # ------------------------------------------------------------------------- #
    #                              Отметка STALE                                #
    # ------------------------------------------------------------------------- #
    def _mark_stale(self, entry: CacheEntry, key: Any, now: float, cache_size: int) -> None:
        """
        Зарегистрировать первое и последующие stale-состояния записи.
        """
        age = now - entry.timestamp
        if key not in self._stale_seen:
            self._stale_seen.add(key)
            self._metrics.record_entry_age_on_stale(age)
            self._metrics.record_stale_initial()
            event = "stale_initial"
            logger.debug(f"t={now:.2f}: CACHE STALE_INITIAL key={key}, age={age:.2f}")
        else:
            self._metrics.record_entry_age_on_stale(age)
            self._metrics.record_stale_repeat()
            event = "stale_repeat"
            logger.debug(f"t={now:.2f}: CACHE STALE_REPEAT key={key}, age={age:.2f}")

        self._metrics.record_event(now, event, key, cache_size)

    # ------------------------------------------------------------------------- #
    #                        Консолидация и fetch‐логику                       #
    # ------------------------------------------------------------------------- #
    def _execute_fetch(self, key: Any, entry: Optional[CacheEntry], start: float):
        """
        Гарантируем один _do_fetch на ключ в любой момент,
        ждём его завершения и финализируем метрики.
        """
        # 1) Получаем или создаём inflight-событие
        if key in self._inflight:
            fetch_evt = self._inflight[key]
        else:
            old_ver = entry.version if entry else None
            fetch_evt = self.env.process(self._do_fetch(key, old_ver))
            self._inflight[key] = fetch_evt

        # 2) Ждём результат
        value, version = yield fetch_evt

        # 3) Убираем из inflight первым завершившимся
        if self._inflight.get(key) is fetch_evt:
            del self._inflight[key]

        # 4) Запись метрик miss и cache_call
        finish = self.env.now
        self._metrics.record_miss(finish - start)
        self._metrics.record_cache_call(key, start, finish, "miss", version)

        return value, version

    # ------------------------------------------------------------------------- #
    #                         Непосредственный запрос к источнику               #
    # ------------------------------------------------------------------------- #
    def _do_fetch(self, key: Any, old_version: Optional[int]):
        """
        Фоновый процесс единственного fetch-а для данного ключа:
        1) вызываем внешний источник,
        2) обновляем store и stale-флаги,
        3) логируем и уведомляем стратегию.
        """
        # 1) Запрос в «чёрный ящик»
        value, version = yield from self._call_source(key)

        now = self.env.now
        # 2) Метрики по обновлениям
        if old_version is None or version != old_version:
            self._metrics.record_cache_update()
        else:
            self._metrics.record_redundant_miss()

        # 3) Обновляем запись
        self._store[key] = CacheEntry(value, version, now)
        self._stale_seen.discard(key)

        logger.info(f"t={now:.2f}: CACHE UPDATE key={key} -> version={version}")
        self._strategy.on_update(self._store[key], now)

        return value, version

    # ------------------------------------------------------------------------- #
    #                        Обёртка над внешним запросом                       #
    # ------------------------------------------------------------------------- #
    def _call_source(self, key: Any):
        """
        Делегируем fetch «чёрному ящику» — просто yield из SimPy-процесса.
        """
        result = yield self._source_fn(key)
        return result
