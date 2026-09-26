# ADR-001: Start PDF extraction with an inspectable text baseline

- Status: Accepted for the initial vertical slice
- Scope: Victorian household electricity bills in Bill Lens

## Context

Electricity bills contain the same kinds of information in different layouts. We need to discover where extraction fails, not assume that a plausible model response is correct. Milestone 0 will supply five synthetic PDFs with human-checked expected values; Milestone 1 will use them to exercise one upload-to-JSON path.

The [extraction contract](../extraction-contract.md) defines what the model may identify. Python owns date calculations, unit conversion, validation, and other exact arithmetic. PDF content is untrusted input, including text that looks like instructions to the model.

## Decision

Use this first pipeline:

```text
PDF → pdfplumber text extraction → structured LLM extraction
    → schema validation → domain checks and deterministic calculations
```

Inspect extracted text locally during development; do not commit text from real customer bills. If a PDF yields no usable text, report a processing failure or need for review instead of inventing field values. The model returns the fields and printed units in the contract; it does not calculate billing days, convert cents to dollars, reconcile charge lines, or decide that an account balance is the current bill amount.

This is a baseline for measurement, not a claim that plain text preserves every bill layout. Later implementation decisions about persistence and model integration belong in their own changes.

## Alternatives

| Approach | Potential benefit | Reason to defer |
| --- | --- | --- |
| Native PDF or multimodal model input | May retain visual relationships between columns and tables | More complex and potentially more expensive; first measure whether text loses information that matters |
| Retailer-specific parsing rules | Deterministic for stable, known templates | Does not establish a general baseline and can become brittle as layouts change |
| OCR before extraction | Can read scanned or image-only bills | Adds another error source and operational cost before we know how often scans occur |

## Trade-offs

Text extraction is simple, inspectable, and easy to test against the golden dataset. It may scramble reading order, especially in tables and multiple columns, and it cannot recover text from an image-only scan without OCR. The deliberately awkward `bill_005` will test one layout failure mode, but five synthetic bills cannot establish real-world accuracy.

Separating text extraction from LLM interpretation makes failures easier to diagnose: we can inspect whether the source text omitted a value, reordered it, or contained it correctly while the model chose the wrong field. Structured output and validation constrain the shape of an answer; they do not prove the answer matches the PDF. Keep document text in a data role and treat any embedded commands as untrusted.

## When we will revisit

After the initial five bills exist, inspect the extracted text and record field-level errors, missing fields, review flags, latency, and model cost for the baseline. Revisit this decision if text extraction loses table or column relationships needed for the contract, if scanned bills become a required input, or if evaluation shows repeated errors that visual PDF input could plausibly address. Compare a replacement on the same labelled bills before adopting it; expand the dataset before making claims about broader accuracy.
