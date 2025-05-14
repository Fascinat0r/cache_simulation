# cache_simulation/strategies/base.py

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cache_simulation.cache import CacheEntry


class CacheStrategy(ABC):
    """
    Базовый абстрактный класс для стратегий инвалидации кеша.
    Определяет интерфейс для проверки валидности и реакцию на доступ/обновление.
    """

    @abstractmethod
    def is_valid(self, entry: "CacheEntry", now: float) -> bool:
        """
        Проверяет, считается ли запись актуальной в момент времени now.

        :param entry: объект CacheEntry для проверки
        :param now: текущее время симуляции (env.now)
        :return: True, если запись ещё валидна (HIT), False иначе (MISS)
        """
        ...

    @abstractmethod
    def on_access(self, entry: "CacheEntry", now: float) -> None:
        """
        Вызывается при успешном попадании в кеш (HIT).
        Может обновлять внутренние статистики или настраивать параметры.

        :param entry: объект CacheEntry, к которому был доступ
        :param now: время доступа
        """
        ...

    @abstractmethod
    def on_update(self, entry: "CacheEntry", now: float) -> None:
        """
        Вызывается при обновлении кеш-записи (после MISS и получения новых данных).
        Может сбрасывать или перенастраивать внутренние параметры.

        :param entry: обновлённый CacheEntry
        :param now: время обновления
        """
        ...
