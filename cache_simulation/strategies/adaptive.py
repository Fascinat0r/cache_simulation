"""
Адаптивная стратегия инвалидации кеша.

Алгоритм‑идея
-------------
* В течение фиксированного окна собираем статистику:
    - n_requests  – сколько раз читали запись из кеша;
    - n_misses    – сколько раз пришлось ходить во внешний источник
                    (т.е. пришёл `on_update`);
* После истечения окна ∆t вычисляем оценки интенсивностей:
    λ̂_u   = n_requests / ∆t      – поток обращений пользователей;
    λ̂_upd = n_misses   / ∆t      – фактическая «частота изменений» ресурса
                                    (раз обновили – значит, предыдущая версия устарела);
* Новый TTL берём по формуле обратной пропорциональности:

        T_next = θ / λ̂_upd ,                    (1)

  где θ – коэффициент сглаживания (настраивается из конфига).
* TTL ограничиваем диапазоном [min_ttl, max_ttl] во избежание крайностей.
* Значение T хранится в атрибуте `self.ttl` – его читает `Cache.is_valid`.

Внутренняя реализация
---------------------
* Стратегия получает `env` – доступ к времени SimPy и возможностям планирования.
* В конструкторе порождаем фоновый процесс `_recalc_loop`, который будитcя
  каждые `recalc_interval` сим‑единиц; можно задать интервал через конфиг.
* Все события TTL‑смен фиксируются в `MetricsCollector` (метод `record_ttl_change`)
  – это позволит потом визуализировать эволюцию алгоритма.
"""

from __future__ import annotations

import simpy

from cache_simulation.cache import CacheEntry
from cache_simulation.logger import get_logger
from cache_simulation.metrics import MetricsCollector
from cache_simulation.strategies.base import CacheStrategy

logger = get_logger(__name__)


class AdaptiveTTLStrategy(CacheStrategy):
    """
    Адаптивный TTL по формуле (1).

    Parameters
    ----------
    env : simpy.Environment
        Симулятор, необходим для планирования фонового пересчёта.
    metrics : MetricsCollector
        Сборщик метрик, чтобы логировать эволюцию TTL.
    initial_ttl : float
        Стартовое значение T (если λ̂_upd ещё неизвестна).
    theta : float
        Коэффициент из (1) ― задаёт «запас» времени жизни.
    recalc_interval : float, default 100.0
        Как часто (в сим‑времени) пересчитывать TTL.
    min_ttl / max_ttl : float
        Жёсткие границы допустимого TTL.
    """

    def __init__(
            self,
            env: simpy.Environment,
            metrics: MetricsCollector,
            *,
            initial_ttl: float = 60.0,
            theta: float = 1.0,
            recalc_interval: float = 100.0,
            min_ttl: float = 1.0,
            max_ttl: float = 3600.0,
    ) -> None:
        if theta <= 0:
            raise ValueError("theta must be positive")

        self.env = env
        self.metrics = metrics

        # Параметры алгоритма
        self._theta = theta
        self._recalc_interval = recalc_interval
        self._min_ttl = min_ttl
        self._max_ttl = max_ttl

        # Текущее значение TTL
        self.ttl: float = initial_ttl

        # Счётчики внутри скользящего окна
        self._reset_window(now=env.now)

        # Фоновый процесс регулярного пересчёта
        env.process(self._recalc_loop())

        logger.info(
            "AdaptiveTTLStrategy initialized: "
            f"initial_ttl={initial_ttl}, θ={theta}, interval={recalc_interval}"
        )

    # ------------------------------------------------------------------ #
    #   Интерфейс CacheStrategy                                           #
    # ------------------------------------------------------------------ #
    def is_valid(self, entry: CacheEntry, now: float) -> bool:
        """Запись валидна, пока её возраст не превысил текущий TTL."""
        age = now - entry.timestamp
        valid = age <= self.ttl
        logger.debug(
            f"[AdaptiveTTL] is_valid? age={age:.3f}, ttl={self.ttl:.3f}, valid={valid}"
        )
        return valid

    def on_access(self, entry: CacheEntry, now: float) -> None:
        """Любое обращение к кешу увеличивает число заявок n_requests."""
        self._n_requests += 1

    def on_update(self, entry: CacheEntry, now: float) -> None:
        """
        Получили свежие данные из источника → это признак того, что
        прежняя версия устарела → фиксируем miss.
        """
        self._n_requests += 1
        self._n_misses += 1

    # ------------------------------------------------------------------ #
    #   Внутренняя логика                                                #
    # ------------------------------------------------------------------ #
    def _reset_window(self, now: float) -> None:
        """Начинаем новое окно статистики."""
        self._t_window_start = now
        self._n_requests = 0
        self._n_misses = 0

    def _recalc_loop(self):
        """Периодически пересчитывает TTL (SimPy‑процесс)."""
        while True:
            yield self.env.timeout(self._recalc_interval)
            self._recalculate_ttl(self.env.now)

    def _recalculate_ttl(self, now: float) -> None:
        """Основная формула пересчёта + логирование."""
        window = now - self._t_window_start or 1e-9  # защита от деления на ноль
        lam_u = self._n_requests / window
        lam_upd = self._n_misses / window

        if lam_upd > 0:
            ttl_new = self._theta / lam_upd
        else:  # не наблюдали обновлений
            ttl_new = self._max_ttl

        ttl_new = max(self._min_ttl, min(self._max_ttl, ttl_new))

        logger.info(
            f"[AdaptiveTTL] t={now:.2f}: λ̂_u={lam_u:.3f}, λ̂_upd={lam_upd:.3f} → "
            f"TTL {self.ttl:.2f} → {ttl_new:.2f}"
        )

        # фиксируем метрику и применяем новое значение
        self.metrics.record_ttl_change(now, ttl_new)
        self.ttl = ttl_new

        # начинаем новое окно
        self._reset_window(now)
