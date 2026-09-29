"""Reproduce the documented Fisher result from preserved counts, without a model."""

from fractions import Fraction
import json
from math import comb
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
COUNTS = ROOT / "docs/learning/evidence/retailer-brand-v4/repeat-study-statistics.json"
NOTE = ROOT / "docs/learning/retailer-brand-evaluation.md"


def test_fisher_exact_result_matches_preserved_counts_and_documentation():
    data = json.loads(COUNTS.read_text(encoding="utf-8"))
    section = NOTE.read_text(encoding="utf-8").split("### Fisher exact comparison\n", 1)[1].split("\n### ", 1)[0]
    table = re.findall(r"\| (v[24]) \| (\d+) \| (\d+) \| (\d+) \|", section)
    assert len(table) == 2
    assert {row[0] for row in table} == {"v2", "v4"}
    for version, failures, others, total in table:
        saved = data[version]
        assert (int(failures), int(others), int(total)) == (
            saved["false_extraction_count"], saved["n"] - saved["false_extraction_count"], saved["n"])

    n1, n2 = data["v2"]["n"], data["v4"]["n"]
    observed_x = data["v2"]["false_extraction_count"]
    failures = observed_x + data["v4"]["false_extraction_count"]
    denominator = comb(n1 + n2, failures)
    distribution = {
        x: Fraction(comb(n1, x) * comb(n2, failures - x), denominator)
        for x in range(max(0, failures - n2), min(n1, failures) + 1)
    }
    assert sum(distribution.values()) == 1
    observed = distribution[observed_x]
    one_sided = sum(p for x, p in distribution.items() if x <= observed_x)
    two_sided = sum(p for p in distribution.values() if p <= observed)
    assert one_sided == Fraction(19, 78)
    assert two_sided == Fraction(19, 39)

    documented = re.findall(r"\| (One-sided \(v4 higher\)|Two-sided) \| (\d+)/(\d+) \| ([0-9.]+) \|", section)
    assert {row[0] for row in documented} == {"One-sided (v4 higher)", "Two-sided"}
    expected = {"One-sided (v4 higher)": one_sided, "Two-sided": two_sided}
    for tail, numerator, divisor, rounded in documented:
        assert int(divisor) == denominator
        assert Fraction(int(numerator), int(divisor)) == expected[tail]
        assert rounded == f"{float(expected[tail]):.3f}"
