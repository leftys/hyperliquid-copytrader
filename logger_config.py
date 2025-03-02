import logging
import os
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration


def setup_logging(service_name):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(levelname)5s| %(message)s')

    # Configure Sentry
    sentry_dsn = os.getenv('SENTRY_DSN', '')
    if sentry_dsn:
        sentry_logging = LoggingIntegration(
            level=logging.INFO,        # Capture info and above as breadcrumbs
            event_level=logging.ERROR  # Send errors as events
        )
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[sentry_logging],
            traces_sample_rate=1.0,
            environment=os.getenv('ENVIRONMENT', 'production'),
            release=os.getenv('RELEASE'),
            server_name=os.getenv('PROFILE', ''),
            enable_tracing=True
        )
    else:
        logging.info("Sentry is disabled")

    # Configure logging - using default handlers
    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)
    return logger
