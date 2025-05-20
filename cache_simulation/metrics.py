# заменяем весь файл; добавлены метрики ttl_changes и метод record_ttl_change
from statistics import mean
from typing import Any, Dict, List, Optional

from cache_simulation.logger import get_logger

logger = get_logger(__name__)


class MetricsCollector:
    """
    Сбор и экспорт метрик симуляции.

    Расширено:
    ----------
    * ttl_changes – динамика изменения TTL адаптивной стратегии.
    """

    def __init__(self):
        # ---- задержки ----
        self.miss_times: List[float] = []
        self.correct_hits: List[float] = []
        self.incorrect_hits: List[float] = []

        # ---- счётчики событий ----
        self.stale_initial: int = 0
        self.stale_repeat: int = 0
        self.cache_updates: int = 0
        self.redundant_misses: int = 0

        # ---- «сырые» данные ----
        self.hit_entry_ages: List[float] = []
        self.stale_entry_ages: List[float] = []
        self.events: List[Dict[str, Any]] = []
        self.source_calls: List[Dict[str, Any]] = []
        self.source_updates: List[Dict[str, Any]] = []
        self.cache_calls: List[Dict[str, Any]] = []
        self.ttl_changes: List[Dict[str, float]] = []

        self.prefetch_events: List[Dict[str, Any]] = []
        self.detected_periods: List[Dict[str, Any]] = []
        self.profile_scores: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    #   Методы‑регистраторы                                              #
    # ------------------------------------------------------------------ #
    def record_miss(self, wait_time: float):
        self.miss_times.append(wait_time)

    def record_correct_hit(self, wait_time: float):
        self.correct_hits.append(wait_time)

    def record_incorrect_hit(self, wait_time: float):
        self.incorrect_hits.append(wait_time)

    def record_stale_initial(self):
        self.stale_initial += 1

    def record_stale_repeat(self):
        self.stale_repeat += 1

    def record_cache_update(self):
        self.cache_updates += 1

    def record_redundant_miss(self):
        self.redundant_misses += 1

    def record_entry_age_on_hit(self, age: float):
        self.hit_entry_ages.append(age)

    def record_entry_age_on_stale(self, age: float):
        self.stale_entry_ages.append(age)

    def record_cache_call(
            self,
            key: Any,
            start: float,
            finish: float,
            call_type: str,
            version: int,
    ):
        self.cache_calls.append(
            {
                "key": str(key),
                "start": start,
                "finish": finish,
                "type": call_type,
                "version": version,
            }
        )

    def record_prefetch(self, time: float, resource: str):
        self.prefetch_events.append({"time": time, "resource": resource})

    def record_periods(self, time: float, periods: List[float]):
        self.detected_periods.append({"time": time, "periods": periods})

    def record_profile(self, time: float, period: float, bin_start: float, p: float):
        self.profile_scores.append({
            "time": time,
            "period": period,
            "bin": bin_start,
            "p": p
        })

    def record_event(self, time: float, event_type: str, key: Any, cache_size: int):
        self.events.append(
            {
                "time": time,
                "event": event_type,
                "key": str(key) if key is not None else None,
                "cache_size": cache_size,
            }
        )

    def record_source_call(self, resource, start: float, finish: float):
        self.source_calls.append(
            {
                "resource": resource.name,
                "start": start,
                "finish": finish,
                "latency": finish - start,
            }
        )

    def record_source_update(self, resource, time: float):
        self.source_updates.append(
            {
                "resource": resource.name,
                "time": time,
                "new_version": resource.version,
            }
        )

    # ---------- НОВОЕ ----------
    def record_ttl_change(self, time: float, ttl: float):
        """Фиксируем момент смены TTL адаптивной стратегии."""
        self.ttl_changes.append({"time": time, "ttl": ttl})

    # ------------------------------------------------------------------ #
    #   Сводка результатов                                               #
    # ------------------------------------------------------------------ #
    def collect_from(self, simulator) -> None:
        self.record_event(simulator.env.now, "final_cache_size", None, len(simulator.cache))

    def summary(self) -> dict:
        correct = len(self.correct_hits)
        incorrect = len(self.incorrect_hits)
        misses = len(self.miss_times)
        total = correct + incorrect + misses

        hit_rate = (correct + incorrect) / total if total else 0.0
        correct_rate = correct / (correct + incorrect) if (correct + incorrect) else 0.0
        miss_rate = misses / total if total else 0.0

        updates_by_res: Dict[str, int] = {}
        for rec in self.source_updates:
            updates_by_res.setdefault(rec["resource"], 0)
            updates_by_res[rec["resource"]] += 1

        data = {
            # агрегаты
            "total_requests": total,
            "correct_hits": correct,
            "incorrect_hits": incorrect,
            "misses": misses,
            "hit_rate": hit_rate,
            "correct_rate": correct_rate,
            "miss_rate": miss_rate,
            "cache_updates": self.cache_updates,
            "redundant_misses": self.redundant_misses,
            "avg_correct_hit_time": mean(self.correct_hits) if self.correct_hits else None,
            "avg_incorrect_hit_time": mean(self.incorrect_hits) if self.incorrect_hits else None,
            "avg_miss_time": mean(self.miss_times) if self.miss_times else None,
            "stale_initial": self.stale_initial,
            "stale_repeat": self.stale_repeat,
            "source_calls": len(self.source_calls),
            "updates_by_resource": updates_by_res,
            "total_source_updates": len(self.source_updates),
            # подробные логи
            "events": self.events,
            "cache_calls_detail": self.cache_calls,
            "source_calls_detail": self.source_calls,
            "source_updates_detail": self.source_updates,
            "hit_entry_ages": self.hit_entry_ages,
            "stale_entry_ages": self.stale_entry_ages,
            "ttl_changes": self.ttl_changes,
            "prefetch_events": self.prefetch_events,
            "detected_periods": self.detected_periods,
            "profile_scores": self.profile_scores,
        }
        return data

    # экспорт (без изменений)
    def export(self, path: Optional[str]) -> None:
        ...
