import logging
import sys

def setup_logging(level=logging.INFO):
    """Настраивает базовое логирование (вызывается один раз при старте)."""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=level,
        handlers=[logging.StreamHandler(sys.stdout)]
    )