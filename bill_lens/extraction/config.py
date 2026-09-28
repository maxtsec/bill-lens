"""Select the adapter at startup; constructing the SDK does not send requests."""

import os
from pathlib import Path

from .fake import FakeExtractor
from .openai_adapter import OpenAIExtractor
from .port import BillExtractor


def configured_extractor() -> BillExtractor:
    provider = os.environ.get("BILL_EXTRACTOR", "fake")
    if provider == "fake":
        return FakeExtractor.from_dataset(Path(os.environ.get("BILL_DATASET_ROOT", "dataset")))
    if provider == "openai":
        return OpenAIExtractor(model=os.environ.get("OPENAI_MODEL", ""),
                               api_key=os.environ.get("OPENAI_API_KEY"))
    raise ValueError("BILL_EXTRACTOR must be fake or openai")
