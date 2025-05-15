# cache_simulation/resource.py

class Resource:
    """
    Простая обёртка-ключ для кеша.
    """
    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return isinstance(other, Resource) and self.name == other.name

    def __hash__(self):
        return hash(self.name)
