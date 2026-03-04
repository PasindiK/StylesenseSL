import logging
import os
from datetime import datetime

# Determine repository root (one level above scripts/) and create logs dir there
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)


def setup_logger(name, log_file='lakehouse_component.log'):
    """Setup logging configuration"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # File handler - saves logs to file in repo-root `logs/`
    log_path = os.path.join(LOGS_DIR, log_file)
    try:
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.DEBUG)
    except Exception:
        # Fall back to no file handler if the path cannot be used
        file_handler = None

    # Console handler - prints logs to screen
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Formatter - how the log messages look
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    if file_handler:
        file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers to logger
    if not logger.handlers:  # Avoid duplicate handlers
        if file_handler:
            logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger

# Example usage
if __name__ == "__main__":
    logger = setup_logger(__name__)
    logger.info("Logger initialized successfully")
    logger.warning("This is a warning")
    logger.error("This is an error")