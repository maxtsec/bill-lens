"""Export the synthetic PDFs' baseline text for a person to inspect."""

from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    output = ROOT / "tmp" / "extracted"
    output.mkdir(parents=True, exist_ok=True)
    for path in sorted((ROOT / "dataset").glob("bill_*/bill.pdf")):
        with pdfplumber.open(path) as pdf:
            text = "\n\n".join(page.extract_text() or "" for page in pdf.pages)
        target = output / f"{path.parent.name}.txt"
        target.write_text(text, encoding="utf-8")
        print(f"{path.parent.name}: {len(text)} characters -> {target.relative_to(ROOT)}")
