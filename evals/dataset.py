"""Freeze PDF bytes/labels and their provenance before any provider call."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
import subprocess

from bill_lens.contract import ExpectedLabel
from bill_lens.pdf_text import PdfText, extract_pdf_text


@dataclass(frozen=True)
class Case:
    name: str
    document: PdfText
    label: ExpectedLabel
    label_sha256: str


def load_cases(root: Path) -> list[Case]:
    cases, seen = [], set()
    for path in sorted(root.glob("bill_*")):
        if not path.is_dir() or re.fullmatch(r"bill_[A-Za-z0-9_-]+", path.name) is None:
            raise ValueError("dataset case names must be bill_ followed by letters, digits, hyphens or underscores")
        pdf = (path / "bill.pdf").read_bytes()
        label = (path / "expected.json").read_bytes()
        document = extract_pdf_text(pdf)
        if document.file_sha256 in seen:
            raise ValueError("dataset contains duplicate PDF hashes")
        seen.add(document.file_sha256)
        cases.append(Case(path.name, document, ExpectedLabel.model_validate_json(label), sha256(label).hexdigest()))
    if not cases:
        raise ValueError("dataset must contain at least one bill_* case")
    return cases


def manifest(cases: list[Case]) -> dict:
    return {case.name: {"pdf_sha256": case.document.file_sha256, "label_sha256": case.label_sha256}
            for case in cases}


def git_revision(root: Path) -> dict:
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()
    try:
        return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}
