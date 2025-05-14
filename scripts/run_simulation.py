# scripts/run_simulation.py

import argparse
import sys

from cache_simulation.config import Settings
from cache_simulation.logger import setup_logging, get_logger
from cache_simulation.simulator import Simulator

logger = get_logger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Запуск DES-симуляции кеширования с заданным конфигом"
    )
    parser.add_argument(
        "-c", "--config",
        metavar="PATH",
        type=str,
        default=None,
        help="Путь до YAML-конфига (по умолчанию: CONFIG_PATH или config/default.yaml)"
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Не экспортировать метрики в файл"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Загрузка конфига
    settings = Settings.load(path=args.config)

    # Настройка логирования (файл + консоль) сразу, т.к. внутри Simulator тоже вызывается setup_logging
    setup_logging(settings)
    logger.info("Loaded settings and configured logging")

    # Инициализация симулятора
    sim = Simulator(settings)

    # Запуск симуляции
    sim.run()

    # Печать сводки по метрикам
    summary = sim.metrics.summary()
    print("\n=== Simulation Metrics Summary ===")
    for k, v in summary.items():
        print(f"{k:20}: {v}")

    if args.no_export:
        logger.info("Skipping metrics export (--no-export)")
    else:
        out_path = getattr(settings, "output", {}).get("path", None)
        if out_path:
            logger.info(f"Metrics were exported to {out_path}(.json/.csv)")
        else:
            logger.warning("No output.path in config; nothing was exported")

    return 0


if __name__ == "__main__":
    sys.exit(main())
