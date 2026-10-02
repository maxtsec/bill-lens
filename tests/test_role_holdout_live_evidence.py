"""Preserved live artifacts and offline replay; no key, model call or Git history."""

from decimal import Decimal
from hashlib import sha256
import json

import pytest

from scripts import analyse_role_holdout_live as analysis

SAVED = analysis.ROOT / 'docs/learning/evidence/role-holdout-live-v4'
MANIFEST_SHA256 = 'ee68d54758a2330951e261978c7360419699a8f8a3edb4e3b82cb9ac9f4f2f1d'
ARTIFACTS = (
    'summary.json', 'attempts.jsonl', 'report.md', 'budget.json', 'pip-freeze.txt',
    'analysis/analysis.json', 'analysis/report.md',
)


def load(name):
    return json.loads((SAVED / name).read_bytes())


def test_live_evidence_manifest_is_locked():
    assert sha256((SAVED / 'manifest.json').read_bytes()).hexdigest() == MANIFEST_SHA256
    manifest = load('manifest.json')
    assert set(manifest['artifact_hashes']) == set(ARTIFACTS)
    assert manifest['completed_api_calls'] == 30
    assert manifest['additional_api_calls_by_preservation_and_analysis'] == 0
    assert (SAVED / '.gitattributes').read_bytes() == b'* -text whitespace=trailing-space,space-before-tab,cr-at-eol\n'


@pytest.mark.parametrize('name', ARTIFACTS)
def test_every_preserved_artifact_retains_exact_bytes(name):
    raw = (SAVED / name).read_bytes()
    expected = load('manifest.json')['artifact_hashes'][name]
    assert {'sha256': sha256(raw).hexdigest(), 'bytes': len(raw)} == expected


def test_live_run_coverage_clean_provenance_and_cost():
    manifest, summary, budget = (load(name) for name in ('manifest.json', 'summary.json', 'budget.json'))
    records = [json.loads(line) for line in (SAVED / 'attempts.jsonl').read_bytes().splitlines()]
    pairs = [(f'holdout_r{case:02}', repeat) for repeat in range(1, 4) for case in range(1, 11)]
    assert [(row['bill'], row['repeat']) for row in records] == pairs
    assert summary['completed'] and summary['abort_reason'] is None
    assert summary['git'] == manifest['run_git'] == {
        'commit': 'ce5ea6cab244a47e80977a7b850f0c49d0861dd7', 'dirty': False,
    }
    assert {row['resolved_model'] for row in records} == {'gpt-5.4-mini-2026-03-17'}
    assert {row['prompt_version'] for row in records} == {'extract-v4'}
    assert {row['reasoning_effort'] for row in records} == {'low'}
    assert summary['budget'] == budget
    assert len(budget['calls']) == 30
    assert all(call['state'] == 'settled' and call['stop_reason'] is None for call in budget['calls'])
    assert all(Decimal(call['reserved_total_usd']) <= Decimal('0.30') for call in budget['calls'])
    assert sum(row['input_tokens'] for row in records) == 49088
    assert sum(row['output_tokens'] for row in records) == 5900
    # Historical prices from the saved ledger, independent of future price tables.
    price_in, price_out = map(Decimal, budget['prices_per_million_usd'])
    cost = sum((Decimal(row['input_tokens']) * price_in + Decimal(row['output_tokens']) * price_out)
               / Decimal(1000000) for row in records)
    assert cost == Decimal('0.06336600') == Decimal(budget['known_settled_usd']) == Decimal(budget['spent_usd'])


def test_analysis_counts_inputs_and_source_hashes_are_preserved():
    result = load('analysis/analysis.json')
    assert result['completed'] and result['live_api_calls_by_analysis'] == 0
    for name, digest in result['source_sha256'].items():
        assert sha256((SAVED / name).read_bytes()).hexdigest() == digest
    for case, hashes in result['input_hashes'].items():
        for name, digest in hashes.items():
            assert sha256((analysis.DATASET / case / name).read_bytes()).hexdigest() == digest
    assert result['totals']['correct'] == {'count': 30, 'total': 30}
    assert result['printed_current']['correct'] == {'count': 27, 'total': 27}
    assert result['printed_current']['false_review'] == {'count': 18, 'total': 27}
    assert result['totals']['wrong_value'] == {'count': 0, 'total': 30}
    assert result['totals']['silent_false_acceptance'] == {'count': 0, 'total': 30}
    assert result['r07']['categories'] == {'null': 3}
    assert all(not row['r07_computed_87_20'] for row in result['per_attempt'])


def require_frozen_implementation(root, hashes):
    changed = [name for name, digest in hashes.items()
               if not (root / name).is_file()
               or sha256((root / name).read_text(encoding='utf-8').encode('utf-8')).hexdigest() != digest]
    if changed:
        pytest.fail('Live analysis recorded at ce5ea6c; frozen implementation changed '
                    f'({", ".join(changed)}). Replay must not silently skip. Reproduce with '
                    'the pinned implementation and explicitly migrate the replay check before '
                    'accepting new implementation fingerprints; do not regenerate saved evidence.')


@pytest.mark.parametrize('content', [None, 'changed source\n'])
def test_frozen_source_drift_fails_instead_of_skipping(tmp_path, content):
    if content is not None:
        (tmp_path / 'source.py').write_text(content, encoding='utf-8')
    with pytest.raises(pytest.fail.Exception, match='Replay must not silently skip'):
        require_frozen_implementation(tmp_path, {'source.py': sha256(b'original\n').hexdigest()})


def test_saved_live_analysis_reproduces_with_frozen_implementation():
    saved = load('analysis/analysis.json')
    reference = json.loads(analysis.REFERENCE.read_bytes())
    hashes = {name: digest for name, digest in reference['implementation_lf_sha256'].items()
              if not name.startswith('scripts/')}
    hashes['scripts/analyse_role_holdout_live.py'] = saved['analysis_script_lf_sha256']
    hashes['bill_lens/extraction/prompts/extract_v4.md'] = saved['prompt_sha256']
    require_frozen_implementation(analysis.ROOT, hashes)
    assert analysis.analyse(SAVED) == saved
    assert analysis.render_report(saved) == (SAVED / 'analysis/report.md').read_text(encoding='utf-8')
