# cache_simulation/client.py

import random
from typing import Callable, Any, Optional

import simpy

from cache_simulation.logger import get_logger

logger = get_logger(__name__)


class Client:
    """
    Класс-генератор клиентских запросов в DES-модели.
    Порождает запросы с заданным законом прихода и ключом для кеша.
    """

    def __init__(
            self,
            env: simpy.Environment,
            cache_request_fn: Callable[[Any], simpy.Event],
            arrival_rate: Optional[float] = None,
            interarrival_fn: Optional[Callable[[], float]] = None,
            key_generator: Optional[Callable[[], Any]] = None,
            start_time: float = 0.0,
            name_prefix: str = "Client"
    ):
        """
        :param env: SimPy Environment
        :param cache_request_fn: функция для выполнения запроса к кешу: cache_request_fn(key) -> Event
        :param arrival_rate: интенсивность пуассоновского прихода (requests per time unit)
        :param interarrival_fn: функция генерации времени между приходами, должна возвращать float
        :param key_generator: функция выдачи ключа для запроса
        :param start_time: время первой активации генератора
        :param name_prefix: префикс для имён клиентов (для логирования)
        """
        self.env = env
        self.cache_request_fn = cache_request_fn
        self.arrival_rate = arrival_rate
        self.interarrival_fn = interarrival_fn or self._default_interarrival
        self.key_generator = key_generator or (lambda: None)
        self.start_time = start_time
        self.name_prefix = name_prefix
        self._counter = 0

        logger.info(f"Scheduler started: arrival_rate={arrival_rate}, start_time={start_time}")

        env.process(self._generate_clients())

    def _default_interarrival(self) -> float:
        if self.arrival_rate is None:
            raise ValueError("Either arrival_rate or interarrival_fn must be provided")
        interval = random.expovariate(self.arrival_rate)
        logger.debug(f"Generated default interarrival interval={interval:.2f}")
        return interval

    def _generate_clients(self):
        # Ждём до старта
        yield self.env.timeout(self.start_time)
        logger.info(f"Client generation begins at t={self.env.now:.2f}")
        while True:
            self._counter += 1
            client_id = f"{self.name_prefix}-{self._counter}"
            key = self.key_generator()
            logger.debug(f"t={self.env.now:.2f}: {client_id} generated, key={key}")

            self.env.process(self._handle_request(client_id, key))

            interval = self.interarrival_fn()
            logger.debug(f"t={self.env.now:.2f}: Next client in {interval:.2f}")
            yield self.env.timeout(interval)

    def _handle_request(self, client_id: str, key: Any):
        start = self.env.now
        logger.debug(f"t={start:.2f}: {client_id} requests key={key}")
        result = yield self.cache_request_fn(key)
        end = self.env.now
        wait = end - start
        logger.info(f"t={end:.2f}: {client_id} received {result} (waited {wait:.2f})")
