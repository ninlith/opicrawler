"""Logging configuration."""

import logging
import logging.config
import operator
import re
import time
import stamina
from rich.logging import RichHandler


class OpenAILogMonitor(logging.Handler):
    """Capture log messages containing OpenAI HTTP response headers."""

    def __init__(self, total):
        super().__init__()
        self.counter = 0
        self.total = total
        self.processing_times = []
        self.request_ids = []
        self.timestamp = time.time()
        self.logger = logging.getLogger(__name__)
        httpcore_logger = logging.getLogger("httpcore.http11")
        httpcore_logger.addHandler(self)

    def emit(self, record):
        log_message = self.format(record)
        if "x-ratelimit-remaining-tokens" in log_message:
            self.counter += 1
            if self.counter in [1, self.total] or (time.time() - self.timestamp > 10):
                self.timestamp = time.time()
                matches = re.findall(r"b'([^']+)'\s*,\s*b'([^']+)'", log_message)
                header = dict(matches)
                try:
                    self.processing_times.append(int(header["openai-processing-ms"]))
                    self.request_ids.append(header["x-request-id"])
                    mean_delay = sum(self.processing_times)/len(self.processing_times)
                    max_delay_index, max_delay = max(enumerate(self.processing_times),
                                                     key=operator.itemgetter(1))
                    max_delay_request_id = self.request_ids[max_delay_index]
                    self.logger.info(
                        f'({self.__class__.__name__}) '
                        f'tokens remaining: {header["x-ratelimit-remaining-tokens"]}/'
                        f'{header["x-ratelimit-limit-tokens"]} '
                        f'(reset: {header["x-ratelimit-reset-tokens"].replace("ms", " ms")}), '
                        f'requests remaining: {header["x-ratelimit-remaining-requests"]}/'
                        f'{header["x-ratelimit-limit-requests"]} '
                        f'(reset: {header["x-ratelimit-reset-requests"].replace("ms", " ms")}), '
                        f'mean processing time: {round(mean_delay/1000)} s '
                        f'(max: {round(max_delay/1000)} s)'
                    )
                    self.logger.debug(
                        f'max processing time x-request-id: {max_delay_request_id}'
                    )
                except (KeyError, NameError) as exc:
                    logging.getLogger(__name__).error(exc)


class _CustomRichHandler(RichHandler):
    """Disable line numbers and replace pathname with name."""

    def emit(self, record):
        original_lineno = record.lineno
        original_pathname = record.pathname
        record.lineno = 0
        record.pathname = record.name
        try:
            super().emit(record)
        finally:
            record.lineno = original_lineno
            record.pathname = original_pathname


def setup_logging(loglevel, log_path):
    """Set up logging configuration."""
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "f": {
                "format": "%(asctime)s %(name)s:%(lineno)d: [%(levelname)s] %(message)s",
                "datefmt": "%F %T",
            },
            "rf": {
                "format": "%(message)s",
                "datefmt": "%F %T",
            },
        },
        "handlers": {
            "rich": {
                "class": "opicrawler.logging._CustomRichHandler",
                "formatter": "rf",
                "level": loglevel,
            },
            "fh": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "filename": log_path,
                "when": "H",
                "backupCount": 10,
                "formatter": "f",
                "level": "DEBUG",
            },
        },
        "root": {
            "handlers": ["rich", "fh"],
            "level": "DEBUG",
        },
    }
    logging.config.dictConfig(logging_config)

    # Configure stamina.
    # https://github.com/hynek/stamina/blob/main/src/stamina/instrumentation/_logging.py
    def log_retries(details) -> None:
        stamina_logger = logging.getLogger("stamina")
        args = ", ".join(repr(a) for a in details.args)
        kwargs = dict(details.kwargs.items())
        invoker = details.name
        caused_by = repr(details.caused_by)
        wait_for = round(details.wait_for, 2)
        retry_num = details.retry_num
        stamina_logger.debug(
            f"Retrying due to {caused_by} in {wait_for} seconds. "
            f"{retry_num = }, {invoker = }, {args = }, {kwargs = }"
        )
    stamina.instrumentation.set_on_retry_hooks([log_retries])

    # Configure httpx.
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.propagate = False
