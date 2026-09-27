# Synthetic PDF text baseline

Inspected on 2026-09-27 with Python 3.12.14, ReportLab 4.5.1 and pdfplumber 0.11.10. Reproduce from the repository root with `python scripts/inspect_dataset.py` in the project environment. The script calls `page.extract_text()` with defaults and writes ignored UTF-8 files under `tmp/extracted/`. No LLM was called.

All five PDFs have one digitally generated A4 page. Poppler renders were visually inspected for clipped text, incorrect symbols and overlapping columns. The local Poppler build emitted missing-font mapping warnings for unused fonts; the rendered pages, including the cent symbol and credit notation, were readable. The selected source values were also checked in extracted text.

| Case | Text characters | Observed behavior |
| --- | ---: | --- |
| `bill_001` | 485 | Usage and supply descriptions precede amounts on the same lines; the four-decimal AUD equivalent is not substituted for the printed cents rate. |
| `bill_002` | 618 | The amount column precedes each charge description. 162.66 is prominent and 132.66 is absent. |
| `bill_003` | 605 | Table rows preserve tariff, quantity, rate, and charge order. The DD/MM/YYYY heading and both different totals survive extraction. |
| `bill_004` | 641 | Imports and exports retain separate headings. The current total retains its CR suffix. |
| `bill_005` | 592 | The independent columns are interleaved by y position. Labels, dates and amounts survive, but their visual grouping is lost. |

For example, `bill_005` contains these consecutive lines:

```text
Billing period Total imported usage: 0 kWh
1 August 2026 to Usage: 0 kWh at AUD 0.30/kWh
31 August 2026 Usage charge: AUD 0.00
Billing days: 30 Supply: 31 days at 95¢/day
Current bill amount Supply charge: AUD 29.45
AUD 29.45
```

The two day counts reflect a deliberate contradiction in the PDF. Text interleaving is a separate layout issue. The candidate label preserves the printed summary's 30 days, and Python independently derives 31 from the period dates. A future LLM must associate values correctly rather than choose the nearest number.

This establishes a reproducible layout challenge, not evidence that an LLM will fail. The next useful experiment is to run structured extraction on this exact text and compare its fields with owner-verified labels. A later comparison with native PDF input should hold the labels and scoring rules fixed. Real bills, scans and ambiguous or missing GST labels remain outside this small dataset.
