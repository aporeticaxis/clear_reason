# Clear Reason Test Suite

Empirical evaluation of Clear Reason formalization quality across prompt versions, using the Socratic Test criterion.

## Scoring

- `2` Interrogation-ready: structure is rich enough for productive Socratic interrogation
- `1` Functional but shallow: basic structure is present but mostly surface-level
- `0` Opaque or wrong frame: not interrogable or framed as the wrong task type

## Corpora

### Naturalistic corpus (`test_corpus.json`)

- 39 texts
- 13 reasoning types
- 3 difficulties per type (simple, complex, edge)

### Logic Book corpus (`test_corpus_logic_book.json`)

- 649 exercises from *The Logic Book* (6th ed.)
- 5 categories: `lb_intro`, `lb_symbolization`, `lb_semantics`, `lb_pred_symbol`, `lb_pred_semantics`
- Includes metadata such as symbolization keys (when available), good-formalization indicators, and failure modes

### Bullshit detection corpus (`test_corpus_bullshit.json`)

**55 nonsense questions** across 10 techniques, derived from the
[Bullshit Benchmark](https://github.com/petergpt/bullshit-benchmark).
Tests whether formalization surfaces structural nonsense rather than
engaging with it at face value.

Runtime note:
- The suite executes directly from `test_corpus.json`, `test_corpus_logic_book.json`, and `test_corpus_bullshit.json`.
- Intermediate extraction artifacts (`logic_book_exercises/`, OCR/PDF refs, conversion helpers) are not required for running the benchmark.

## Requirements

- `python3`
- `claude` CLI installed and authenticated

All model calls use `claude -p` (subscription-backed CLI usage, no API key required by this pipeline).

## Quick Start

### Full pipeline

```bash
./scripts/run_end_to_end.sh --run-id my_run
```

### Dry run (no model calls)

```bash
./scripts/run_end_to_end.sh --dry-run --run-id dry_run_smoke
```

### Naturalistic smoke

```bash
python3 scripts/clear_reason_eval.py collect \
  --run-id nat_smoke \
  --version-filter "v3_2026,no_prompt" \
  --type-filter "argumentative_deductive" \
  --limit 2
python3 scripts/clear_reason_eval.py grade \
  --responses-file runs/nat_smoke/formalizations.jsonl
python3 scripts/clear_reason_eval.py compare \
  --responses-file runs/nat_smoke/formalizations.jsonl
python3 scripts/clear_reason_eval.py aggregate --run-dir runs/nat_smoke
```

### Logic Book smoke

```bash
python3 scripts/clear_reason_eval.py collect \
  --run-id lb_smoke \
  --corpus test_corpus_logic_book.json \
  --version-filter "v3_2026,no_prompt" \
  --type-filter "lb_symbolization" \
  --limit 2
python3 scripts/clear_reason_eval.py grade \
  --responses-file runs/lb_smoke/formalizations.jsonl
python3 scripts/clear_reason_eval.py compare \
  --responses-file runs/lb_smoke/formalizations.jsonl
python3 scripts/clear_reason_eval.py aggregate --run-dir runs/lb_smoke
```

### Bullshit detection smoke

```bash
python3 scripts/clear_reason_eval.py collect \
  --corpus test_corpus_bullshit.json \
  --version-filter "v3_2026,no_prompt" \
  --type-filter "cross_domain_concept_stitching" \
  --limit 3
```

## Dashboard

Serve the repo root and open the Clear Reason viewer:

```bash
python3 -m http.server 8000
# http://localhost:8000/viewer/clear_reason.html?run=<run_id>
```

Behavior:
- Without `?run=...`: dashboard shows a guidance empty state.
- With `?run=<run_id>`: dashboard loads run artifacts from `runs/<run_id>/`.

Expected run artifacts:
- `runs/<run_id>/collect_meta.json`
- `runs/<run_id>/run_manifest.json`
- `runs/<run_id>/aggregate/aggregate_summary.json`
- `runs/<run_id>/grades/<timestamp>_.../grades.jsonl`
- `runs/<run_id>/comparisons/<timestamp>/comparisons.jsonl`

## Main Files

```text
config.json
prompt_versions.json
test_corpus.json
test_corpus_logic_book.json
test_corpus_bullshit.json
prompts/
scripts/clear_reason_eval.py
scripts/ablate.py
scripts/export_console_csv.py
scripts/run_end_to_end.sh
viewer/clear_reason.html
index.html
```

## Legal and Provenance

- `test_corpus_logic_book.json` is derived from *The Logic Book* source material and adaptation work done in this fork.
- Public publication of that derived corpus is an explicit project decision and accepted repository risk.

## Legacy Fork Note

This repo originated as a fork of [petergpt/bullshit-benchmark](https://github.com/petergpt/bullshit-benchmark). Legacy benchmark tooling and schemas are not part of the Clear Reason mainline workflow.
