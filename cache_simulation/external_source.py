# cache_simulation/external_source.py

import random

import simpy

from cache_simulation.logger import get_logger
from cache_simulation.metrics import MetricsCollector

logger = get_logger(__name__)


class ExternalSource:
    """
    Внешний источник данных с единым M/M/1-сервером для всех ресурсов,
    но независимыми фоновыми обновлениями для каждого Resource.
    """

    def __init__(
            self,
            env: simpy.Environment,
            min_service: float,
            max_service: float,
            resources: list,
            metrics: MetricsCollector = None
    ):
        """
        :param env: SimPy Environment.
        :param min_service: минимальное время обслуживания запроса (сек).
        :param max_service: максимальное время обслуживания запроса (сек).
        :param resources: список объектов Resource (у каждого своя версия и update_rate).
        :param metrics: опциональный сборщик метрик.
        """
        self.env = env
        self.min_service = min_service
        self.max_service = max_service
        self.resources = resources
        self.metrics = metrics
        self.server = simpy.Resource(env, capacity=1)

        # Запускаем фоновые обновления для каждого ресурса
        for res in self.resources:
            self.env.process(self._update_generator(res))

        logger.info(
            f"ExternalSource initialized: service_time∈[{min_service},{max_service}], "
            f"{len(resources)} resources"
        )

    def _update_generator(self, resource):
        """Пуассоновские обновления версии конкретного ресурса."""
        while True:
            tau = random.expovariate(resource.update_rate)
            yield self.env.timeout(tau)
            resource.version += 1
            logger.info(f"t={self.env.now:.2f}: {resource} updated to v={resource.version}")
            if self.metrics:
                self.metrics.record_source_update(resource, self.env.now)

    def request(self, resource):
        """
        Обслуживает запрос клиента на конкретный Resource через общую очередь.
        Возвращает (value, version).
        """
        return self.env.process(self._request_proc(resource))

    def _request_proc(self, resource):
        arr = self.env.now
        # общая очередь
        with self.server.request() as req:
            yield req
            service_time = random.uniform(self.min_service, self.max_service)
            yield self.env.timeout(service_time)

        finish = self.env.now
        wait = finish - arr
        logger.info(f"t={finish:.2f}: Served {resource}, v={resource.version}, wait={wait:.2f}")

        if self.metrics:
            self.metrics.record_source_call(resource, arr, finish)

        value = f"data_for_{resource.name}"
        return value, resource.version
