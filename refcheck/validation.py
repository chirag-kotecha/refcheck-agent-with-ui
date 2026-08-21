"""
Input validation for reference check inputs. Two concerns kept separate:
1. Basic sanity checks (length bounds) -- fail fast with a clear error.
2. A lightweight heuristic flag for text that looks like prompt
   injection -- logs a warning, does NOT block. The actual defense is
   the prompt wording in prompts.py.
"""

import re

from refcheck.logging_config import get_logger
from refcheck import config

logger = get_logger(__name__)

_INJECTION_PATTERNS = [
    re.compile(r"ignore (all )?(previous|prior|above) instructions", re.I),
    re.compile(r"you are now", re.I),
    re.compile(r"system prompt", re.I),
    re.compile(r"disregard (the )?(rules|guidelines)", re.I),
]


class ValidationError(ValueError):
    pass


def validate_raw_input(raw_input: str, *, context: str = "") -> None:
    if not raw_input or len(raw_input.strip()) < config.MIN_RAW_INPUT_CHARS:
        raise ValidationError(
            f"raw_input is too short (min {config.MIN_RAW_INPUT_CHARS} chars)"
            f"{' for ' + context if context else ''}."
        )
    if len(raw_input) > config.MAX_RAW_INPUT_CHARS:
        raise ValidationError(
            f"raw_input exceeds max length ({config.MAX_RAW_INPUT_CHARS} chars)"
            f"{' for ' + context if context else ''}. Truncate or split it upstream."
        )
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(raw_input):
            logger.warning(
                f"possible prompt-injection pattern matched in raw_input "
                f"({context or 'unknown context'}); proceeding, model is "
                f"instructed to treat this as untrusted data"
            )
            break
