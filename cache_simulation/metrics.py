# cache_simulation/metrics.py

import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

from cache_simulation.logger import get_logger

logger = get_logger(__name__)


class MetricsCollector:
    def __init__(self):
        # miss
        self.miss_times: List[float] = []
        # hits разбиваем на правильные и неправильные
        self.correct_hits: List[float] = []
        self.incorrect_hits: List[float] = []
        # stale initial / repeat
        self.stale_initial: int = 0
        self.stale_repeat: int = 0
        # прочие счётчики
        self.cache_updates: int = 0
        self.redundant_misses: int = 0
        # entry ages
        self.hit_entry_ages: List[float] = []
        self.stale_entry_ages: List[float] = []
        # события и вызовы источника
        self.events: List[Dict[str, Any]] = []
        self.source_calls: List[Dict[str, Any]] = []
        self.source_updates: List[Dict[str, Any]] = []
        self.cache_calls: List[Dict[str, Any]] = []

    def record_miss(self, wait_time: float):
        self.miss_times.append(wait_time)
        logger.debug(f"Metric: miss ({wait_time:.2f})")

    def record_correct_hit(self, wait_time: float):
        self.correct_hits.append(wait_time)
        logger.debug(f"Metric: hit_correct ({wait_time:.2f})")

    def record_incorrect_hit(self, wait_time: float):
        self.incorrect_hits.append(wait_time)
        logger.debug(f"Metric: hit_incorrect ({wait_time:.2f})")

    def record_stale_initial(self):
        self.stale_initial += 1
        logger.debug("Metric: stale_initial")

    def record_stale_repeat(self):
        self.stale_repeat += 1
        logger.debug("Metric: stale_repeat")

    def record_cache_update(self):
        self.cache_updates += 1
        logger.debug("Metric: cache updated")

    def record_redundant_miss(self):
        self.redundant_misses += 1
        logger.debug("Metric: redundant miss")

    def record_entry_age_on_hit(self, age: float):
        self.hit_entry_ages.append(age)

    def record_entry_age_on_stale(self, age: float):
        self.stale_entry_ages.append(age)

    def record_cache_call(self, key: Any, start: float, finish: float, call_type: str, version: int):
        """
        Запись запроса к кэшу: start, finish, тип ('hit_correct', 'miss', …) и версия.
        """
        self.cache_calls.append({
            "key": str(key),
            "start": start,
            "finish": finish,
            "type": call_type,
            "version": version,
        })
        logger.debug(f"Metric: cache_call {call_type} key={key} v={version} [{start:.3f}→{finish:.3f}]")

    def record_event(self, time: float, event_type: str, key: Any, cache_size: int):
        self.events.append({
            "time": time,
            "event": event_type,
            "key": str(key) if key is not None else None,
            "cache_size": cache_size
        })

    def record_source_call(self, resource, start: float, finish: float):
        """
        Запись о том, что внешний источник обслужил запрос по resource.
        """
        self.source_calls.append({
            "resource": resource.name,
            "start": start,
            "finish": finish,
            "latency": finish - start
        })

    def record_source_update(self, resource, time: float):
        """
        Фоновое обновление версии resource.
        """
        self.source_updates.append({
            "resource": resource.name,
            "time": time,
            "new_version": resource.version
        })

    def collect_from(self, simulator) -> None:
        # final cache size
        self.record_event(simulator.env.now, "final_cache_size", None, len(simulator.cache))
        logger.debug("Collected final cache size")

    def summary(self) -> dict:
        correct = len(self.correct_hits)
        incorrect = len(self.incorrect_hits)
        misses = len(self.miss_times)
        total = correct + incorrect + misses

        hit_rate = (correct + incorrect) / total if total else 0.0
        correct_rate = correct / (correct + incorrect) if (correct + incorrect) else 0.0
        incorrect_rate = incorrect / (correct + incorrect) if (correct + incorrect) else 0.0
        miss_rate = misses / total if total else 0.0

        # подсчёт обновлений источника по ресурсам
        updates_by_res: Dict[str, int] = {}
        for rec in self.source_updates:
            updates_by_res.setdefault(rec["resource"], 0)
            updates_by_res[rec["resource"]] += 1

        summary = {
            "total_requests": total,
            "correct_hits": correct,
            "incorrect_hits": incorrect,
            "misses": misses,
            "hit_rate": hit_rate,
            "correct_rate": correct_rate,
            "incorrect_rate": incorrect_rate,
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
            "total_source_updates": len(self.source_updates)
        }

        # добавить «сырые» данные
        summary.update({
            "events": self.events,
            "cache_calls_detail": self.cache_calls,
            "source_calls_detail": self.source_calls,
            "source_updates_detail": self.source_updates,
            "hit_entry_ages": self.hit_entry_ages,
            "stale_entry_ages": self.stale_entry_ages,
        })
        return summary

    def export(self, path: Optional[str]) -> None:
        if not path:
            logger.warning("Skipping export, no path")
            return
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # json
        with open(p.with_suffix(".json"), "w", encoding="utf-8") as f:
            json.dump(self.summary(), f, indent=2, ensure_ascii=False)
        # csv как прежде...
