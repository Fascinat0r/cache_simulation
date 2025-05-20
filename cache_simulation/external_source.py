# cache_simulation/external_source.py

import math
import random
from typing import Optional

import simpy

from cache_simulation.logger import get_logger
from cache_simulation.metrics import MetricsCollector

logger = get_logger(__name__)


class ExternalSource:
    def __init__(
            self,
            env: simpy.Environment,
            min_service: float,
            max_service: float,
            resources: list,
            metrics: Optional[MetricsCollector] = None,
            update_pattern: str = "poisson",
            cycle_period: float = None,
            cycle_amplitude: float = None,
            peak_phase: float = None,
    ):
        self.env = env
        self.min_service = min_service
        self.max_service = max_service
        self.resources = resources
        self.metrics = metrics
        self.server = simpy.Resource(env, capacity=1)

        # Запускаем фоновые обновления для каждого ресурса
        for res in self.resources:
            if update_pattern == "cyclic":
                self.env.process(self._update_generator_cyclic(
                    res, cycle_period, cycle_amplitude, peak_phase))
            else:
                self.env.process(self._update_generator_poisson(res))

    def _update_generator_poisson(self, resource):
        while True:
            tau = random.expovariate(resource.update_rate)
            yield self.env.timeout(tau)
            resource.version += 1
            logger.info(f"t={self.env.now:.2f}: {resource} updated to v={resource.version}")
            if self.metrics:
                self.metrics.record_source_update(resource, self.env.now)

    def _update_generator_cyclic(self, resource, P, A, φ):
        λ0 = resource.update_rate
        λmax = λ0 * (1 + A)
        t_cur = self.env.now
        while True:
            # thinning: ждём кандидата
            tau = random.expovariate(λmax)
            t_cur += tau
            # момент с проверкой принятия
            lam_t = λ0 * (1 + A * math.sin(2 * math.pi * (t_cur - φ) / P))
            if random.random() <= lam_t / λmax:
                yield self.env.timeout(tau)
                resource.version += 1
                if self.metrics:
                    self.metrics.record_source_update(resource, self.env.now)
            else:
                # отклонили — просто двигаем время
                yield self.env.timeout(tau)

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
