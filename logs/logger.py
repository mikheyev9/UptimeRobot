import os
import logging
from logging.handlers import TimedRotatingFileHandler

base_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(base_dir, 'uptime.log')

def setup_logger(log_file,  logger_name='uptime_monitor'):
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    handler = TimedRotatingFileHandler(log_file, when='midnight', interval=5, backupCount=5)
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    logger.addHandler(handler)
    return logger

logger = setup_logger(log_file)
