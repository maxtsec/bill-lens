"""Run sequential extraction evaluations; live calls require two explicit gates."""

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import sys
from uuid import uuid4

from bill_lens.extraction import BillExtractor, FakeExtractor, ScriptedResponse
from bill_lens.extraction.openai_adapter import OpenAIConfigurationError, OpenAIExtractor, REASONING_EFFORT
from . import HARNESS_VERSION, LIMITATION, SCORING_VERSION
from .dataset import Case, git_revision, load_cases, manifest
from .pricing import PRICE_DATE, PRICES, estimate_cost, planned_cost
from .reporting import render_report, summarize
from .scoring import score_attempt

ROOT = Path(__file__).resolve().parents[1]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_metadata(cases, dataset, extractor, *, provider, model, repeats, run_id, plan):
    return {"run_id": run_id, "harness_version": HARNESS_VERSION, "scoring_version": SCORING_VERSION,
            "started_at": now(), "git": git_revision(ROOT), "dataset_git": git_revision(dataset),
            "dataset": manifest(cases), "bill_count": len(cases), "repeats": repeats,
            "planned_attempts": len(cases) * repeats, "provider": provider, "requested_model": model,
            "configured_prompt_version": extractor.prompt_version,
            "reasoning_effort": REASONING_EFFORT if provider == "openai" else None,
            "price_date": PRICE_DATE, "plan": plan,
            "runtime": {"python": platform.python_version(),
                        "packages": {name: version(name) for name in ("pydantic", "pdfplumber", "pdfminer.six", "openai")}}}


def evaluate(cases: list[Case], extractor: BillExtractor, output: Path, metadata: dict) -> dict:
    """Use the production port. Adapters themselves call build_attempt.

    Write each completed attempt immediately, including exact raw text as JSON
    escapes. If configuration/programming errors raise, retain a marked partial
    report and re-raise; never manufacture a failed attempt for an unmade call.
    """
    repeats = metadata["repeats"]
    if type(repeats) is not int or repeats < 1 or not cases:
        raise ValueError("evaluation needs cases and positive integer repeats")
    if metadata["dataset"] != manifest(cases) or metadata["planned_attempts"] != len(cases) * repeats:
        raise ValueError("metadata must describe the evaluated cases and repeats")
    output.mkdir(parents=True, exist_ok=False)
    records, completed, abort_reason = [], False, None
    with (output / "attempts.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        try:
            for repeat in range(1, repeats + 1):
                for case in cases:
                    attempt = extractor.extract(case.document)
                    cost = (estimate_cost(metadata["requested_model"], attempt.model,
                                          attempt.input_tokens, attempt.output_tokens)
                            if metadata["provider"] == "openai" else 0)
                    record = {"run_id": metadata["run_id"], "bill": case.name, "repeat": repeat,
                              "recorded_at": now(), **metadata["dataset"][case.name],
                              "provider": attempt.provider, "requested_model": metadata["requested_model"],
                              "resolved_model": attempt.model, "prompt_version": attempt.prompt_version,
                              "reasoning_effort": metadata["reasoning_effort"],
                              "error_code": attempt.error_code, "raw_response": attempt.raw_response,
                              "input_tokens": attempt.input_tokens, "output_tokens": attempt.output_tokens,
                              "latency_ms": attempt.latency_ms, "price_date": PRICE_DATE,
                              "estimated_cost_usd": str(cost) if cost is not None else None,
                              **score_attempt(attempt, case.label)}
                    # ensure_ascii preserves literal NUL/lone surrogates losslessly.
                    stream.write(json.dumps(record, ensure_ascii=True) + "\n")
                    stream.flush()
                    records.append(record)
            completed = True
        except Exception as error:
            abort_reason = (f"OpenAIConfigurationError:{error.reason}"
                            if isinstance(error, OpenAIConfigurationError) else type(error).__name__)
            raise
        finally:
            summary = summarize(metadata, records, completed=completed, abort_reason=abort_reason)
            (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
            (output / "report.md").write_text(render_report(summary), encoding="utf-8")
    return summary


def positive_integer(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extractor", choices=("fake", "openai"), required=True)
    parser.add_argument("--model", choices=list(PRICES))
    parser.add_argument("--repeats", type=positive_integer, default=1)
    parser.add_argument("--dataset", type=Path, default=ROOT / "dataset")
    parser.add_argument("--output", type=Path, help="new output directory; existing paths are never overwritten")
    args = parser.parse_args(argv)
    if args.extractor == "openai":
        if os.environ.get("BILL_LENS_LIVE") != "1" or not os.environ.get("OPENAI_API_KEY", "").strip():
            parser.error("openai requires BILL_LENS_LIVE=1 and OPENAI_API_KEY; this spends credit")
        if args.model is None:
            parser.error("openai requires an explicit --model from the dated price table")
    elif args.model is not None:
        parser.error("--model applies only to openai; fake uses fake-v1")
    cases = load_cases(args.dataset)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12]
    output = args.output if args.output is not None else ROOT / "evals/results" / run_id
    if output.exists():
        parser.error("output directory already exists; choose a new directory")
    model = args.model if args.extractor == "openai" else FakeExtractor.model
    plan = (planned_cost(cases, args.repeats, model) if args.extractor == "openai" else
            {"planned_calls": 0, "planned_attempts": len(cases) * args.repeats, "estimated_cost_usd": "0", "price_date": PRICE_DATE})
    print(LIMITATION, flush=True)
    print(json.dumps({"provider": args.extractor, "model": model, "bills": len(cases),
                      "repeats": args.repeats, "output": str(output), **plan}), flush=True)
    # Plan and both live gates precede client construction. Use the frozen labels
    # for fake responses so changes on disk cannot escape the recorded hashes.
    extractor = (OpenAIExtractor(model=model, api_key=os.environ["OPENAI_API_KEY"])
                 if args.extractor == "openai" else FakeExtractor({
                     case.document.file_sha256: ScriptedResponse(case.label.fields.model_dump_json()) for case in cases}))
    try:
        metadata = make_metadata(cases, args.dataset, extractor, provider=args.extractor,
                                 model=model, repeats=args.repeats, run_id=run_id, plan=plan)
        evaluate(cases, extractor, output, metadata)
    except OpenAIConfigurationError as error:
        print(f"Evaluation stopped: {error.reason}. Partial results: {output}", file=sys.stderr)
        return 1
    finally:
        if args.extractor == "openai":
            extractor.close()
    print(f"Report: {output / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
