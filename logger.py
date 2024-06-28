import logging
from logging.handlers import TimedRotatingFileHandler

def setup_logger():
    logger = logging.getLogger('uptime_monitor')
    logger.setLevel(logging.INFO)

    handler = TimedRotatingFileHandler('uptime.log', when='midnight', interval=5, backupCount=1)
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    logger.addHandler(handler)
    return logger

logger = setup_logger()
