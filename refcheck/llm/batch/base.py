"""
Shared types for batch backends. Anthropic's Batch API and Bedrock's
batch inference API work very differently under the hood (inline
request list + poll/retrieve vs. S3 files + a job resource), but both
backends expose the same shape here -- BatchItem in, BatchItemResult
out, submit/wait/fetch/run_batch_sync functions -- so
pipelines/batch_runner.py can select either one without changing its
own code beyond which module it imports.
"""

from dataclasses import dataclass, field
from typing import Optional, Type

from pydantic import BaseModel


@dataclass
class BatchItem:
    """One request to include in a batch. `custom_id` is yours to
    define -- use it to map results back to whatever you're processing.
    Must be unique within a batch."""
    custom_id: str
    system: str
    user_message: str
    output_model: Type[BaseModel]
    model: str
    max_tokens: int = field(default=None)


@dataclass
class BatchItemResult:
    custom_id: str
    success: bool
    value: Optional[BaseModel] = None
    error: Optional[str] = None


class BatchError(RuntimeError):
    pass
