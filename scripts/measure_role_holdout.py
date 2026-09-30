"""Measure the preregistered role holdout once, offline, without changing rules."""

import argparse
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from bill_lens.current_amount_role import derive_current_amount_role_flags
from bill_lens.document_validation import derive_document_flags, printed_number_occurrences
from bill_lens.pdf_text import PageText, PdfText
from bill_lens.validation import derive_review_flags, derive_status
from evals.dataset import load_cases
from evals.role_cases import RoleCase


ROOT = Path(__file__).resolve().parents[1]
DATASET = Path("dataset/role-holdout")
PREDICTIONS = Path("docs/learning/evidence/role-holdout-predictions.json")
SAVED_EVIDENCE = Path("docs/learning/evidence/role-holdout-measurement.json")
CASE_NAMES = tuple(f"holdout_r{n:02}" for n in range(1, 11))
INPUT_FILES = ("bill.pdf", "expected.json", "role_cases.json")
ROLE_FLAG = "current_bill_amount_role_unconfirmed"
RULE_COMMIT = "940272e8cbefb07e9f2bce1bcacd0ec4f3415bbb"
DATASET_COMMIT = "1047d5e63ba839a66841fc7607a11ec05add3ea3"
PREDICTION_COMMIT = "9fc8131b7c9045005d30685c6d4848dea624db3a"
MEASUREMENT_COMMIT = "a8f5706"
FROZEN_INPUT_MANIFEST_SHA256 = "15334a4973dacc340c1bb93f02e04c8f24ec0c678544f8a3257ff7d8f31892e5"
FROZEN_PREDICTIONS_SHA256 = "a838d38303432a7a7f6cf6d42f2fae772f3a86b16e055f7860603723c7a35514"
IMPLEMENTATION_FILES = (
    "bill_lens/current_amount_role.py", "bill_lens/document_validation.py",
    "bill_lens/validation.py", "bill_lens/pdf_text.py", "bill_lens/contract.py",
    "evals/role_cases.py", "scripts/measure_role_holdout.py",
)
FROZEN_RULE_HASHES = {
    "bill_lens/current_amount_role.py": "669d09ca028f49568ddd326e8d6e6edeee2c0d428f8c55bd480d3de77ae1a575",
    "bill_lens/document_validation.py": "0f84cbe3f60d7178ca1360e9a6cbbb2cccf75a818505d50bd8ea58771e9b9430",
    "bill_lens/validation.py": "abc610d3b35f80becb6a1c3c4d02facbfc3eceb1610e3eb54c9bc0cc29f61301",
    "bill_lens/contract.py": "6d823380b78be113083abde3f87732c572daea9060bdafd7b3672e3f9c1fb4a7",
}


def _manifest(dataset: Path) -> tuple[dict, str]:
    found = {path.name for path in dataset.iterdir() if path.is_dir() and path.name.startswith("holdout_")}
    if found != set(CASE_NAMES):
        raise ValueError(f"missing or unexpected role-holdout case: {sorted(set(CASE_NAMES) ^ found)}")
    manifest = {}
    for name in CASE_NAMES:
        manifest[name] = {}
        for filename in INPUT_FILES:
            path = dataset / name / filename
            if not path.is_file():
                raise ValueError(f"missing input: {name}/{filename}")
            manifest[name][filename] = sha256(path.read_bytes()).hexdigest()
    digest = sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return manifest, digest


def _check_inputs(root: Path, dataset: Path, manifest: dict, digest: str) -> None:
    saved = root / SAVED_EVIDENCE
    if saved.is_file():
        reference = json.loads(saved.read_bytes())["input_hashes"]
        for name in CASE_NAMES:
            for filename in INPUT_FILES:
                if manifest[name][filename] != reference[name][filename]:
                    raise ValueError(f"input hash mismatch: {name}/{filename}")
    if digest != FROZEN_INPUT_MANIFEST_SHA256:
        raise ValueError("input manifest hash mismatch against owner-verified dataset")


def _occurrences(document: PdfText, value: str) -> list[dict]:
    """Record provenance with the shared tokenizer; do not recreate label windows."""
    wanted = Decimal(value)
    result = []
    for page in document.pages:
        previous_non_empty_line = ""
        for line_number, line in enumerate(page.text.splitlines(), 1):
            single_line = PdfText(document.file_sha256, (PageText(page.page_number, line),))
            for occurrence in printed_number_occurrences(single_line):
                if occurrence.value == wanted:
                    result.append({"page": page.page_number, "line_number": line_number,
                                   "line": line, "previous_non_empty_line": previous_non_empty_line})
            if line.strip():
                previous_non_empty_line = line
    return result


def _prediction_map(root: Path) -> tuple[dict, str]:
    raw = (root / PREDICTIONS).read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != FROZEN_PREDICTIONS_SHA256:
        raise ValueError("preregistered prediction hash mismatch")
    prediction = json.loads(raw)
    if prediction["rule_commit"] != "940272e" or prediction["dataset_commit"] != "1047d5e":
        raise ValueError("prediction provenance mismatch")
    cases = prediction["cases"]
    if len(cases) != len(CASE_NAMES) or {row["case_id"] for row in cases} != set(CASE_NAMES):
        raise ValueError("predictions do not cover exactly ten cases")
    if sum(row["correct"]["value"] is not None for row in cases) != 9 or sum(len(row["distractors"]) for row in cases) != 40:
        raise ValueError("predictions do not cover exactly 49 measured items")
    return {row["case_id"]: row for row in cases}, digest


def _implementation_hashes(root: Path) -> dict[str, str]:
    return {name: sha256((root / name).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            for name in IMPLEMENTATION_FILES}


def _check_implementation(root: Path, hashes: dict[str, str]) -> None:
    def refuse(name: str) -> None:
        raise ValueError(f"implementation fingerprint mismatch: {name}; saved evidence was measured "
                         f"at {MEASUREMENT_COMMIT} with the frozen rule. Reproduce from that commit; "
                         "do not regenerate the saved evidence")

    for name, frozen_hash in FROZEN_RULE_HASHES.items():
        if hashes[name] != frozen_hash:
            refuse(name)
    saved = root / SAVED_EVIDENCE
    if saved.is_file():
        recorded = json.loads(saved.read_bytes())["implementation_lf_sha256"]
        for name in IMPLEMENTATION_FILES:
            if hashes[name] != recorded[name]:
                refuse(name)


def _counters() -> dict:
    return {"correct_total": 0, "false_reviews": 0, "distractors_total": 0,
            "caught": 0, "missed": 0, "silent_false_acceptances": 0,
            "prediction_items": 0, "prediction_mismatches": 0}


def _add_counters(target: dict, source: dict) -> None:
    for key in target:
        target[key] += source[key]


def build_evidence(root: Path = ROOT, *, dataset: Path | None = None) -> dict:
    dataset = dataset or root / DATASET
    manifest, manifest_hash = _manifest(dataset)
    _check_inputs(root, dataset, manifest, manifest_hash)
    predictions, prediction_hash = _prediction_map(root)
    implementation_hashes = _implementation_hashes(root)
    _check_implementation(root, implementation_hashes)
    cases = {case.name: case for case in load_cases(dataset)}
    if set(cases) != set(CASE_NAMES):
        raise ValueError("case loader did not return exactly ten bills")

    per_case, per_shape, mismatches = [], {}, []
    totals = _counters()
    r07 = None
    for name in CASE_NAMES:
        case = cases[name]
        annotation = RoleCase.model_validate_json((dataset / name / "role_cases.json").read_bytes())
        prediction = predictions[name]
        if annotation.current_bill_amount != case.label.fields.current_bill_amount:
            raise ValueError(f"role_cases disagrees with expected.json: {name}/current_bill_amount")
        if annotation.shape != prediction["shape"] or annotation.current_bill_amount != prediction["correct"]["value"]:
            raise ValueError(f"prediction and label identity mismatch: {name}")
        if len(annotation.printed_distractors) != len(prediction["distractors"]):
            raise ValueError(f"prediction distractor count mismatch: {name}")
        if annotation.current_label is not None and annotation.current_label not in case.document.text:
            raise ValueError(f"current label absent from PDF text: {name}")

        stats = _counters()
        fields = case.label.fields
        role_flags = sorted(derive_current_amount_role_flags(fields, case.document))
        combined_flags = sorted(derive_review_flags(fields, case.document))
        status = derive_status(combined_flags)
        matches_label = combined_flags == case.label.expected_flags and status == case.label.expected_status
        correct_value = annotation.current_bill_amount
        correct_outcome = ("missing" if correct_value is None else
                           "confirmed" if matches_label else "false_review")
        correct_occurrences = [] if correct_value is None else _occurrences(case.document, correct_value)
        if correct_value is not None and not correct_occurrences:
            raise ValueError(f"correct amount absent from PDF text: {name}")
        correct_predicted = prediction["correct"]["predicted_outcome"]
        correct_match = correct_outcome == correct_predicted
        if correct_value is None:
            r07 = {"case_id": name, "role_flags": role_flags, "combined_flags": combined_flags,
                   "status": status, "matches_label": matches_label,
                   "prediction_match": correct_match}
        else:
            stats["correct_total"] += 1
            stats["false_reviews"] += int(not matches_label)
            stats["prediction_items"] += 1
            stats["prediction_mismatches"] += int(not correct_match)
            if not correct_match:
                mismatches.append({"case_id": name, "kind": "correct", "value": correct_value,
                                   "predicted": correct_predicted, "measured": correct_outcome})
        correct = {"value": correct_value, "predicted": correct_predicted,
                   "prediction_reason": prediction["correct"]["reason"], "measured": correct_outcome,
                   "prediction_match": correct_match, "occurrences": correct_occurrences,
                   "role_flags": role_flags, "combined_flags": combined_flags,
                   "status": status, "matches_label": matches_label}

        distractors = []
        for item, expected in zip(annotation.printed_distractors, prediction["distractors"], strict=True):
            if (item.value, item.printed_label) != (expected["value"], expected["printed_label"]):
                raise ValueError(f"prediction and role_cases distractor mismatch: {name}")
            if item.printed_label not in case.document.text:
                raise ValueError(f"distractor label absent from PDF text: {name}/{item.printed_label}")
            occurrences = _occurrences(case.document, item.value)
            if not occurrences:
                raise ValueError(f"distractor value absent from PDF text: {name}/{item.printed_label}")
            changed = fields.model_copy(update={"current_bill_amount": item.value})
            item_role_flags = sorted(derive_current_amount_role_flags(changed, case.document))
            presence_flags = sorted(derive_document_flags(changed, case.document))
            item_flags = sorted(derive_review_flags(changed, case.document))
            item_status = derive_status(item_flags)
            measured = "caught" if ROLE_FLAG in item_role_flags else "missed"
            predicted = expected["predicted_outcome"]
            prediction_match = predicted == measured
            stats["distractors_total"] += 1
            stats[measured] += 1
            stats["silent_false_acceptances"] += int(item_status == "processed")
            stats["prediction_items"] += 1
            stats["prediction_mismatches"] += int(not prediction_match)
            if not prediction_match:
                mismatches.append({"case_id": name, "kind": "distractor", "value": item.value,
                                   "printed_label": item.printed_label, "predicted": predicted,
                                   "measured": measured})
            distractors.append({"value": item.value, "printed_label": item.printed_label,
                                "role": item.role, "predicted": predicted,
                                "prediction_reason": expected["reason"], "measured": measured,
                                "prediction_match": prediction_match, "occurrences": occurrences,
                                "role_flags": item_role_flags, "presence_flags": presence_flags,
                                "combined_flags": item_flags, "status": item_status,
                                "silent_false_acceptance": item_status == "processed"})
        per_case.append({"case_id": name, "shape": annotation.shape,
                         "label_vocabulary": "n/a" if annotation.shape == "G" else
                         "out" if annotation.shape == "E" else "in",
                         "correct": correct, "distractors": distractors, "counts": stats})
        _add_counters(totals, stats)
        shape_counts = per_shape.setdefault(annotation.shape, _counters())
        _add_counters(shape_counts, stats)
    if totals["correct_total"] != 9 or totals["distractors_total"] != 40 or totals["prediction_items"] != 49:
        raise ValueError("measurement does not cover exactly 49 items")
    if r07 is None:
        raise ValueError("missing r07 null case")
    return {"schema_version": 1, "live_api_calls": 0, "rule_commit": RULE_COMMIT,
            "dataset_commit": DATASET_COMMIT, "prediction_commit": PREDICTION_COMMIT,
            "prediction_sha256": prediction_hash, "input_hashes": manifest,
            "input_manifest_sha256": manifest_hash,
            "implementation_lf_sha256": implementation_hashes,
            "per_case": per_case, "per_shape": dict(sorted(per_shape.items())),
            "totals": totals, "r07_decision": r07, "prediction_mismatches": mismatches,
            "definitions": {"false_review": "correct non-null amount has flags/status different from handwritten field/presence ground truth",
                            "missed_distractor": "annotated non-current value did not get the role flag",
                            "silent_false_acceptance": "distractor substitution produced processed status"}}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new evidence file; never overwritten")
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(args.output)
    evidence = build_evidence()
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(evidence["totals"], sort_keys=True))


if __name__ == "__main__":
    main()
