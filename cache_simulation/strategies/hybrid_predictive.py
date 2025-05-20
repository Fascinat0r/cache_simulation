# cache_simulation/strategies/hybrid_predictive.py

from typing import List

import numpy as np
import simpy

from cache_simulation.cache import CacheEntry
from cache_simulation.logger import get_logger
from cache_simulation.metrics import MetricsCollector
from cache_simulation.strategies.adaptive import AdaptiveTTLStrategy
from cache_simulation.strategies.base import CacheStrategy

logger = get_logger(__name__)


class HybridPredictiveStrategy(CacheStrategy):
    def __init__(self, *,
                 env: simpy.Environment,
                 metrics: MetricsCollector,
                 base_strategy: AdaptiveTTLStrategy,
                 history_window: float,
                 analyze_interval: float,
                 profile_bin_size: float,
                 prefetch_interval: float,
                 max_periods: int,
                 k: float):
        # базовый адаптивный TTL
        self.base = base_strategy
        self.env = env
        self.metrics = metrics

        # параметры предиктива
        self.history_window = history_window
        self.analyze_interval = analyze_interval
        self.profile_bin = profile_bin_size
        self.prefetch_interval = prefetch_interval
        self.max_periods = max_periods
        self.k = k

        # хранить timestamps источника обновлений
        self._update_history: List[float] = []
        # профиль вероятностей по бинам и периодам
        self._profiles = {}

        # фоновые процессы
        env.process(self._analysis_loop())
        env.process(self._prefetch_loop())

    # делегируем реактивную логику
    def is_valid(self, entry: CacheEntry, now: float) -> bool:
        return self.base.is_valid(entry, now)

    def on_access(self, entry: CacheEntry, now: float) -> None:
        return self.base.on_access(entry, now)

    def on_update(self, entry: CacheEntry, now: float) -> None:
        # сюда попадаем при miss → источник гарантированно обновлён
        self._update_history.append(now)
        return self.base.on_update(entry, now)

    def on_prefetch_success(self, entry: CacheEntry, now: float) -> None:
        # сбрасываем историю до последнего fetch, чтобы не портить статистику
        self._update_history = [t for t in self._update_history if t > now]

    # ——— анализ FFT каждые analyze_interval ———
    def _analysis_loop(self):
        while True:
            yield self.env.timeout(self.analyze_interval)
            window_start = self.env.now - self.history_window
            hist = [t for t in self._update_history if t >= window_start]
            if len(hist) < 2:
                continue

            # строим интервальную функцию: бинаризуем события в бины
            bins = np.arange(window_start, self.env.now + self.profile_bin, self.profile_bin)
            counts, _ = np.histogram(hist, bins=bins)
            # делаем FFT
            freqs = np.fft.fftfreq(len(counts), d=self.profile_bin)
            mag = np.abs(np.fft.fft(counts))
            idx = np.argsort(mag)[-self.max_periods:]
            periods = [1 / abs(freqs[i]) for i in idx if freqs[i] != 0]
            self.metrics.record_periods(self.env.now, periods)

            # строим профиль вероятностей для каждого периода
            for T in periods:
                profile = {}
                for i, b in enumerate(bins[:-1]):
                    # вероятность события в бинi
                    p = counts[i] / counts.sum() if counts.sum() > 0 else 0
                    profile[b] = p
                    self.metrics.record_profile(self.env.now, T, b, p)
                self._profiles[T] = profile

    # ——— префетчинг каждые prefetch_interval ———
    def _prefetch_loop(self):
        while True:
            yield self.env.timeout(self.prefetch_interval)
            now = self.env.now
            for T, profile in self._profiles.items():
                # выбираем бин по текущему времени
                bin_start = now - (now % self.profile_bin)
                p = profile.get(bin_start, 0)
                # вероятность предиктива
                p_pred = 1 - np.exp(-self.k * p * self.history_window / T)
                if np.random.rand() < p_pred:
                    # запускаем prefetch
                    self.metrics.record_event(now, "prefetch_trigger", None, len(self._profiles))
                    # self._cache.request(...) вызовит on_prefetch_success()
                    # стратегии нужно иметь доступ к Cache, поэтому мы сохраняем его при init
                    self.cache_ref.request(self.key, is_prefetch=True)

    # ——— метод для привязки Cache и ключа ресурса ———
    def bind_cache(self, cache, key):
        self.cache_ref = cache
        self.key = key
