# Pre-registered live v4 role-holdout analysis (D1)

Status: preparation only; no live result exists in this PR. Review and merge
this plan, budget guard and analysis script before the owner runs anything.

## Authorised owner run

- One sequential run on `dataset/role-holdout`: ten synthetic bills, three
  repeats each, at most **30 calls**. No retries or automatic resume/rerun.
- `gpt-5.4-mini`, `extract-v4`, low reasoning effort, 4096 output-token cap,
  SDK retries zero and the existing adapter settings.
- **US$0.30 cap**. Historical usage suggests about US$0.06, but that is not a
  guarantee. A budget stop leaves a partial run; only Max can authorise a rerun.
- Max runs with his own key from a clean main checkout after D1 merges.
  Codex makes no live call and does not receive or inspect the key.

This set was already measured offline against the frozen role heuristic. It
has not yet been evaluated with this model/prompt. Repeats expose model
variability, not additional independent documents.

## Questions and fixed definitions

Does the model choose printed non-current amounts on these layouts? How many
wrong numeric choices reach review, and what review cost does the role rule
impose on correct numeric choices?

The [analysis script](../../scripts/analyse_role_holdout_live.py) verifies all
30 PDF/label/role-annotation hashes against the byte-locked
[PR C evidence](evidence/role-holdout-measurement.json), as well as the frozen
rule/reader/schema fingerprints. It verifies the v4 prompt SHA-256
`3c6762fc560688769faa74c2866b719beeccf047986f3765929873e0a575a02a`, clean
run provenance, run/attempt settings, sequential coverage, budget ledger and
recorded scoring by rebuilding each attempt from the raw response. It never
rewrites a source artifact. Complete runs need 30 unique bill/repeat pairs;
partial runs must be an ordered prefix and remain labelled partial.

Each schema-valid amount is assigned exactly one category, using Decimal:

1. `correct`: non-null value equals the handwritten printed current amount.
2. `null`: a schema-valid null, correct only on r07.
3. `distractor:<role>`: equals an annotated distractor. Credit matches include
   both its signed value and its positive magnitude; record `signed` or
   `unsigned_magnitude`. Keep all matches if roles share a value.
4. `other_wrong`: another numeric value. Signed printed occurrences and the
   existing presence/role flags distinguish printed from unprinted values.

Failed/schema-invalid attempts are separately `no_fields`, not null answers.
They stay in the denominator. `incorrect_current` includes missing/null and
failed answers on bills with a printed current amount. `wrong_value` means a
**non-null schema-valid numeric value** different from the handwritten answer;
it includes a non-null value on r07. Missing answers are not invented numeric
mistakes and are reported separately.

- **Caught:** wrong numeric value and final `needs_review`.
- **Silent false acceptance:** wrong numeric value and final `processed`.
- **False review due to the role rule:** correct non-null current amount and
  `current_bill_amount_role_unconfirmed`. Other field errors are reported
  separately; this is narrower than PR C's combined-decision false-review
  definition. A correct amount does not imply that the whole bill is correct.

Report counts per attempt, bill, shape and overall. The full planned split is
**27** attempts on nine bills with a printed current amount, plus **r07's 3**.
Partial reports show observed and planned counts separately and use observed
denominators for measured outcomes, without calling absent attempts failures.
Other fields' correctness is separate from current-amount analysis.

For r07, explicitly report null, annotated amount due **112.20**, other
distractors and reconstructable-but-unprinted **87.20**. The latter remains
`other_wrong`; inference or arithmetic cannot make it a printed fact.
Record every matching numeric occurrence's page, line number and line text
using the shared tokenizer, plus the annotated label and sign for distractors.

## Reservation and settlement policy

The opt-in `--budget-usd` guard uses Decimal and the existing dated standard
uncached prices, verified against the
[official model page](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
on 2026-10-01: US$0.75 input / US$4.50 output per million tokens. Existing
historical price dates and evidence are unchanged. Cached savings are ignored.

Before each call, JSON-serialise the actual v4 instructions, page-delimited user
text and structured schema with ASCII escapes. Reject requests over **16,384
bytes**; reserve **32,768 input tokens** and the full **4096 output tokens**.
This repeats the conservative allowance from the preserved bill_002 budget
experiment: the input allowance is twice the bounded request bytes, allowing
for text tokenisation and server framing. It is a stated conservative allowance,
not a remotely measured exact token count or a proof of provider tokenisation.
Current ten inputs occupy 7,542–7,899 bytes and all fit the request ceiling.

Each mini-model reservation is **US$0.043008**. Permit a call only when
`conservative_spent + reservation <= cap`. Persist the reservation in
`budget.json` **before** extraction, then settle using returned usage and the
dated prices, releasing the difference. Missing usage, an unknown model or
usage outside the allowance preserves the reservation and stops further calls.
A raised request also retains the reservation and a partial report without
manufacturing an attempt. Partial runs remain rejected by `evals.compare`.
Do not resume or rerun them without new owner authorisation.

The ledger records request bytes, reserved cost, actual-usage cost when known,
and conservative cumulative cost. Dated-price costs are estimates, not invoices.
The ceiling is enforced under the recorded standard-price and token-allowance
assumptions; if returned usage violates them, report it and stop rather than
claiming that the allowance proved an account-wide billing cap. Regional,
nonstandard or changed prices require revisiting the policy before the run.

## Owner commands after D1 merges

Use PowerShell 7 (`Read-Host -MaskInput`). These commands make paid calls. Do
not run before D1 is reviewed/merged, and do not pass a key to Codex. The output
directory is new and ignored; it must not be reused after an abort.

```powershell
Set-Location C:\Users\maxch\Dev\bill-lens
git switch main
if ($LASTEXITCODE -ne 0) { throw "Could not select main" }
git pull --ff-only
if ($LASTEXITCODE -ne 0) { throw "Could not update main" }
if (git status --porcelain) { throw "Checkout must be clean" }
if (Test-Path Env:OPENAI_API_KEY) { throw "Clear the existing session key first" }
if (Test-Path Env:BILL_LENS_LIVE) { throw "Clear the existing live gate first" }
$roleRunOutput = "evals/results/role-v4-" + (Get-Date -Format "yyyyMMddTHHmmss")
try {
    $env:OPENAI_API_KEY = Read-Host -MaskInput "OpenAI API key (session only)"
    $env:BILL_LENS_LIVE = "1"
    .\.venv\Scripts\python.exe -m evals.run --extractor openai --model gpt-5.4-mini --repeats 3 --dataset dataset/role-holdout --budget-usd 0.30 --output $roleRunOutput
    $roleRunExit = $LASTEXITCODE
    if (Test-Path $roleRunOutput) {
        .\.venv\Scripts\python.exe -m pip freeze | Set-Content -Encoding utf8 "$roleRunOutput/pip-freeze.txt"
    }
    Write-Output "Run exit=$roleRunExit; output=$roleRunOutput. Do not rerun automatically."
} finally {
    Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:BILL_LENS_LIVE -ErrorAction SilentlyContinue
}
```

The CLI additionally refuses budgeted live execution without a clean recorded
Git commit. Give Codex the **output directory**, not the key. A nonzero exit
needs inspection and an owner decision; it is not permission for another run.

## Frozen analysis and D2

After the owner supplies the run, D2 preserves raw `summary.json`,
`attempts.jsonl`, `report.md`, `budget.json` and `pip-freeze.txt` unchanged,
records their hashes, and runs the already-merged script into a separate new
directory:

```powershell
.\.venv\Scripts\python.exe -m scripts.analyse_role_holdout_live evals/results/<owner-run> --output tmp/role-live-analysis
```

No prompt, rule or analysis-method change in response to the run is allowed
inside D2. A discovered analysis bug requires a separate disclosed change,
preserving the original output too. No new live calls are authorised by D2.

## Interpreting broad outcomes (before seeing results)

- No distractor choices: the safeguard's review cost buys little against that
  failure on these selected layouts; inspect correct-amount false reviews.
  This does not prove a role check is unnecessary on real bills.
- Some distractor choices, all caught: evidence of value on those choices,
  weighed against the measured false-review cost.
- Any silent wrong numeric acceptance: document every case and context before
  choosing a new safeguard. Do not quietly loosen or tune the frozen rule.
- Many false reviews: consider a reviewed rule/vocabulary/layout change with
  **another fresh holdout**, or model evidence spans plus context verification.
- Null/failed attempts: report separately; they do not establish successful
  protection against wrong printed numbers.

The owner chooses whether to keep the rule, revise it with a fresh holdout, or
try evidence spans. The rule and prompt remain frozen whatever this run shows.
This is one model/prompt on ten selected synthetic bills, three repeats each;
there is no real-world error-rate or sampling claim.

**No live API call was made in D1.**
