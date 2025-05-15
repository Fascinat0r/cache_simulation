# cache_simulation/external_source.py

import random

import simpy

from cache_simulation.logger import get_logger
from cache_simulation.metrics import MetricsCollector

logger = get_logger(__name__)


class ExternalSource:
    """
    Класс, моделирующий внешний источник данных («чёрный ящик») в системе массового
    обслуживания. Обслуживает **все** виды данных через единый сервер (Resource, capacity=1),
    но хранит **для каждого** вида данных (Resource) свою версию и генерирует обновления
    по пуассоновскому процессу с индивидуальной скоростью.

    Модель:
      - Одна общая очередь (M/M/1) для всех входящих запросов.
      - Равномерное время обслуживания в пределах [min_service, max_service].
      - Для каждого ресурса (запроса) фоновый процесс обновлений с λ = resource.update_rate.
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
        Инициализирует внешний источник.

        :param env: SimPy Environment для моделирования событий.
        :param min_service: минимальное время обслуживания одного запроса (секунды).
        :param max_service: максимальное время обслуживания одного запроса (секунды).
        :param resources: список объектов Resource, у каждого своя версия и update_rate.
        :param metrics: опциональный MetricsCollector — для записи времени обновлений.
        """
        self.env = env
        self.min_service = min_service
        self.max_service = max_service
        self.resources = resources
        self.metrics = metrics

        # Одна общая единичная очередь для всех запросов
        self.server = simpy.Resource(env, capacity=1)

        # Запускаем фоновые процессы для обновлений каждого ресурса
        for resource in self.resources:
            self.env.process(self._update_generator(resource))

        logger.info(
            f"Initialized ExternalSource: service_time∈[{self.min_service},{self.max_service}], "
            f"{len(self.resources)} resources"
        )

    def _update_generator(self, resource):
        """
        Фоновый процесс: для данного resource генерируем обновления по пуассоновскому
        процессу (экспоненциальный интервал с λ = resource.update_rate).
        При каждом обновлении bump’им resource.version и логируем событие.
        """
        while True:
            # Ждём до следующего апдейта для этого ресурса
            tau = random.expovariate(resource.update_rate)
            yield self.env.timeout(tau)

            # Увеличиваем версию отдельного ресурса
            resource.version += 1
            logger.info(f"t={self.env.now:.2f}: {resource} updated to version {resource.version}")

            if self.metrics:
                self.metrics.record_source_update(self.env.now)

    def request(self, resource):
        """
        Входная точка для клиентских запросов к внешнему источнику.

        :param resource: объект Resource, который запрашивает клиент.
        :return: simpy.Event, завершающийся результатом (value, version).
        """
        return self.env.process(self._request_proc(resource))

    def _request_proc(self, resource):
        """
        Процесс обслуживания одного запроса:
          1. Запрос в общую очередь self.server.
          2. Служба равномерно от min_service до max_service.
          3. Возвращает кэшируемую пару (value, version) для конкретного resource.
        """
        arrival = self.env.now

        # Ожидаем в очереди до освобождения «сервера»
        with self.server.request() as req:
            yield req
            # Служба занимает случайное время в заданном диапазоне
            service_time = random.uniform(self.min_service, self.max_service)
            yield self.env.timeout(service_time)

        finish = self.env.now
        wait = finish - arrival

        # Логирование окончательного обслуживания
        logger.info(
            f"t={finish:.2f}: Served {resource}, version={resource.version}, wait={wait:.2f}"
        )

        # Формируем результат: value может быть «сырыми данными» для этого ключа
        value = f"data_for_{resource.name}"
        return value, resource.version
