import random

import simpy

from cache_simulation.logger import get_logger

logger = get_logger(__name__)


class ExternalSource:
    """
    Класс, моделирующий внешний источник данных («чёрный ящик») в системе массового обслуживания.
    Работает как M/M/1-сервер, но вместо экспоненциального распределения обслуживания
    использует равномерное из диапазона [min_service, max_service].
    Генерирует обновления данных по пуассоновскому процессу.
    Логгирует все события.
    """

    def __init__(self,
                 env: simpy.Environment,
                 min_service: float,
                 max_service: float,
                 update_rate: float):
        """
        :param env: SimPy Environment для моделирования событий.
        :param min_service: Минимальное время обслуживания (сек).
        :param max_service: Максимальное время обслуживания (сек).
        :param update_rate: Интенсивность обновлений λ_upd.
        """
        self.env = env
        self.min_service = min_service
        self.max_service = max_service
        self.update_rate = update_rate
        self.server = simpy.Resource(env, capacity=1)
        self.version = 0

        logger.info(f"Initialized ExternalSource with service ∈[{min_service},{max_service}], "
                    f"update_rate={update_rate}")

        # Запускаем фоновые обновления
        self.env.process(self._update_generator())

    def _update_generator(self):
        """Генерирует события обновления по пуассоновскому процессу."""
        while True:
            tau = random.expovariate(self.update_rate)
            yield self.env.timeout(tau)
            self.version += 1
            logger.info(f"t={self.env.now:.2f}: Data updated to version {self.version}")

    def request(self, client_id: int) -> simpy.Event:
        """
        Обрабатывает запрос от клиента:
        - ждёт освобождения сервера
        - обслуживается в random.uniform(min_service, max_service)
        - логгирует все этапы
        """
        return self.env.process(self._request_proc(client_id))

    def _request_proc(self, client_id: int):
        arrival = self.env.now
        logger.debug(f"t={arrival:.2f}: Client {client_id} arrived, requesting service")

        with self.server.request() as req:
            yield req
            wait = self.env.now - arrival
            logger.debug(f"t={self.env.now:.2f}: Client {client_id} acquired server after waiting {wait:.2f}")

            service_time = random.uniform(self.min_service, self.max_service)
            logger.debug(f"t={self.env.now:.2f}: Service starts for {client_id}, will take {service_time:.2f}")
            yield self.env.timeout(service_time)

        finish = self.env.now
        logger.info(
            f"t={finish:.2f}: Client {client_id} done, version={self.version}, total_wait={finish - arrival:.2f}"
        )
        # TODO Предположим, что «value» совпадает с client_id или берётся из внешнего хранилища:
        value = f"data_for_{client_id}"
        return value, self.version
