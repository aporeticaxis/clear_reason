#!/usr/bin/env python3
"""Export test_corpus.json texts into CSV files for the Anthropic Console.

The Console lets you create prompts with {{variable}} placeholders and import
CSVs to batch-run them.  This script generates:

  console/all_texts.csv               -- all 39 texts
  console/simple_only.csv             -- 13 texts (one per type, simple only)
  console/by_type/<type_id>.csv       -- per-type subsets (13 files)
  console/preamble_texts.csv          -- 13 simple texts with metacognitive preamble

CSV columns:
  text                          -- maps to {{text}} in Console prompt
  good_formalization_indicators -- reference for human grading ("Ideal Output" toggle)

Usage:
  python3 scripts/export_console_csv.py [--corpus test_corpus.json] [--output-dir console]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path


# Maps reasoning_type_id to the appropriate focus term for the preamble.
FOCUS_MAP: dict[str, str] = {
    "argumentative_deductive":         "logical",
    "argumentative_inductive":         "logical",
    "argumentative_abductive":         "logical",
    "evidential_probabilistic":        "probabilistic",
    "causal_explanatory":              "causal",
    "similarity_based":                "analogical",
    "normative_deliberative":          "normative",
    "temporal_sequential":             "temporal",
    "systemic_configurational":        "constraint",
    "defeasible_revisable":            "defeasible",
    "non_argumentative_explanations":  "explanatory",
    "non_argumentative_deliberations": "deliberative",
    "non_argumentative_explorations":  "hypothetical",
}


def load_corpus(path: Path) -> list[dict]:
    """Load and return the test corpus entries as a flat list.

    Handles the nested reasoning_types[].texts[] structure in test_corpus.json.
    Each returned entry includes reasoning_type and reasoning_type_name from
    its parent type.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        # Primary format: reasoning_types[].texts[]
        if "reasoning_types" in data:
            entries: list[dict] = []
            for rtype in data["reasoning_types"]:
                type_id = rtype.get("id", "")
                type_name = rtype.get("name", type_id)
                for text_entry in rtype.get("texts", []):
                    entry = dict(text_entry)
                    entry["reasoning_type"] = type_id
                    entry["reasoning_type_name"] = type_name
                    entries.append(entry)
            return entries
        if "texts" in data:
            return data["texts"]

    raise ValueError(
        f"Unexpected corpus format in {path}: expected reasoning_types[] "
        f"or texts[] structure."
    )


def build_preamble(reasoning_type_id: str, reasoning_type_name: str) -> str:
    """Build the metacognitive preamble for a given reasoning type."""
    focus = FOCUS_MAP.get(reasoning_type_id)
    if focus is None:
        raise ValueError(
            f"No focus mapping for reasoning type '{reasoning_type_id}'. "
            f"Add it to FOCUS_MAP."
        )
    return (
        f"This text employs {reasoning_type_name} reasoning; "
        f"focus on {focus} structure and adequacy."
    )


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write rows to a CSV file with QUOTE_ALL quoting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["text", "good_formalization_indicators"],
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerows(rows)


def make_row(entry: dict) -> dict[str, str]:
    """Extract the two CSV columns from a corpus entry."""
    return {
        "text": entry["text"],
        "good_formalization_indicators": entry["good_formalization_indicators"],
    }


def get_reasoning_type_id(entry: dict) -> str:
    """Return the reasoning type ID from a corpus entry."""
    return str(entry.get("reasoning_type", ""))


def get_reasoning_type_name(entry: dict) -> str:
    """Return the human-readable reasoning type name from a corpus entry."""
    return str(entry.get("reasoning_type_name", entry.get("reasoning_type", "")))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export test corpus to Anthropic Console CSV files."
    )
    parser.add_argument(
        "--corpus",
        default="test_corpus.json",
        help="Path to test_corpus.json (default: test_corpus.json)",
    )
    parser.add_argument(
        "--output-dir",
        default="console",
        help="Output directory for CSV files (default: console)",
    )
    args = parser.parse_args()

    corpus_path = Path(args.corpus)
    output_dir = Path(args.output_dir)

    if not corpus_path.exists():
        print(f"Error: corpus file not found: {corpus_path}", file=sys.stderr)
        sys.exit(1)

    entries = load_corpus(corpus_path)
    print(f"Loaded {len(entries)} texts from {corpus_path}")

    all_rows = [make_row(e) for e in entries]
    all_path = output_dir / "all_texts.csv"
    write_csv(all_path, all_rows)

    simple_rows = [
        make_row(e) for e in entries
        if str(e.get("difficulty", "")).lower() == "simple"
    ]
    simple_path = output_dir / "simple_only.csv"
    write_csv(simple_path, simple_rows)

    by_type: dict[str, list[dict[str, str]]] = {}
    for e in entries:
        type_id = get_reasoning_type_id(e)
        by_type.setdefault(type_id, []).append(make_row(e))

    by_type_dir = output_dir / "by_type"
    for type_id, rows in sorted(by_type.items()):
        type_path = by_type_dir / f"{type_id}.csv"
        write_csv(type_path, rows)

    preamble_rows: list[dict[str, str]] = []
    for e in entries:
        if str(e.get("difficulty", "")).lower() != "simple":
            continue
        type_id = get_reasoning_type_id(e)
        type_name = get_reasoning_type_name(e)
        preamble = build_preamble(type_id, type_name)
        preamble_rows.append({
            "text": f"{preamble}\n\n{e['text']}",
            "good_formalization_indicators": e["good_formalization_indicators"],
        })
    preamble_path = output_dir / "preamble_texts.csv"
    write_csv(preamble_path, preamble_rows)

    generated: list[tuple[str, int]] = []
    generated.append((str(all_path), len(all_rows)))
    generated.append((str(simple_path), len(simple_rows)))
    for type_id in sorted(by_type):
        p = by_type_dir / f"{type_id}.csv"
        generated.append((str(p), len(by_type[type_id])))
    generated.append((str(preamble_path), len(preamble_rows)))

    print(f"\nGenerated {len(generated)} CSV files in {output_dir}/:\n")
    for filepath, count in generated:
        print(f"  {filepath:<50s}  {count:>3d} rows")

    total_rows = sum(c for _, c in generated)
    print(f"\n  {'TOTAL':<50s}  {total_rows:>3d} rows")


if __name__ == "__main__":
    main()
