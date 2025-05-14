# cache_simulation/metrics.py

import csv
import json
from pathlib import Path
from statistics import mean
from typing import List, Optional

from cache_simulation.logger import get_logger

logger = get_logger(__name__)


class MetricsCollector:
    """
    Сборщик метрик для DES-симуляции кеширования.

    Метрики:
      - hit_times: времена ожидания при попадании в кеш
      - miss_times: времена ожидания при промахе
      - stale_count: число случаев, когда возвращены устаревшие данные
      - source_calls: число обращений к внешнему источнику
    """

    def __init__(self):
        self.hit_times: List[float] = []
        self.miss_times: List[float] = []
        self.stale_count: int = 0
        self.source_calls: int = 0

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

    def collect_from(self, simulator) -> None:
        """
        Если нужно, можно собрать дополнительные метрики из объектов симуляции.
        Заготовка для расширения.
        """
        pass

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

        summary = {
            "total_requests": total_requests,
            "total_hits": total_hits,
            "total_misses": total_misses,
            "hit_rate": hit_rate,
            "miss_rate": miss_rate,
            "avg_hit_time": avg_hit_time,
            "avg_miss_time": avg_miss_time,
            "stale_count": self.stale_count,
            "source_calls": self.source_calls
        }
        logger.info(f"Metrics summary: {summary}")
        return summary

    def export(self, path: Optional[str]) -> None:
        """
        Экспортирует summary в JSON и CSV рядом с указанным файлом.
        """
        if not path:
            logger.warning("No export path provided; skipping metrics export")
            return

        summary = self.summary()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        # JSON
        json_path = p.with_suffix(".json")
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(summary, jf, indent=2, ensure_ascii=False)
        logger.info(f"Metrics exported to {json_path}")

        # CSV
        csv_path = p.with_suffix(".csv")
        with open(csv_path, "w", newline='', encoding="utf-8") as cf:
            writer = csv.writer(cf)
            writer.writerow(["metric", "value"])
            for k, v in summary.items():
                writer.writerow([k, v])
        logger.info(f"Metrics exported to {csv_path}")
