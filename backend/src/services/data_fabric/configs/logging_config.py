"""Logging setup module."""

import logging
import logging.config
import yaml
import os


def setup_logging(config_file: str = "logs/config.yaml") -> None:
    """Setup logging configuration.

    Args:
        config_file: Path to logging configuration file
    """
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
            logging.config.dictConfig(config)
    else:
        # Default logging setup
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    logger = logging.getLogger(__name__)
    logger.info("Logging initialized")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
