# cache_simulation/metrics.py

import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

from cache_simulation.logger import get_logger

logger = get_logger(__name__)


class MetricsCollector:
    """
    Сборщик метрик для DES-симуляции кеширования.
    """

    def __init__(self):
        # старые
        self.hit_times: List[float] = []
        self.miss_times: List[float] = []
        self.stale_count: int = 0
        self.source_calls: int = 0
        self.cache_updates: int = 0  # сколько miss-ов реально обновили данные
        self.redundant_misses: int = 0  # сколько miss-ов вернули ту же версию
        self.hit_entry_ages: List[float] = []
        self.stale_entry_ages: List[float] = []
        self.events: List[Dict[str, Any]] = []
        self.source_update_times: List[float] = []

    def record_hit(self, wait_time: float):
        self.hit_times.append(wait_time)
        logger.debug(f"Metric: hit recorded, wait_time={wait_time:.2f}")

    def record_miss(self, wait_time: float):
        self.miss_times.append(wait_time)
        logger.debug(f"Metric: miss recorded, wait_time={wait_time:.2f}")

    def record_stale(self):
        self.stale_count += 1
        logger.debug("Metric: stale recorded")

    def record_source_call(self):
        self.source_calls += 1
        logger.debug("Metric: source call recorded")

    def record_cache_update(self):
        """Miss-запрос, при котором версия отличается и кэш реально обновился."""
        self.cache_updates += 1
        logger.debug("Metric: cache updated on miss")

    def record_redundant_miss(self):
        """Miss-запрос, при котором версия совпала — бесполезный miss."""
        self.redundant_misses += 1
        logger.debug("Metric: redundant miss (no version change)")

    def record_entry_age_on_hit(self, age: float):
        self.hit_entry_ages.append(age)
        logger.debug(f"Metric: entry age on hit={age:.2f}")

    def record_entry_age_on_stale(self, age: float):
        self.stale_entry_ages.append(age)
        logger.debug(f"Metric: entry age on stale={age:.2f}")

    def record_event(self, time: float, event_type: str, key: Any, cache_size: int):
        """
        Логируем каждое событие hit/stale/miss
        вместе с временем, ключом и текущим размером кеша.
        """
        self.events.append({
            "time": time,
            "event": event_type,
            "key": None if key is None else str(key),
            "cache_size": cache_size
        })
        logger.debug(f"Metric: event {event_type} at t={time:.2f}, key={key}, cache_size={cache_size}")

    def record_source_update(self, time: float):
        self.source_update_times.append(time)
        logger.debug(f"Metric: source updated at t={time:.2f}")

    # ——————————————————————————————————————

    def collect_from(self, simulator) -> None:
        """
        Собираем финальный размер кеша и финальную версию источника.
        """
        final_cache_size = len(simulator.cache)
        final_version = simulator.source.version
        # дополнительно можно сохранить в events
        self.record_event(simulator.env.now, "final_cache_size", None, final_cache_size)
        self.record_source_update(simulator.env.now)  # на всякий случай
        logger.debug(f"Collected final cache size={final_cache_size}, source version={final_version}")

    def summary(self) -> dict:
        """
        Возвращает словарь с агрегированными метриками.
        """
        total_hits = len(self.hit_times)
        total_misses = len(self.miss_times)
        total_requests = total_hits + total_misses
        hit_rate = total_hits / total_requests if total_requests else 0.0
        miss_rate = total_misses / total_requests if total_requests else 0.0

        avg_hit_time = mean(self.hit_times) if self.hit_times else None
        avg_miss_time = mean(self.miss_times) if self.miss_times else None

        avg_entry_age_on_hit = mean(self.hit_entry_ages) if self.hit_entry_ages else None
        avg_entry_age_on_stale = mean(self.stale_entry_ages) if self.stale_entry_ages else None

        # посчитаем события по типам
        etypes = [e["event"] for e in self.events]
        events_by_type = {t: etypes.count(t) for t in set(etypes)}

        summary: Dict[str, Any] = {
            "total_requests": total_requests,
            "total_hits": total_hits,
            "total_misses": total_misses,
            "hit_rate": hit_rate,
            "miss_rate": miss_rate,
            "cache_updates": self.cache_updates,
            "redundant_misses": self.redundant_misses,
            "invalidation_efficiency": (self.cache_updates / total_misses if total_misses else None),
            "avg_hit_time": avg_hit_time,
            "avg_miss_time": avg_miss_time,
            "stale_count": self.stale_count,
            "source_calls": self.source_calls,
            "avg_entry_age_on_hit": avg_entry_age_on_hit,
            "avg_entry_age_on_stale": avg_entry_age_on_stale,
            "total_events": len(self.events),
            "events_by_type": events_by_type,
            "total_source_updates": len(self.source_update_times)
        }
        logger.info(f"Metrics summary: {summary}")

        # === добавляем сырые данные ===
        summary.update({
            "events": self.events,
            "hit_entry_ages": self.hit_entry_ages,
            "stale_entry_ages": self.stale_entry_ages,
            "source_update_times": self.source_update_times,
        })
        return summary

    def export(self, path: Optional[str]) -> None:
        """
        Экспортирует summary в JSON/CSV рядом с указанным файлом.
        """
        if not path:
            logger.warning("No export path provided; skipping metrics export")
            return

        summary = self.summary()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        # JSON summary
        json_path = p.with_suffix(".json")
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(summary, jf, indent=2, ensure_ascii=False)
        logger.info(f"Metrics summary exported to {json_path}")

        # CSV summary
        csv_path = p.with_suffix(".csv")
        with open(csv_path, "w", newline='', encoding="utf-8") as cf:
            writer = csv.writer(cf)
            writer.writerow(["metric", "value"])
            for k, v in summary.items():
                writer.writerow([k, v])
        logger.info(f"Metrics summary exported to {csv_path}")
