# cache_simulation/strategies/fixed_ttl.py

from cache_simulation.cache import CacheEntry
from cache_simulation.logger import get_logger
from cache_simulation.strategies.base import CacheStrategy

logger = get_logger(__name__)


class FixedTTLStrategy(CacheStrategy):
    """
    Простая стратегия инвалидации с фиксированным временем жизни (TTL).
    Запись считается валидной, если с момента последнего обновления прошло не более ttl.
    """

    def __init__(self, ttl: float):
        """
        :param ttl: время жизни записи в тех же единицах, что и env.now
        """
        if ttl < 0:
            raise ValueError("TTL must be non-negative")
        self.ttl = ttl
        logger.info(f"FixedTTLStrategy initialized with ttl={ttl}")

    def is_valid(self, entry: CacheEntry, now: float) -> bool:
        """
        Возвращает True, если запись ещё действительна.
        """
        age = now - entry.timestamp
        valid = age <= self.ttl
        logger.debug(
            f"is_valid: now={now:.2f}, entry_ts={entry.timestamp:.2f}, age={age:.2f}, ttl={self.ttl}, valid={valid}")
        return valid

    def on_access(self, entry: CacheEntry, now: float) -> None:
        """
        На HIT ничего не меняем.
        """
        logger.debug(f"on_access: key version={entry.version}, timestamp={entry.timestamp:.2f}")

    def on_update(self, entry: CacheEntry, now: float) -> None:
        """
        При обновлении обновляем timestamp (делается при создании CacheEntry).
        """
        logger.debug(f"on_update: entry updated to version={entry.version} at t={now:.2f}")
