# cache_simulation/resource.py

from abc import ABC


class Resource(ABC):
    """
    Абстрактный базовый класс для всех типов ресурсов (видов запросов).
    Каждый ресурс хранит свою текущую версию данных и умеет сообщать,
    с какой интенсивностью должен обновляться.
    """

    __slots__ = ("name", "version")

    def __init__(self, name: str):
        """
        :param name: уникальное имя ресурса (ключ запроса)
        """
        self.name = name
        self.version = 0  # изначальная версия

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name}, v={self.version})"

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return isinstance(other, Resource) and self.name == other.name

    def __hash__(self):
        return hash(self.name)
