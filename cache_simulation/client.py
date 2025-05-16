"""
Генераторы клиентских запросов.

* Client          – прежний «стационарный» (постоянная λ или собственная функция
                    inter-arrival);
* CyclicClient    – новый класс с циклической (временнозависимой) интенсивностью
                    λ(t) = λ_base · (1 + A·sin(2π t / P)).
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable, Optional

import simpy

from cache_simulation.logger import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
#   БАЗОВЫЙ КЛАСС (как был)                                                   #
# --------------------------------------------------------------------------- #
class Client:
    """
    Генератор запросов с постоянной интенсивностью или полноценной функцией
    inter-arrival (оставляем без изменений, кроме мелких правок typing).
    """

    def __init__(
            self,
            env: simpy.Environment,
            cache_request_fn: Callable[[Any], simpy.Event],
            *,
            arrival_rate: Optional[float] = None,
            interarrival_fn: Optional[Callable[[], float]] = None,
            key_generator: Optional[Callable[[str], Any]] = None,
            start_time: float = 0.0,
            name_prefix: str = "Client",
    ):
        self.env = env
        self.cache_request_fn = cache_request_fn
        self.arrival_rate = arrival_rate
        self.interarrival_fn = interarrival_fn or self._default_interarrival
        self.key_generator = key_generator or (lambda cid: cid)
        self.start_time = start_time
        self.name_prefix = name_prefix
        self._counter = 0

        logger.info(
            f"[Client] started: λ={arrival_rate}, start={start_time}, prefix={name_prefix}"
        )
        env.process(self._generate_clients())

    # ------------------------------------------------------------------ #
    def _default_interarrival(self) -> float:
        if self.arrival_rate is None:
            raise ValueError("Either arrival_rate or interarrival_fn must be provided")
        return random.expovariate(self.arrival_rate)

    # ------------------------------------------------------------------ #
    def _generate_clients(self):
        yield self.env.timeout(self.start_time)
        logger.info(f"[Client] generation begins at t={self.env.now:.2f}")
        while True:
            self._counter += 1
            client_id = f"{self.name_prefix}-{self._counter}"
            key = self.key_generator(client_id)

            self.env.process(self._handle_request(client_id, key))

            interval = self.interarrival_fn()
            yield self.env.timeout(interval)

    def _handle_request(self, client_id: str, key: Any):
        start = self.env.now
        logger.debug(f"t={start:.2f}: {client_id} → key={key}")
        yield self.cache_request_fn(key)
        end = self.env.now
        logger.info(f"t={end:.2f}: {client_id} done (wait {end - start:.3f})")


# --------------------------------------------------------------------------- #
#   НОВЫЙ КЛАСС: ЦИКЛИЧЕСКАЯ ИНТЕНСИВНОСТЬ                                    #
# --------------------------------------------------------------------------- #
class CyclicClient:
    """
    Клиент с периодически меняющейся интенсивностью запросов.

    Λ(t) = λ_base · (1 + A · sin(2π t / P)),              0 ≤ A ≤ 1

    Реализован классический метод «отклонения» (thinning) для
    нестационарного пуассоновского процесса.

    Parameters
    ----------
    env : simpy.Environment
    cache_request_fn : Callable
        Функция «сделать запрос к кешу».
    λ_base : float
        Средняя интенсивность.
    amplitude : float
        Амплитуда колебаний (0 — нет колебаний, 1 — от 0 до 2λ_base).
    period : float
        Период колебаний в тех же единицах, что и env.now.
    start_time : float
        Отложенный старт генерации.
    name_prefix : str
        Для красивых логов.
    """

    def __init__(
            self,
            env: simpy.Environment,
            cache_request_fn: Callable[[Any], simpy.Event],
            *,
            lambda_base: float,
            amplitude: float,
            period: float,
            key_generator: Optional[Callable[[str], Any]] = None,
            start_time: float = 0.0,
            name_prefix: str = "CyclicClient",
    ):
        if not (0.0 <= amplitude <= 1.0):
            raise ValueError("amplitude must be within [0, 1]")
        if lambda_base <= 0 or period <= 0:
            raise ValueError("lambda_base and period must be positive")

        self.env = env
        self.cache_request_fn = cache_request_fn
        self.lambda_base = lambda_base
        self.amplitude = amplitude
        self.period = period
        self.key_generator = key_generator or (lambda cid: cid)
        self.start_time = start_time
        self.name_prefix = name_prefix
        self._counter = 0

        # верхняя граница для метода thinning
        self._lambda_max = self.lambda_base * (1 + self.amplitude)

        logger.info(
            f"[CyclicClient] λ_base={lambda_base}, A={amplitude}, P={period}, "
            f"λ_max={self._lambda_max}"
        )
        env.process(self._generate_clients())

    # ------------------------------------------------------------------ #
    #   Основной генератор                                               #
    # ------------------------------------------------------------------ #
    def _generate_clients(self):
        yield self.env.timeout(self.start_time)
        logger.info(f"[CyclicClient] begins at t={self.env.now:.2f}")

        while True:
            # inhomogeneous Poisson – Lewis–Shedler thinning
            t_cur = self.env.now
            while True:
                # 1) кандидат
                tau = random.expovariate(self._lambda_max)
                t_cur += tau
                # 2) вероятность принятия
                lam_t = self._instant_rate(t_cur)
                if random.random() <= lam_t / self._lambda_max:
                    break  # заявка принята

            # дождались до времени t_cur
            yield self.env.timeout(t_cur - self.env.now)

            # создаём клиента
            self._counter += 1
            client_id = f"{self.name_prefix}-{self._counter}"
            key = self.key_generator(client_id)
            self.env.process(self._handle_request(client_id, key))

    # ------------------------------------------------------------------ #
    def _instant_rate(self, t: float) -> float:
        """λ(t) по формуле синуса."""
        return self.lambda_base * (1.0 + self.amplitude * math.sin(2 * math.pi * t / self.period))

    def _handle_request(self, client_id: str, key: Any):
        start = self.env.now
        logger.debug(f"t={start:.2f}: {client_id} → key={key}")
        yield self.cache_request_fn(key)
        end = self.env.now
        logger.info(f"t={end:.2f}: {client_id} done (wait {end - start:.3f})")
