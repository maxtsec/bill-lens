"""Offline-only replay of preserved attempts; never constructs an extractor/client."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from bill_lens.extraction import build_attempt
from bill_lens.validation import derive_document_flags, derive_flags, derive_status
from evals import SCORING_VERSION
from evals.dataset import load_cases
from evals.scoring import score_attempt

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("docs/learning/evidence/retailer-brand-v4")


def build_evidence(root: Path = ROOT) -> dict:
    source = root / SOURCE
    manifest_bytes = (source / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    # Verify the original artifacts before using any saved model response.
    for name, expected in manifest["artifact_hashes"].items():
        content = (source / name).read_bytes()
        if len(content) != expected["bytes"] or sha256(content).hexdigest() != expected["sha256"]:
            raise ValueError(f"source artifact hash mismatch: {name}")
    cases = {c.name: c for folder in ("dataset", "dataset/holdout") for c in load_cases(root / folder)}
    per_run, changes = {}, []
    totals = dict(attempts=0, silent_false_acceptance_before=0, silent_false_acceptance_after=0,
                  new_false_reviews=0, flag_changes=0, status_changes=0)
    for role, run_id in manifest["run_ids"].items():
        summary = json.loads((source / role / "summary.json").read_bytes())
        rows = [json.loads(line) for line in (source / role / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
        if summary["run_id"] != run_id or summary["scoring_version"] != "1" or not summary["completed"]:
            raise ValueError("expected complete scoring-v1 source run")
        pairs = {(r["bill"], r["repeat"]) for r in rows}
        expected_pairs = {(name, repeat) for name in summary["dataset"] for repeat in range(1, summary["repeats"] + 1)}
        if len(rows) != len(pairs) or pairs != expected_pairs or len(rows) != summary["planned_attempts"]:
            raise ValueError("source attempt coverage mismatch")
        stats = dict.fromkeys(totals, 0)
        for row in rows:
            case = cases[row["bill"]]
            hashes = {"pdf_sha256": case.document.file_sha256, "label_sha256": case.label_sha256}
            if row["run_id"] != run_id or summary["dataset"][case.name] != hashes or any(row[k] != v for k, v in hashes.items()):
                raise ValueError("dataset or run identity mismatch")
            attempt = build_attempt(provider=row["provider"], model=row["resolved_model"],
                                    prompt_version=row["prompt_version"], raw_response=row["raw_response"],
                                    error_code=row["error_code"], latency_ms=row["latency_ms"],
                                    input_tokens=row["input_tokens"], output_tokens=row["output_tokens"])
            old_flags = sorted(derive_flags(attempt.fields)) if attempt.fields is not None else None
            old_status = derive_status(old_flags) if old_flags is not None else "failed"
            if (old_flags, old_status) != (row["flags"], row["status"]):
                raise ValueError("source decision does not match scoring-v1 field rules")
            scored = score_attempt(attempt, case.label, case.document)
            for name in ("predicted", "expected", "expected_flags", "expected_status", "field_outcomes", "supply_components", "exact_bill_match"):
                if row[name] != scored[name]:
                    raise ValueError(f"unexpected non-decision scoring change: {name}")
            added = sorted(derive_document_flags(attempt.fields, case.document)) if attempt.fields is not None else []
            flags_changed, status_changed = scored["flags"] != old_flags, scored["status"] != old_status
            stats["attempts"] += 1
            stats["silent_false_acceptance_before"] += int(row["expected_status"] == "needs_review" and old_status == "processed")
            stats["silent_false_acceptance_after"] += int(row["expected_status"] == "needs_review" and scored["status"] == "processed")
            stats["new_false_reviews"] += int(row["exact_bill_match"] and bool(added))
            stats["flag_changes"] += int(flags_changed)
            stats["status_changes"] += int(status_changed)
            if flags_changed or status_changed:
                changes.append({"run": role, "run_id": run_id, "bill": case.name, "repeat": row["repeat"],
                                "current_bill_amount": row["predicted"]["current_bill_amount"],
                                "document_flags": added, "flags_before": old_flags, "flags_after": scored["flags"],
                                "status_before": old_status, "status_after": scored["status"],
                                "flags_match_before": row["flags_match"], "flags_match_after": scored["flags_match"]})
        per_run[role] = stats
        for name in totals:
            totals[name] += stats[name]
    if totals["attempts"] != manifest["total_preserved_calls"] or totals["attempts"] != 88:
        raise ValueError("expected all 88 preserved attempts")
    implementation = ("bill_lens/document_validation.py", "bill_lens/validation.py",
                      "bill_lens/contract.py", "evals/scoring.py", "scripts/rescore_printed_values.py")
    return {"source_scoring_version": "1", "derived_scoring_version": SCORING_VERSION,
            "source_manifest_sha256": sha256(manifest_bytes).hexdigest(),
            "implementation_lf_sha256": {name: sha256((root / name).read_text(encoding="utf-8").encode("utf-8")).hexdigest() for name in implementation},
            "live_api_calls": 0, "per_run": per_run, "totals": totals, "changes": changes,
            "definitions": {"silent_false_acceptance": "expected needs_review, predicted processed",
                            "new_false_review": "original exact-bill-correct attempt now has a document-derived flag"}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new derived evidence file; refuses overwrite")
    args = parser.parse_args(argv)
    evidence = build_evidence()
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence["totals"]))


if __name__ == "__main__":
    main()
