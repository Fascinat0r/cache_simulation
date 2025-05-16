# cache_simulation/resources/simple.py

from cache_simulation.resources.base import ResourceBase


class SimpleResource(ResourceBase):
    """
    Простейшая реализация Resource, у которой
    интенсивность обновлений задаётся в конструкторе.
    """

    __slots__ = ("_update_rate",)

    def __init__(self, name: str, update_rate: float):
        """
        :param name: уникальное имя ресурса
        :param update_rate: λ_upd — интенсивность пуассоновского процесса обновлений
        """
        super().__init__(name)
        if update_rate < 0:
            raise ValueError("update_rate must be non-negative")
        self._update_rate = update_rate

    @property
    def update_rate(self) -> float:
        """
        Интенсивность обновлений этого ресурса.
        """
        return self._update_rate
