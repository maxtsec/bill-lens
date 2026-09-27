# M1: PDF text boundary

`bill_lens.pdf_text.extract_pdf_text(data: bytes)` is the first M1 building block.
It accepts PDF bytes and returns an immutable `PdfText` containing a SHA-256 hash
of the original bytes and a tuple of `PageText(page_number, text)` values. Page
numbers start at 1. Its `text` property joins pages with two newlines, preserving
the existing inspection script's baseline. It does not extract bill fields.

The implementation uses [pdfplumber](https://github.com/jsvine/pdfplumber#python-library)
with default `extract_text()` settings, following ADR-001. It preserves the text
as extracted, including suspicious instructions. Document text remains untrusted
data; successful parsing does not establish field accuracy, complete visual
coverage, or protection from prompt injection.

## Acceptance policy

These initial limits are product choices, not measured capacity guarantees:

| Check | Policy |
| --- | --- |
| File bytes | Nonempty, at most 10 MiB (10,485,760 bytes) |
| Signature | Must start with `%PDF-` at byte zero; leading junk is rejected |
| Encryption | Not supported, including PDFs readable with an empty password |
| Page count | 1 to 20 inclusive |
| Page text | Every page must contain non-whitespace extracted text |
| Combined text | At most 100,000 Python string characters, including page separators |

A blank or image-only page aborts the whole extraction. This deliberately also
rejects harmless blank appendices: until OCR or explicit page-review routing
exists, silently dropping a page risks passing incomplete evidence to the model.
A scanned page containing only a digital header can still pass; nonempty text is
not a scan detector. Multi-column ordering remains a known limitation (bill_005).

## Failures

Expected failures raise `PdfTextError` with a stable `code`, an optional
one-based `page_number`, and an optional `parser_error` containing only the
exception class name (for example, `TypeError`). No partial result is returned.
The exception message contains only the code. Parser messages are not copied,
and translation raises outside the exception handler so the original parser
exception is not attached as `__context__` or `__cause__`. This does not sanitize
traceback frame locals or library logs; error reporting must not capture document
bytes, text or parser objects from locals.

| Code | Meaning |
| --- | --- |
| `empty_file` | No bytes supplied |
| `file_too_large` | Byte limit exceeded before parsing |
| `invalid_pdf_signature` | Missing required prefix |
| `unreadable_pdf` | Parser failure, including a password required at open |
| `encrypted_pdf` | Parser opened the document, but detected encryption |
| `no_pages` | Parser found no pages, whether genuinely empty or damaged beyond recovery |
| `too_many_pages` | Page count exceeds the limit |
| `page_without_text` | A page has no non-whitespace text; page number included |
| `text_too_long` | Combined text exceeds the limit; page number included |

An incorrect Python input type raises `TypeError`. Each parser operation (open,
metadata/page access, text extraction and cleanup) catches `Exception`, including
builtin types such as `TypeError` and `IndexError` raised by malformed inputs.
Checks, text-length accounting and result construction run outside those catch
blocks, so application bugs there propagate. A library bug inside a guarded call
is indistinguishable from malformed-input failure and is also classified; the
class name is retained for diagnosis. `KeyboardInterrupt` and `SystemExit` are
not caught. Cleanup failures cannot replace an earlier failure; a cleanup-only
failure becomes `unreadable_pdf`.

The future processing layer will map these errors to operational failure
responses; these are not the domain review flags in `expected.json`, and no HTTP
status mapping is defined yet. `no_pages` describes the parser's observation, not
a diagnosis that the source was a valid empty PDF. There is no separate PDF
conformance validator here.

## Remaining work and limits

- The future upload endpoint must enforce the byte limit while streaming the
  request, before allocating a complete `bytes` object. This function's length
  check cannot limit an allocation that has already happened.
- Page counts are checked after pdfplumber enumerates pages; text length is
  checked after each page is extracted. These limits do not cap parser CPU, peak
  memory or decompressed stream size. Process isolation/timeouts belong before
  exposing this parser to untrusted public uploads. Resource exhaustion inside
  the parser (`MemoryError`, `RecursionError`) is currently classified as
  `unreadable_pdf`; only `parser_error` distinguishes it from a malformed file.
  Revisit whether it needs its own code alongside isolation and timeouts
  (M6). A signature is not proof of
  safety or validity. Library logs may include PDF metadata or diagnostics and
  need a separate logging policy before handling real customer documents.
- No OCR, layout repair, file storage, server-generated filenames, HTTP endpoint,
  database or model call is introduced here. The hash identifies bytes, not
  semantically equivalent bills or an authorization boundary.
- All seven extraction fields and the three supply-rate components now carry
  contract-aligned descriptions in generated Pydantic JSON schema. This is an
  input to future prompt construction, not a provider integration or measured
  model behavior. Required nullable keys and the string-only ISO date boundary
  remain unchanged. Provider schema compatibility still needs verification.
- The extraction contract is the semantic authority; schema descriptions are a
  manually maintained projection. Future semantic changes must review both in
  the same PR. A generated single source may be worth exploring if drift occurs.

## Verify locally

Run `python -m pytest -q` and `python scripts/inspect_dataset.py` in the installed
development environment. Tests exercise all five golden PDFs against the existing
independent pdfplumber baseline, page ordering, encrypted/invalid/textless PDFs,
inclusive limits, partial failure, and schema descriptions/required keys. Test
PDFs are generated in memory; the five owner-verified PDFs and labels are unchanged.

The [fuzzing learning note](learning/pdf-boundary-fuzzing.md) separates the
reviewer's reported experiment from locally reproduced regressions.
