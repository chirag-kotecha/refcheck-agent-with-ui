"""
Structured logging setup with a PII-scrubbing filter. Minimal
implementation -- swap `logging` for `structlog` for richer output, or
point the handler at your log aggregator instead of stdout.
"""

import logging
import re
import sys

_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_LONG_DIGIT_PATTERN = re.compile(r"\b\d{9,}\b")
_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


class PIIScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        scrubbed = _SSN_PATTERN.sub("[REDACTED-SSN]", msg)
        scrubbed = _LONG_DIGIT_PATTERN.sub("[REDACTED-NUM]", scrubbed)
        scrubbed = _EMAIL_PATTERN.sub("[REDACTED-EMAIL]", scrubbed)
        if scrubbed != msg:
            record.msg = scrubbed
            record.args = ()
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt='{"ts":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","msg":"%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    handler.addFilter(PIIScrubFilter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
