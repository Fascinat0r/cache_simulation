import random

import matplotlib.pyplot as plt
import simpy

from cache_simulation.external_source import ExternalSource
from cache_simulation.logger import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


def test_client_simulation():
    """
    Демонстрация работы клиентов с ExternalSource и построение графиков:
    - гистограмма времён ожидания клиентов
    - эволюция версии данных во времени
    """
    RANDOM_SEED = 42
    SIM_TIME = 10
    ARRIVAL_INTERVAL = 1  # клиенты приходят каждую секунду
    EXTRA_TIME = 2000  # дополнительное время для фоновых обновлений

    random.seed(RANDOM_SEED)
    env = simpy.Environment()

    # Внешний источник: обслуживание 3–10 с, обновления ~1 раз в 20 с
    source = ExternalSource(env,
                            min_service=3.0,
                            max_service=10.0,
                            update_rate=1 / 50)

    wait_times = []
    versions = []
    times = []

    def client(env, source, client_id):
        arrival = env.now
        with source.server.request() as req:
            yield req
            wait = env.now - arrival
            wait_times.append(wait)
            service_time = random.uniform(source.min_service, source.max_service)
            yield env.timeout(service_time)
            versions.append(source.version)
            times.append(env.now)

    # Генерация клиентов до SIM_TIME
    next_arrival = 0.0
    while next_arrival < SIM_TIME:
        env.process(client(env, source, int(next_arrival / ARRIVAL_INTERVAL) + 1))
        env.run(until=next_arrival + ARRIVAL_INTERVAL)
        next_arrival += ARRIVAL_INTERVAL

    # Дадим еще немного времени фоновым обновлениям
    env.run(until=SIM_TIME + EXTRA_TIME)

    # Построение графиков
    fig, axes = plt.subplots(2, 1, figsize=(8, 6))
    axes[0].hist(wait_times, bins=10)
    axes[0].set_title('Гистограмма времён ожидания клиентов')
    axes[0].set_xlabel('Время ожидания (с)')
    axes[0].set_ylabel('Число клиентов')

    axes[1].step(times, versions, where='post')
    axes[1].set_title('Эволюция версии данных во времени')
    axes[1].set_xlabel('Время моделирования (с)')
    axes[1].set_ylabel('Версия данных')

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    logger.info("Test Client Simulation started")
    test_client_simulation()
