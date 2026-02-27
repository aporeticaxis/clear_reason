#!/usr/bin/env python3
"""Post-hoc stratification of eval run results.

Reads existing grades and comparisons from a run directory and produces
finer-grained rankings than the 0/1/2 coarse scores provide.

Outputs:
  - Bradley-Terry strength scores (continuous ranking from pairwise data)
  - Pairwise edge matrix (net win margin, non-loss rate)
  - Per-type pairwise win rates
  - Per-type grade deltas between version pairs
  - Grade-pairwise divergence analysis (ceiling-effect detection)
  - Stratified leaderboard combining all signals

Requires: aggregate has been run first (reads aggregate_summary.json).

Usage:
  python3 scripts/stratify_run.py --run-dir runs/bullshit_eval
  python3 scripts/stratify_run.py --run-dir runs/bullshit_eval --anchor v3_2026
  python3 scripts/stratify_run.py --run-dir runs/bullshit_eval --output-format csv
"""

import argparse
import csv
import json
import math
import pathlib
import sys
from collections import defaultdict
from typing import Any


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_json(path: pathlib.Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: pathlib.Path, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def resolve_artifact_from_manifest(
    run_dir: pathlib.Path,
    manifest: dict[str, Any],
    manifest_key: str,
    filename: str,
) -> pathlib.Path | None:
    """Resolve an artifact path using run_manifest.json when available."""
    rel_dir = manifest.get(manifest_key)
    if not isinstance(rel_dir, str) or not rel_dir.strip():
        return None
    candidate_dir = run_dir / rel_dir
    if candidate_dir.is_file() and candidate_dir.name == filename:
        return candidate_dir
    candidate_file = candidate_dir / filename
    if candidate_file.exists():
        return candidate_file
    return None


def find_latest_artifact(run_dir: pathlib.Path, subdir: str, filename: str) -> pathlib.Path | None:
    """Find latest matching artifact in timestamped subdirectory."""
    parent = run_dir / subdir
    if not parent.exists():
        return None
    dirs = [d for d in parent.iterdir() if d.is_dir()]
    for d in sorted(dirs, reverse=True):
        if not d.is_dir():
            continue
        candidate = d / filename
        if candidate.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Bradley-Terry
# ---------------------------------------------------------------------------

def bradley_terry(
    pair_data: list[dict[str, Any]],
    anchor: str | None = None,
    anchor_strength: float = 1000.0,
    max_iter: int = 200,
    tol: float = 1e-8,
    tie_weight: float = 0.5,
) -> dict[str, float]:
    """Compute Bradley-Terry strength scores from pairwise comparison data.

    Ties count as ``tie_weight`` wins for each side.
    Laplace smoothing (0.5 pseudo-wins per side per pair) prevents zero
    estimates for versions that never won.
    """
    versions: set[str] = set()
    wins: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    n_cmp: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for pair in pair_data:
        va = pair["version_a"]
        vb = pair["version_b"]
        a_w = pair["a_wins"]
        b_w = pair["b_wins"]
        ties = pair.get("ties", 0)
        total = pair["total"]

        versions.add(va)
        versions.add(vb)

        wins[va][vb] = a_w + tie_weight * ties + 0.5
        wins[vb][va] = b_w + tie_weight * ties + 0.5
        n_cmp[va][vb] = total + 1.0
        n_cmp[vb][va] = total + 1.0

    if not versions:
        return {}

    strength: dict[str, float] = {v: 1.0 for v in versions}

    for _ in range(max_iter):
        old = dict(strength)
        for i in versions:
            total_wins_i = sum(wins[i][j] for j in versions if j != i)
            denom = sum(
                n_cmp[i][j] / (strength[i] + strength[j])
                for j in versions
                if j != i and n_cmp[i][j] > 0
            )
            if denom > 0:
                strength[i] = total_wins_i / denom

        s_sum = sum(strength.values())
        for v in versions:
            strength[v] /= s_sum

        if max(abs(strength[v] - old[v]) for v in versions) < tol:
            break

    if anchor and anchor in strength and strength[anchor] > 0:
        scale = anchor_strength / strength[anchor]
    else:
        best = max(strength, key=strength.get)  # type: ignore[arg-type]
        scale = anchor_strength / strength[best]

    return {v: round(strength[v] * scale, 1) for v in versions}


# ---------------------------------------------------------------------------
# Wilson score confidence interval
# ---------------------------------------------------------------------------

def wilson_ci(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95 % Wilson score interval for a proportion."""
    if total == 0:
        return (0.0, 0.0)
    p = wins / total
    denom = 1 + z ** 2 / total
    center = (p + z ** 2 / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z ** 2 / (4 * total)) / total) / denom
    return (round(max(0.0, center - spread), 4), round(min(1.0, center + spread), 4))


# ---------------------------------------------------------------------------
# Per-type pairwise win rates (from raw comparisons.jsonl)
# ---------------------------------------------------------------------------

def per_type_pairwise(
    comparison_rows: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    acc: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"a_wins": 0, "b_wins": 0, "ties": 0, "total": 0})
    )

    for row in comparison_rows:
        if row.get("error"):
            continue
        pair_key = f"{row.get('version_a', '')} vs {row.get('version_b', '')}"
        rtype = str(row.get("reasoning_type", ""))
        score = row.get("score", 0)
        s = acc[pair_key][rtype]
        s["total"] += 1
        if score > 0:
            s["a_wins"] += 1
        elif score < 0:
            s["b_wins"] += 1
        else:
            s["ties"] += 1

    out: dict[str, dict[str, dict[str, Any]]] = {}
    for pair_key, types in acc.items():
        out[pair_key] = {}
        for rtype, s in sorted(types.items()):
            t = s["total"]
            out[pair_key][rtype] = {
                **s,
                "a_win_rate": round(s["a_wins"] / t, 4) if t else None,
            }
    return out


# ---------------------------------------------------------------------------
# Per-type grade deltas
# ---------------------------------------------------------------------------

def per_type_grade_deltas(
    grade_rows: list[dict[str, Any]],
    version_pairs: list[tuple[str, str]],
) -> dict[str, dict[str, float]]:
    scores: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for row in grade_rows:
        vid = str(row.get("version_id", ""))
        rtype = str(row.get("reasoning_type", ""))
        s = row.get("judge_score")
        if s in (0, 1, 2):
            scores[vid][rtype].append(int(s))

    deltas: dict[str, dict[str, float]] = {}
    for va, vb in version_pairs:
        key = f"{va} vs {vb}"
        d: dict[str, float] = {}
        all_types = set(scores.get(va, {}).keys()) | set(scores.get(vb, {}).keys())
        for rtype in sorted(all_types):
            a_s = scores.get(va, {}).get(rtype, [])
            b_s = scores.get(vb, {}).get(rtype, [])
            if a_s and b_s:
                d[rtype] = round(sum(a_s) / len(a_s) - sum(b_s) / len(b_s), 4)
        deltas[key] = d
    return deltas


# ---------------------------------------------------------------------------
# Grade-pairwise divergence
# ---------------------------------------------------------------------------

def grade_pairwise_divergence(
    grade_rows: list[dict[str, Any]],
    comparison_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Items where grading gave the same score but pairwise picked a winner."""
    gl: dict[tuple[str, str], int] = {}
    for row in grade_rows:
        vid = str(row.get("version_id", ""))
        tid = str(row.get("text_id", ""))
        s = row.get("judge_score")
        if s in (0, 1, 2):
            gl[(vid, tid)] = int(s)

    divergences: list[dict[str, Any]] = []
    for row in comparison_rows:
        if row.get("error"):
            continue
        va = row.get("version_a", "")
        vb = row.get("version_b", "")
        tid = row.get("text_id", "")
        score = row.get("score", 0)
        ga = gl.get((va, tid))
        gb = gl.get((vb, tid))
        if ga is not None and gb is not None and ga == gb and score != 0:
            divergences.append({
                "text_id": tid,
                "reasoning_type": row.get("reasoning_type", ""),
                "version_a": va,
                "version_b": vb,
                "shared_grade": ga,
                "pairwise_winner": va if score > 0 else vb,
                "pairwise_score": score,
            })
    return divergences


# ---------------------------------------------------------------------------
# Stratified leaderboard
# ---------------------------------------------------------------------------

def build_leaderboard(
    grade_lb: list[dict[str, Any]],
    pair_summaries: list[dict[str, Any]],
    bt_scores: dict[str, float],
) -> list[dict[str, Any]]:
    grade_by_v = {e["version_id"]: e for e in grade_lb}

    pw: dict[str, dict[str, int]] = defaultdict(
        lambda: {"wins": 0, "losses": 0, "ties": 0, "total": 0}
    )
    for p in pair_summaries:
        va, vb = p["version_a"], p["version_b"]
        for side, w, l in [(va, "a_wins", "b_wins"), (vb, "b_wins", "a_wins")]:
            pw[side]["wins"] += p[w]
            pw[side]["losses"] += p[l]
            pw[side]["ties"] += p.get("ties", 0)
            pw[side]["total"] += p["total"]

    all_versions = set(grade_by_v.keys()) | set(bt_scores.keys())
    rows: list[dict[str, Any]] = []
    for vid in all_versions:
        g = grade_by_v.get(vid, {})
        s = pw.get(vid, {})
        t = s.get("total", 0)
        w = s.get("wins", 0)
        lo = s.get("losses", 0)
        ti = s.get("ties", 0)

        rows.append({
            "version_id": vid,
            "version_name": g.get("version_name", vid),
            "avg_score": g.get("avg_score"),
            "interrogation_ready_rate": g.get("interrogation_ready_rate"),
            "score_distribution": [g.get("score_0", 0), g.get("score_1", 0), g.get("score_2", 0)],
            "bt_strength": bt_scores.get(vid),
            "pairwise_wins": w,
            "pairwise_losses": lo,
            "pairwise_ties": ti,
            "pairwise_total": t,
            "win_rate": round(w / t, 4) if t else None,
            "non_loss_rate": round((w + ti) / t, 4) if t else None,
            "win_rate_ci_95": list(wilson_ci(w, t)) if t else None,
            "pairwise_edge": w - lo,
        })

    rows.sort(
        key=lambda r: (
            r["bt_strength"] if r["bt_strength"] is not None else -1,
            r["avg_score"] if r["avg_score"] is not None else -1,
        ),
        reverse=True,
    )
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows


# ---------------------------------------------------------------------------
# Divergence summary (compact)
# ---------------------------------------------------------------------------

def summarize_divergence(
    divergences: list[dict[str, Any]],
) -> dict[str, Any]:
    if not divergences:
        return {"total": 0, "by_pair": {}}
    by_pair: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "a_preferred": 0, "b_preferred": 0, "by_grade": defaultdict(int)}
    )
    for d in divergences:
        pk = f"{d['version_a']} vs {d['version_b']}"
        bp = by_pair[pk]
        bp["total"] += 1
        if d["pairwise_winner"] == d["version_a"]:
            bp["a_preferred"] += 1
        else:
            bp["b_preferred"] += 1
        bp["by_grade"][str(d["shared_grade"])] += 1

    # Convert defaultdicts for JSON
    clean: dict[str, Any] = {}
    for pk, bp in by_pair.items():
        clean[pk] = {
            "total": bp["total"],
            "a_preferred": bp["a_preferred"],
            "b_preferred": bp["b_preferred"],
            "by_grade": dict(bp["by_grade"]),
        }
    return {"total": len(divergences), "by_pair": clean}


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------

def print_leaderboard(rows: list[dict[str, Any]]) -> None:
    print("\n=== Stratified Leaderboard ===\n")
    hdr = (
        f"{'#':>3}  {'Version':<35}  {'Grade':>5}  "
        f"{'BT':>7}  {'W-L-T':>11}  {'Win%':>6}  "
        f"{'NL%':>6}  {'95% CI':>14}  {'Edge':>5}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        ci = r.get("win_rate_ci_95")
        ci_s = f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "       —"
        wlt = f"{r['pairwise_wins']}-{r['pairwise_losses']}-{r['pairwise_ties']}"
        print(
            f"{r['rank']:>3}  {r['version_id']:<35}  "
            f"{r['avg_score'] or 0:>5.3f}  "
            f"{r.get('bt_strength') or 0:>7.1f}  "
            f"{wlt:>11}  "
            f"{(r['win_rate'] or 0) * 100:>5.1f}%  "
            f"{(r['non_loss_rate'] or 0) * 100:>5.1f}%  "
            f"{ci_s:>14}  "
            f"{r.get('pairwise_edge', 0):>+5d}"
        )


def print_per_type_pw(data: dict[str, dict[str, dict[str, Any]]]) -> None:
    for pk, types in data.items():
        print(f"\n--- {pk}: per-type pairwise ---")
        for rtype, s in types.items():
            wr = s.get("a_win_rate")
            wr_s = f"{wr * 100:.0f}%" if wr is not None else "—"
            print(
                f"  {rtype:<45}  "
                f"A {s['a_wins']:>2}  B {s['b_wins']:>2}  "
                f"T {s['ties']:>2}  (A: {wr_s})"
            )


def print_divergence(div_summary: dict[str, Any]) -> None:
    total = div_summary.get("total", 0)
    if total == 0:
        print("\nNo grade-pairwise divergences (grades discriminated all items).")
        return
    print(f"\n=== Grade-Pairwise Divergence: {total} items ===")
    print("Items where both versions share the same grade but pairwise picked a winner:\n")
    for pk, info in div_summary.get("by_pair", {}).items():
        print(f"  {pk}:  {info['total']} divergent  "
              f"(A preferred {info['a_preferred']}, B preferred {info['b_preferred']})")
        for grade, count in sorted(info.get("by_grade", {}).items()):
            print(f"    at grade {grade}: {count}")


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def write_csv(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "rank", "version_id", "avg_score", "interrogation_ready_rate",
        "bt_strength", "pairwise_wins", "pairwise_losses", "pairwise_ties",
        "win_rate", "non_loss_rate", "pairwise_edge",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Post-hoc stratification of eval run results")
    ap.add_argument("--run-dir", required=True, help="Path to run directory")
    ap.add_argument("--output-format", choices=["json", "csv", "both"], default="both")
    ap.add_argument("--anchor", default=None,
                    help="Version ID to anchor BT scores at 1000 (default: auto)")
    ap.add_argument("--quiet", action="store_true", help="Suppress console output")
    args = ap.parse_args()

    run_dir = pathlib.Path(args.run_dir)
    if not run_dir.exists():
        print(f"Run directory not found: {run_dir}", file=sys.stderr)
        return 1

    # --- Load data ---
    agg_path = run_dir / "aggregate" / "aggregate_summary.json"
    if not agg_path.exists():
        print(f"No aggregate_summary.json found. Run 'aggregate' first.", file=sys.stderr)
        return 1

    aggregate = read_json(agg_path)
    pair_summaries = aggregate.get("comparison_pairs", [])
    grade_lb = aggregate.get("leaderboard", [])

    manifest_path = run_dir / "run_manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = read_json(manifest_path)
        except json.JSONDecodeError:
            manifest = {}

    grades_path = resolve_artifact_from_manifest(
        run_dir, manifest, "grades_dir", "grades.jsonl"
    ) or find_latest_artifact(run_dir, "grades", "grades.jsonl")
    grade_rows = read_jsonl(grades_path) if grades_path else []

    comparisons_path = resolve_artifact_from_manifest(
        run_dir, manifest, "comparisons_dir", "comparisons.jsonl"
    ) or find_latest_artifact(run_dir, "comparisons", "comparisons.jsonl")
    comparison_rows = read_jsonl(comparisons_path) if comparisons_path else []

    # --- Compute ---

    # Auto-detect anchor: version appearing most often as version_a
    anchor = args.anchor
    if not anchor and pair_summaries:
        counts: dict[str, int] = defaultdict(int)
        for p in pair_summaries:
            counts[p["version_a"]] += 1
        anchor = max(counts, key=counts.get)  # type: ignore[arg-type]

    bt = bradley_terry(pair_summaries, anchor=anchor) if pair_summaries else {}
    leaderboard = build_leaderboard(grade_lb, pair_summaries, bt)

    ptype_pw = per_type_pairwise(comparison_rows) if comparison_rows else {}
    version_pairs = [(p["version_a"], p["version_b"]) for p in pair_summaries]
    ptype_deltas = per_type_grade_deltas(grade_rows, version_pairs) if grade_rows else {}

    divergences = grade_pairwise_divergence(grade_rows, comparison_rows) if (
        grade_rows and comparison_rows
    ) else []
    div_summary = summarize_divergence(divergences)

    # --- Output ---
    out_dir = run_dir / "stratified"
    out_dir.mkdir(parents=True, exist_ok=True)

    output = {
        "stratified_leaderboard": leaderboard,
        "bradley_terry": {"anchor": anchor, "anchor_strength": 1000.0, "scores": bt},
        "per_type_pairwise": ptype_pw,
        "per_type_grade_deltas": ptype_deltas,
        "divergence": div_summary,
    }

    if args.output_format in ("json", "both"):
        p = out_dir / "stratified_summary.json"
        write_json(p, output)
        if not args.quiet:
            print(f"JSON: {p}")

    if args.output_format in ("csv", "both"):
        p = out_dir / "stratified_leaderboard.csv"
        write_csv(p, leaderboard)
        if not args.quiet:
            print(f"CSV:  {p}")

    if not args.quiet:
        print_leaderboard(leaderboard)
        if ptype_pw:
            print_per_type_pw(ptype_pw)
        print_divergence(div_summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
