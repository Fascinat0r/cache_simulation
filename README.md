## 1. Основные компоненты и их классы

1. **Моделирование окружения (SimPy Environment)**

    * **`Simulator`**
      • Инициализирует SimPy–среду, orchestr-методы для запуска сценариев, сбор результатов.
      • Паттерн «Фасад»: скрывает детали настройки и запуска разных сценариев.

2. **Внешний источник данных («чёрный ящик»)**

    * **`ExternalSource`** (см. предыдущий файл)
      • Симулирует M/G/1–поток: очередь, время обслуживания, фоновая генерация обновлений.
      • Логгирование событий.

3. **Кеш–слой**

    * **`Cache`**
      • Хранит записи (в виде `dict[key] = CacheEntry`).
      • Декоратор для `request`: проверка наличия и актуальности, иначе MISS.

    * **`CacheEntry`**
      • Содержит значение, версию внешних данных, timestamp последнего обновления, TTL-параметры.

4. **Стратегии инвалидации**

   ```text
   CacheStrategy        ← абстрактный базовый класс (паттерн Strategy)
   ├─ FixedTTLStrategy     (фиксированный TTL)
   ├─ AdaptiveTTLStrategy  (динамический TTL на основе метрик)
   └─ HybridStrategy        (реактивно-предиктивный подход)
   ```

   Каждый подкласс реализует метод

   ```python
   def is_valid(self, entry: CacheEntry, now: float) -> bool
   def on_update(self, entry: CacheEntry, metrics: Metrics) -> None
   ```

   и, при необходимости, метод фонового обновления.

5. **Клиентские процессы**

    * **`ClientGenerator`**
      • Порождает процессы–клиенты с заданным законом прихода (пуассон, пиковые интервалы и т. д.).
      • Каждый клиент вызывает `Cache.request(key)`.

6. **Сбор и анализ метрик**

    * **`MetricsCollector`**
      • Собирает времена ожидания, hit/miss, staleness, число обращений к `ExternalSource`.
      • Экспорты в CSV/JSON для последующего анализа.

7. **Конфигурация и фабрики**

    * **`Config`** (или YAML/JSON)
      • Параметры симуляции: λ<sub>u</sub>, λ<sub>upd</sub>, диапазон сервис–таймов, интервалы генерации запросов,
      параметры стратегий.
    * **`Factory`**
      • Строит компоненты по конфигу: `Simulator`, `ExternalSource`, `Cache` с нужной стратегией.

8. **Утилиты и логгирование**

    * **`logger.py`**
      • Единый настроенный логгер для всех модулей.
    * **`utils.py`**
      • Общие функции (генераторы случайных потоков, вспомогательные расчёты).

---

## 2. Предлагаемая структура проекта

```
cache_simulation/
├── README.md
├── pyproject.toml       # зависимости, метаданные проекта
├── config/
│   └── default.yaml     # конфигурации сценариев
├── cache_simulation/
│   ├── __init__.py
│   ├── logger.py
│   ├── utils.py
│   ├── config.py        # загрузка YAML → объект Config
│   ├── simulator.py     # класс Simulator (Facade)
│   ├── external_source.py  # класс ExternalSource
│   ├── cache.py         # классы Cache, CacheEntry
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py          # CacheStrategy
│   │   ├── fixed_ttl.py     # FixedTTLStrategy
│   │   ├── adaptive_ttl.py  # AdaptiveTTLStrategy
│   │   └── hybrid.py         # HybridStrategy
│   ├── client.py         # ClientGenerator
│   └── metrics.py        # MetricsCollector
├── scripts/
│   ├── run_simulation.py  # точка входа: парсит args, вызывает Simulator
│   └── analyze_results.py # Jupyter-style анализ метрик
└── tests/
    ├── __init__.py
    ├── test_external_source.py
    ├── test_cache_strategies.py
    └── test_simulator.py
```

### Описание файлов и модулей

* **`README.md`** — общая документация, примеры запуска.
* **`pyproject.toml`** — зависимости: `simpy`, `pyyaml`, `pandas`, `matplotlib`, `pytest` и т. д.
* **`config/default.yaml`** —

  ```yaml
  simulator:
    sim_time: 1000
    arrival_rate: 0.2
  external_source:
    min_service: 3.0
    max_service: 10.0
    update_rate: 0.05
  cache:
    strategy: fixed_ttl
    fixed_ttl:
      ttl: 60
    adaptive_ttl:
      theta: 1.0
    hybrid:
      k: 0.1
      delta: 5
  ```
* **`cache_simulation/logger.py`** — централизованная настройка Python-логгера (файловый и консольный хендлеры, уровни).
* **`cache_simulation/utils.py`** — вспомогательные функции для генерации пуассоновских и других потоков,
  seed-менеджмент.
* **`cache_simulation/config.py`** — читает YAML и создаёт объект `Config`, валидирует поля.
* **`cache_simulation/simulator.py`** —

  ```python
  class Simulator:
      def __init__(self, config: Config):
          self.env = simpy.Environment()
          self.metrics = MetricsCollector()
          self.source = ExternalSource(self.env, ...)
          self.cache = Cache(self.source, strategy=...)
          self.client_gen = ClientGenerator(self.env, self.cache, ...)
      def run(self):
          # запуск, сбор metrics, экспорт
  ```
* **`cache_simulation/external_source.py`** — класс `ExternalSource` с SimPy Resource + update generator.
* **`cache_simulation/cache.py`** —

  ```python
  class CacheEntry:
      ...
  class Cache:
      def __init__(self, source: ExternalSource, strategy: CacheStrategy):
          self.source = source
          self.strategy = strategy
          self.store: Dict[key, CacheEntry] = {}
      def request(self, key):
          # check hit/miss, call source.request(), update entry, metrics
  ```
* **`cache_simulation/strategies/base.py`** — абстрактный класс `CacheStrategy` с
  методами `is_valid`, `on_access`, `on_update`.
* **`cache_simulation/strategies/fixed_ttl.py`** — конкретная стратегия с полем `ttl`.
* **`cache_simulation/strategies/adaptive_ttl.py`** — стратегия с параметрами `theta`, `c_miss`, `c_stale` и методами
  расчёта нового TTL.
* **`cache_simulation/strategies/hybrid.py`** — комбинированная стратегия с триггером `P_pred`, фоновыми выборками.
* **`cache_simulation/client.py`** — `ClientGenerator`, генерирует события по заданному закону и
  вызывает `cache.request(key)`.
* **`cache_simulation/metrics.py`** — класс `MetricsCollector` для регистрации и выгрузки метрик (через
  pandas.DataFrame).
* **`scripts/run_simulation.py`** — CLI-инструмент: парсинг аргументов, выбор конфига, инициализация и
  запуск `Simulator`.
* **`scripts/analyze_results.py`** — вспомогательный скрипт или Jupyter-ноутбук для визуализации CSV-метрик.
* **`tests/`** — модульные тесты для каждого компонента с использованием `pytest` (моки SimPy, фикстуры конфигурации).

---

**Почему так?**

* Разделение на модули **по ответственности** (Single Responsibility Principle).
* **Strategy** для добавления/переподключения новых алгоритмов инвалидации без правки кода `Cache`.
* **Facade** (`Simulator`) для упрощения работы с несколькими компонентами.
* **Factory-подход** через `config.py` + YAML для гибкости параметризации сценариев.
* **Логгирование** и **метрики** вынесены в отдельные модули для единого контроля.
* **Тестирование** каждого класса гарантирует надёжность и облегчает рефакторинг.

Такой дизайн обеспечит расширяемость (легко добавить новую стратегию), тестируемость (раздельные модули) и удобство
эксплуатации (скрипты, конфиг).
