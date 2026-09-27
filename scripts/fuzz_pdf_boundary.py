"""Mutation fuzzing for bill_lens.pdf_text.extract_pdf_text.

Reproduces the PR #3 review runs exactly (same RNG call order as the original
ad-hoc script). The review used two runs, 9,000 cases in total:

    python fuzz_pdf_boundary.py --seed 1 --cases 3000
    python fuzz_pdf_boundary.py --seed 7 --cases 6000

Run from the repository root with the project venv. Case generation depends on
the bytes of dataset/bill_001..005/bill.pdf and on Python's `random` module, so
keep both fixed when comparing before/after results.
"""

import argparse
import collections
import csv
import hashlib
import logging
import random
from pathlib import Path

from bill_lens.pdf_text import PdfTextError, extract_pdf_text


def generate_cases(seed: int, count: int, sources: list[bytes]):
    rng = random.Random(seed)
    for i in range(count):
        data = bytearray(rng.choice(sources))
        mode = i % 3
        if mode == 0:  # overwrite 1-20 random bytes after the %PDF- prefix
            for _ in range(rng.randint(1, 20)):
                position = rng.randrange(5, len(data))
                data[position] = rng.randrange(256)
        elif mode == 1:  # truncate
            data = data[:rng.randrange(6, len(data))]
        else:  # splice a copy of a random chunk into a random position
            a = rng.randrange(5, len(data))
            b = rng.randrange(5, len(data))
            data[a:a] = data[b:b + rng.randint(1, 200)]
        yield i, ("flip", "truncate", "splice")[mode], bytes(data)


def classify(data: bytes) -> str:
    try:
        extract_pdf_text(data)
        return "ok"
    except PdfTextError as error:
        return f"PdfTextError:{error.code}"
    except Exception as error:  # noqa: BLE001 - the point is to find escapes
        return f"ESCAPED {type(error).__module__}.{type(error).__name__}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--cases", type=int, required=True)
    parser.add_argument("--outcomes", type=Path, help="write per-case CSV for before/after diffs")
    parser.add_argument("--dump-escaped", type=Path, help="directory to save escaped cases as .pdf")
    args = parser.parse_args()

    logging.disable(logging.CRITICAL)  # pdfminer warnings are noise here
    sources = [Path(f"dataset/bill_00{n}/bill.pdf").read_bytes() for n in range(1, 6)]
    counts: collections.Counter[str] = collections.Counter()
    rows = []
    if args.dump_escaped:
        args.dump_escaped.mkdir(parents=True, exist_ok=True)

    for index, mode, data in generate_cases(args.seed, args.cases, sources):
        outcome = classify(data)
        counts[outcome] += 1
        digest = hashlib.sha256(data).hexdigest()
        rows.append((args.seed, index, mode, digest, outcome))
        if outcome.startswith("ESCAPED") and args.dump_escaped:
            (args.dump_escaped / f"seed{args.seed}_case{index:05}.pdf").write_bytes(data)

    for outcome, count in counts.most_common():
        print(f"{count:5d}  {outcome}")
    escaped = sum(v for k, v in counts.items() if k.startswith("ESCAPED"))
    print(f"\nseed={args.seed} cases={args.cases} escaped={escaped}")

    if args.outcomes:
        with args.outcomes.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["seed", "case", "mode", "sha256", "outcome"])
            writer.writerows(rows)


if __name__ == "__main__":
    main()
