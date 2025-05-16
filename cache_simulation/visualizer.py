import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib import cm


class SimulationVisualizer:
    """
    Визуализатор DES-симуляции кеширования:
      - plot_request_flow: диаграмма Ганта запросов + стрелки потоков
      - plot_version_timeline: две дорожки (реальная версия и версия в кеше) для одного ресурса
    """

    def __init__(self, metrics: dict, resource_name: str = None):
        self.metrics = metrics
        self.cache_calls = metrics.get("cache_calls_detail", [])
        self.source_calls = metrics.get("source_calls_detail", [])
        self.real_updates = metrics.get("source_updates_detail", [])

        # конец симуляции = максимум из всех моментов завершения и обновлений
        all_times = [c["finish"] for c in self.cache_calls] + \
                    [c["finish"] for c in self.source_calls] + \
                    [u["time"] for u in self.real_updates]
        self.t_end = max(all_times) if all_times else 0.0

        # выбираем ресурс
        self.resource = resource_name or (
            self.real_updates[0]["resource"] if self.real_updates else None
        )

        # цвета для разных типов ответов кеша
        self.cache_colors = {
            "hit_correct": "#4caf50",
            "hit_incorrect": "#5D00FF",
            "stale_initial": "#ffc107",
            "stale_repeat": "#ff9800",
            "miss": "#f44336",
        }

        # подписи для легенды по типам
        self.cache_labels = {
            "hit_correct": "Попадание",
            "hit_incorrect": "Попадание (ложь)",
            "stale_initial": "Первое устаревание",
            "stale_repeat": "Повторное устаревание",
            "miss": "Промах"
        }

    def plot_request_flow(self, ax=None):
        """
        Рисует диаграмму Ганта для запросов:
          Пользователь → Кеш → Внешний источник
        """
        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 4))

        lane_y = {"user": 2, "cache": 1, "external": 0}
        height = 0.3

        # запросы к кешу
        for call in self.cache_calls:
            if call["key"] != self.resource:
                continue
            t0, t1 = call["start"], call["finish"]
            color = self.cache_colors.get(call["type"], "gray")
            ax.broken_barh(
                [(t0, t1 - t0)],
                (lane_y["cache"] - height / 2, height),
                facecolors=color, edgecolors="black"
            )
            ax.annotate(
                "",
                xy=(t0, lane_y["cache"]),
                xytext=(t0, lane_y["user"]),
                arrowprops=dict(arrowstyle="->", color=color)
            )

        # запросы к внешнему источнику
        for src in self.source_calls:
            if src["resource"] != self.resource:
                continue
            t0, t1 = src["start"], src["finish"]
            matching = next(
                (c for c in self.cache_calls
                 if c["key"] == src["resource"] and abs(c["start"] - t0) < 1e-6),
                None
            )
            color = self.cache_colors.get(matching["type"], "lightgray") if matching else "lightgray"
            ax.broken_barh(
                [(t0, t1 - t0)],
                (lane_y["external"] - height / 2, height),
                facecolors=color, edgecolors="black"
            )
            ax.annotate(
                "",
                xy=(t0, lane_y["external"]),
                xytext=(t0, lane_y["cache"]),
                arrowprops=dict(arrowstyle="->", color=color)
            )

        ax.set_ylim(-0.5, 2.5)
        ax.set_xlim(0, self.t_end)
        ax.margins(x=0)  # убрать отступы слева/справа
        ax.set_yticks([lane_y["user"], lane_y["cache"], lane_y["external"]])
        ax.set_yticklabels(["Пользователь", "Кэш", "Внешний источник"])
        ax.set_xlabel("Время")
        ax.set_title(f"Поток запросов для {self.resource}")

        # легенда по типам cache-ответов
        patches = [
            mpatches.Patch(color=self.cache_colors[k], label=self.cache_labels[k])
            for k in self.cache_colors
        ]
        ax.legend(handles=patches, bbox_to_anchor=(1.02, 1), loc="upper left")

        return ax

    def plot_version_timeline(self, ax=None):
        """
        Рисует две дорожки:
          Реальная версия (y=1) и версия в кеше (y=0) ресурса.
        Цвет каждого сегмента зависит от номера версии.
        """
        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 3))

        y_real, y_cache = 1, 0
        height = 0.4
        cmap = cm.get_cmap("tab20")

        # --- Реальная версия ---
        real_points = [{"time": 0.0, "new_version": 0}] + [
            u for u in self.real_updates if u["resource"] == self.resource
        ]
        real_points.append({"time": self.t_end, "new_version": real_points[-1]["new_version"]})

        for prev, curr in zip(real_points, real_points[1:]):
            t0 = prev["time"]
            t1 = curr["time"]
            v = prev["new_version"]
            ax.broken_barh(
                [(t0, t1 - t0)],
                (y_real - height / 2, height),
                facecolors=cmap(v % cmap.N), edgecolors="black"
            )

        # легенда реальных версий
        real_versions = sorted({p["new_version"] for p in real_points})
        patches_real = [
            mpatches.Patch(color=cmap(v % cmap.N), label=f"v={v}")
            for v in real_versions
        ]
        ax.legend(handles=patches_real,
                  title="Версии ресурса",
                  bbox_to_anchor=(1.02, 1),
                  loc="upper left")

        # --- Версия в кеше ---
        cache_updates = sorted(
            [c for c in self.cache_calls
             if c["key"] == self.resource and c["type"] == "miss"],
            key=lambda c: c["finish"]
        )

        if cache_updates:
            last_t = cache_updates[0]["finish"]
            last_v = cache_updates[0]["version"]
            for upd in cache_updates[1:]:
                t0 = last_t
                t1 = upd["finish"]
                ax.broken_barh(
                    [(t0, t1 - t0)],
                    (y_cache - height / 2, height),
                    facecolors=cmap(last_v % cmap.N), edgecolors="black"
                )
                last_t, last_v = t1, upd["version"]
            # последний сегмент до конца симуляции
            ax.broken_barh(
                [(last_t, self.t_end - last_t)],
                (y_cache - height / 2, height),
                facecolors=cmap(last_v % cmap.N), edgecolors="black"
            )

        ax.set_ylim(-0.5, 1.5)
        ax.set_xlim(0, self.t_end)
        ax.margins(x=0)  # убрать отступы слева/справа
        ax.set_yticks([y_real, y_cache])
        ax.set_yticklabels(["Реальная версия", "Версия в кеше"])
        ax.set_xlabel("Время")
        ax.set_title(f"Хронология версий для {self.resource}")

        return ax

    def show_all(self):
        """
        Выводит оба графика на одной фигуре.
        """
        fig = plt.figure(constrained_layout=True, figsize=(14, 8))
        gs = fig.add_gridspec(3, 1, height_ratios=[2, 1, 2])

        ax1 = fig.add_subplot(gs[0, 0])
        self.plot_request_flow(ax1)

        ax2 = fig.add_subplot(gs[1:, 0])
        self.plot_version_timeline(ax2)

        plt.show()
