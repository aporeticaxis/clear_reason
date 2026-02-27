#!/usr/bin/env python3
"""Clear Reason formalization quality evaluation pipeline.

Evaluates formalization quality across prompt versions using the Socratic Test
criterion. All model calls go through `claude -p` (Claude Code CLI in print
mode), using subscription budget — no API keys or per-token billing.

Subcommands:
  collect    — Formalize test texts under each prompt version
  grade      — Socratic evaluation of collected formalizations (0/1/2)
  compare    — Pairwise blinded comparison of prompt versions
  aggregate  — Leaderboard, per-type breakdown, ablation impact
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime as dt
import hashlib
import json
import os
import pathlib
import random
import re
import statistics
import subprocess
import sys
import threading
import time
from collections import defaultdict
from typing import Any


# --- Constants & prompts ---

JUDGE_SYSTEM_PROMPT = """\
You are evaluating the quality of a logical formalization using the Socratic \
Test criterion. A good formalization is one that a second analyst can \
productively interrogate — identifying strong and weak inferential steps, \
surfacing hidden premises, and challenging foreclosed alternatives.

Focus on structural quality, not surface notation preferences. Do not count \
the following as meaningful criticism:
- Surface notation preferences ("could use ∧ instead of &")
- Generic "this could be formalized differently" without specifying how
- Restating original text without structural analysis
- Acknowledging limitations without specifying them ("this is one possible \
reading") unless alternatives are identified
"""

JUDGE_USER_TEMPLATE = """\
The original text was:
{text}

The formalization produced was:
{formalization}

Evaluate this formalization using the Socratic Test: could a second analyst \
productively interrogate it?

- Score 0 — Opaque or structurally wrong: Formalization (a) can't be \
interrogated — no identifiable inferential steps, or (b) applies the wrong \
analytical frame entirely (assesses validity of an explanation, forces \
argument structure on a deliberation). Interrogator has nothing productive \
to work with.

- Score 1 — Functional but shallow: Identifiable structure, right general \
frame, but interrogation yields only surface findings (minor notation, \
obvious premises). Core analytical work is done but not deeply — hidden \
premises unnoticed, alternatives never considered, structural choices \
unjustified.

- Score 2 — Interrogation-ready: Inferential structure rich enough that \
interrogator can identify strong/weak steps, surface non-obvious hidden \
premises, and challenge foreclosed alternatives. Analytical choices visible \
and pushback-ready.

Return a JSON object with:
- justification: one sentence explaining which elements drove your score
- score: integer (0, 1, or 2)
Use this key order: `justification` first, then `score`."""

COMPARE_SYSTEM_PROMPT = """\
You are comparing two formalizations of the same text. Both are presented \
in randomized order (A and B). Evaluate which formalization would produce \
more productive Socratic interrogation — richer identification of \
inferential structure, hidden premises, and foreclosed alternatives.

Do not prefer one over the other based on length alone, notation style, \
or surface differences. Focus on structural quality for interrogation."""

COMPARE_USER_TEMPLATE = """\
The original text was:
{text}

Formalization A:
{formalization_a}

Formalization B:
{formalization_b}

Which formalization is more interrogation-ready?

Return a JSON object with:
- justification: one sentence explaining the key difference
- winner: "A", "B", or "tie"
Use this key order: `justification` first, then `winner`."""


# --- Utilities ---

def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def to_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")


def stable_short_hash(value: str, length: int = 12) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def write_json(path: pathlib.Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_jsonl(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{lineno}: {exc}") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"Expected object JSON at {path}:{lineno}")
            rows.append(parsed)
    return rows


def append_jsonl(path: pathlib.Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_checkpoint_ids(path: pathlib.Path) -> set[str]:
    """Load sample_ids from an existing JSONL checkpoint file."""
    if not path.exists():
        return set()
    ids: set[str] = set()
    for row in read_jsonl(path):
        sample_id = str(row.get("sample_id", "")).strip()
        if sample_id:
            ids.add(sample_id)
    return ids


def find_first_json_object(text: str) -> str | None:
    """Extract the first {...} JSON object from text."""
    in_string = False
    escaped = False
    depth = 0
    start = -1
    for index, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = index
            depth += 1
            continue
        if ch == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start >= 0:
                return text[start : index + 1]
    return None


def parse_json_output(text: str) -> dict[str, Any]:
    """Parse JSON from model output, tolerating markdown fences."""
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty model output — expected JSON object.")

    candidates: list[str] = [stripped]
    fence_match = re.search(
        r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.IGNORECASE | re.DOTALL
    )
    if fence_match:
        fenced = fence_match.group(1).strip()
        if fenced:
            candidates.append(fenced)
    first_obj = find_first_json_object(stripped)
    if first_obj:
        candidates.append(first_obj)

    for candidate in candidates:
        try:
            loaded = json.loads(candidate)
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            continue

    raise ValueError(f"Could not parse JSON from model output: {stripped[:200]}")


def build_sample_id(*, run_id: str, text_id: str, version_id: str, run_index: int) -> str:
    run_slug = to_slug(run_id) or "run"
    version_key = f"{to_slug(version_id)}_{stable_short_hash(version_id, length=8)}"
    return f"{run_slug}__{text_id}__{version_key}__run{run_index}"


PROGRESS_PHASE_ORDER = ("collect", "grade", "compare", "aggregate")


def _default_phase_progress() -> dict[str, Any]:
    return {
        "status": "pending",
        "total": 0,
        "completed": 0,
        "checkpointed": 0,
        "errors": 0,
        "percent": 0.0,
        "elapsed_seconds": 0.0,
        "eta_seconds": None,
        "throughput_per_min": None,
        "started_at_utc": None,
        "finished_at_utc": None,
        "updated_at_utc": None,
        "message": "",
    }


def _default_progress_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "pipeline_status": "pending",
        "active_phase": "",
        "run_id": "",
        "run_dir": "",
        "updated_at_utc": utc_now_iso(),
        "phases": {
            phase: _default_phase_progress()
            for phase in PROGRESS_PHASE_ORDER
        },
    }


def _load_progress_state(path: pathlib.Path) -> dict[str, Any]:
    state = _default_progress_state()
    if not path.exists():
        return state
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return state
    if not isinstance(loaded, dict):
        return state

    for key in ("schema_version", "pipeline_status", "active_phase", "run_id", "run_dir", "updated_at_utc"):
        if key in loaded:
            state[key] = loaded[key]

    loaded_phases = loaded.get("phases")
    if isinstance(loaded_phases, dict):
        for phase in PROGRESS_PHASE_ORDER:
            existing = loaded_phases.get(phase)
            if isinstance(existing, dict):
                merged = _default_phase_progress()
                merged.update(existing)
                state["phases"][phase] = merged

    return state


def _write_json_atomic(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp_path, path)


def resolve_progress_file(path_value: str) -> pathlib.Path | None:
    raw = path_value.strip() if path_value else ""
    if not raw:
        raw = os.environ.get("CLEAR_REASON_PROGRESS_FILE", "").strip()
    if not raw:
        return None
    return pathlib.Path(raw)


def _derive_pipeline_status(phases: dict[str, dict[str, Any]]) -> str:
    statuses = [str(p.get("status", "pending")) for p in phases.values()]
    if any(status == "running" for status in statuses):
        return "running"
    if any(status == "error" for status in statuses):
        return "error"
    if statuses and all(status == "done" for status in statuses):
        return "done"
    if any(status == "done" for status in statuses):
        return "running"
    return "pending"


def _calc_progress_metrics(
    *,
    total: int,
    completed: int,
    checkpointed: int,
    started_perf: float,
) -> tuple[float, float | None, float | None]:
    elapsed_seconds = max(0.0, time.perf_counter() - started_perf)
    processed = max(0, completed - checkpointed)
    if elapsed_seconds <= 0.0 or processed <= 0:
        return elapsed_seconds, None, None

    rate_per_second = processed / elapsed_seconds
    throughput_per_min = round(rate_per_second * 60.0, 3)
    remaining = max(0, total - completed)
    eta_seconds = round(remaining / rate_per_second, 2)
    return elapsed_seconds, throughput_per_min, eta_seconds


def emit_phase_progress(
    *,
    progress_file: pathlib.Path | None,
    phase: str,
    status: str,
    total: int,
    completed: int,
    checkpointed: int,
    errors: int,
    started_at_utc: str,
    started_perf: float,
    run_id: str = "",
    run_dir: str = "",
    message: str = "",
) -> None:
    if not progress_file:
        return
    state = _load_progress_state(progress_file)
    now = utc_now_iso()
    phase_state = state["phases"].setdefault(phase, _default_phase_progress())
    elapsed_seconds, throughput_per_min, eta_seconds = _calc_progress_metrics(
        total=total,
        completed=completed,
        checkpointed=checkpointed,
        started_perf=started_perf,
    )

    percent = round((completed / total) * 100.0, 2) if total > 0 else 100.0
    phase_state.update(
        {
            "status": status,
            "total": total,
            "completed": completed,
            "checkpointed": checkpointed,
            "errors": errors,
            "percent": percent,
            "elapsed_seconds": round(elapsed_seconds, 2),
            "eta_seconds": eta_seconds,
            "throughput_per_min": throughput_per_min,
            "started_at_utc": started_at_utc,
            "updated_at_utc": now,
            "message": message or "",
        }
    )

    if status in ("done", "error"):
        phase_state["finished_at_utc"] = now
    else:
        phase_state["finished_at_utc"] = None

    if run_id:
        state["run_id"] = run_id
    if run_dir:
        state["run_dir"] = run_dir

    state["active_phase"] = phase if status == "running" else ""
    state["pipeline_status"] = _derive_pipeline_status(state["phases"])
    state["updated_at_utc"] = now
    _write_json_atomic(progress_file, state)


# --- Claude CLI wrapper ---

def run_claude(
    user_message: str,
    system_prompt: str | None = None,
    model: str = "claude-sonnet-4-6",
    timeout: int = 300,
) -> str:
    """Invoke claude CLI in print mode. Returns model response text."""
    cmd = ["claude", "-p", "--model", model]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    cmd.append(user_message)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env
    )
    if result.returncode != 0:
        stderr_text = (result.stderr or "").strip()
        raise RuntimeError(
            f"claude CLI exited with code {result.returncode}: {stderr_text}"
        )
    return result.stdout.strip()


# --- Corpus & version loading ---

def load_corpus(
    path: str,
    type_filter: list[str] | None = None,
    allow_empty: bool = False,
) -> list[dict[str, Any]]:
    """Load test texts from test_corpus.json, optionally filtered by type."""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    reasoning_types = payload.get("reasoning_types")
    if not isinstance(reasoning_types, list):
        raise ValueError("test_corpus.json must contain a 'reasoning_types' array.")

    allowed_types = set(type_filter) if type_filter else None
    texts: list[dict[str, Any]] = []
    for rtype in reasoning_types:
        type_id = str(rtype.get("id", "")).strip()
        if allowed_types and type_id not in allowed_types:
            continue
        for text_entry in rtype.get("texts", []):
            texts.append({
                "id": text_entry["id"],
                "text": text_entry["text"],
                "difficulty": text_entry.get("difficulty", ""),
                "reasoning_type": type_id,
                "reasoning_type_name": rtype.get("name", type_id),
                "good_formalization_indicators": text_entry.get(
                    "good_formalization_indicators", ""
                ),
                "failure_modes": text_entry.get("failure_modes", []),
                "key_prompt_sections": text_entry.get("key_prompt_sections", []),
                "notes": text_entry.get("notes", ""),
            })

    if not texts and not allow_empty:
        raise ValueError("No texts selected. Check --type-filter.")
    return texts


def load_versions(
    path: str,
    version_filter: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Load prompt version definitions from prompt_versions.json."""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    versions = payload.get("versions")
    if not isinstance(versions, list):
        raise ValueError("prompt_versions.json must contain a 'versions' array.")

    allowed = set(version_filter) if version_filter else None
    selected: list[dict[str, Any]] = []
    for version in versions:
        vid = str(version.get("id", "")).strip()
        if allowed and vid not in allowed:
            continue
        selected.append(version)

    if not selected:
        raise ValueError("No versions selected. Check --version-filter.")
    return selected


def assemble_system_prompt(
    version: dict[str, Any],
    base_dir: pathlib.Path,
) -> str | None:
    """Build the full system prompt for a version by concatenating files.

    For ablation versions, the system prompt file is read and then the
    specified section is removed before concatenation with knowledge files.
    """
    prompt_file = version.get("system_prompt_file")
    if not prompt_file:
        return None

    prompt_path = base_dir / prompt_file
    prompt_text = prompt_path.read_text(encoding="utf-8")

    # Handle ablation
    ablate_section_id = version.get("ablate_section")
    if ablate_section_id:
        # Import ablation logic
        scripts_dir = str(base_dir / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from ablate import ablate_section as _ablate, ABLATION_HEADERS
        header = ABLATION_HEADERS.get(ablate_section_id)
        if not header:
            raise ValueError(f"Unknown ablation section: {ablate_section_id}")
        prompt_text = _ablate(prompt_text, header)

    parts = [prompt_text]
    for kf in version.get("knowledge_files", []):
        kf_path = base_dir / kf
        parts.append(kf_path.read_text(encoding="utf-8"))

    return "\n\n".join(parts)


# --- collect subcommand ---

def build_collect_tasks(
    versions: list[dict[str, Any]],
    texts: list[dict[str, Any]],
    num_runs: int,
    run_id: str,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for run_index in range(1, num_runs + 1):
        for version in versions:
            for text_entry in texts:
                sample_id = build_sample_id(
                    run_id=run_id,
                    text_id=text_entry["id"],
                    version_id=version["id"],
                    run_index=run_index,
                )
                tasks.append({
                    "sample_id": sample_id,
                    "run_index": run_index,
                    "version": version,
                    "text_entry": text_entry,
                })
    return tasks


def collect_one(
    task: dict[str, Any],
    *,
    base_dir: pathlib.Path,
    model: str,
    timeout: int,
    dry_run: bool,
) -> dict[str, Any]:
    """Formalize one text under one prompt version."""
    version = task["version"]
    text_entry = task["text_entry"]
    started_at = utc_now_iso()
    t0 = time.perf_counter()

    record: dict[str, Any] = {
        "sample_id": task["sample_id"],
        "run_index": task["run_index"],
        "version_id": version["id"],
        "version_name": version.get("name", version["id"]),
        "version_type": version.get("type", ""),
        "text_id": text_entry["id"],
        "reasoning_type": text_entry["reasoning_type"],
        "difficulty": text_entry["difficulty"],
        "text": text_entry["text"],
        "good_formalization_indicators": text_entry.get(
            "good_formalization_indicators", ""
        ),
        "formalization": "",
        "model": model,
        "started_at_utc": started_at,
        "finished_at_utc": None,
        "latency_ms": None,
        "error": "",
    }

    try:
        system_prompt = assemble_system_prompt(version, base_dir)
        user_message = f"Formalize the following text:\n\n{text_entry['text']}"

        if dry_run:
            formalization = (
                f"DRY RUN formalization for text={text_entry['id']} "
                f"version={version['id']}"
            )
        else:
            formalization = run_claude(
                user_message,
                system_prompt=system_prompt,
                model=model,
                timeout=timeout,
            )

        if not formalization.strip():
            raise RuntimeError("claude returned empty response.")

        record["formalization"] = formalization
    except Exception as exc:
        record["error"] = str(exc)
    finally:
        record["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        record["finished_at_utc"] = utc_now_iso()

    return record


def run_collect(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    collect_cfg = config.get("collect", {})

    corpus_path = args.corpus or collect_cfg.get("test_corpus", "test_corpus.json")
    versions_path = args.versions or collect_cfg.get("prompt_versions", "prompt_versions.json")
    model = args.model or collect_cfg.get("model", "claude-sonnet-4-6")
    num_runs = args.num_runs or collect_cfg.get("num_runs", 1)
    timeout = collect_cfg.get("timeout_seconds", 300)

    type_filter = _split_csv(args.type_filter) if args.type_filter else None
    version_filter = _split_csv(args.version_filter) if args.version_filter else None

    base_dir = pathlib.Path(args.config).resolve().parent
    texts = load_corpus(corpus_path, type_filter=type_filter,
                        allow_empty=bool(args.corpus_extra))
    if args.corpus_extra:
        for extra in args.corpus_extra.split(","):
            extra_path = extra.strip()
            if extra_path:
                texts.extend(load_corpus(extra_path, type_filter=type_filter))
    if not texts:
        raise ValueError("No texts selected from any corpus. Check --type-filter.")
    if args.limit and args.limit > 0:
        # Limit texts per reasoning type for smoke tests
        by_type: dict[str, list] = {}
        for t in texts:
            by_type.setdefault(t["reasoning_type"], []).append(t)
        texts = []
        for rtype_texts in by_type.values():
            texts.extend(rtype_texts[:args.limit])
    versions = load_versions(versions_path, version_filter=version_filter)

    timestamp = dt.datetime.now(dt.UTC)
    run_id = args.run_id or timestamp.strftime("run_%Y%m%d_%H%M%S")
    output_dir = pathlib.Path(args.output_dir)
    run_dir = output_dir / run_id

    if args.resume:
        if not run_dir.exists():
            raise FileNotFoundError(f"Cannot resume — run dir not found: {run_dir}")
    else:
        run_dir.mkdir(parents=True, exist_ok=False)

    tasks = build_collect_tasks(versions, texts, num_runs, run_id)

    partial_path = run_dir / "formalizations.partial.jsonl"
    final_path = run_dir / "formalizations.jsonl"
    checkpoint_ids: set[str] = set()
    if args.resume:
        checkpoint_source = partial_path if partial_path.exists() else final_path
        if checkpoint_source.exists():
            checkpoint_ids = load_checkpoint_ids(checkpoint_source)
            if not partial_path.exists():
                # Copy final to partial for incremental append
                import shutil
                shutil.copy2(checkpoint_source, partial_path)

    tasks_to_run = [t for t in tasks if t["sample_id"] not in checkpoint_ids]

    meta = {
        "phase": "collect",
        "run_id": run_id,
        "timestamp_utc": timestamp.isoformat(),
        "corpus_path": corpus_path,
        "versions_path": versions_path,
        "model": model,
        "num_runs": num_runs,
        "text_count": len(texts),
        "version_count": len(versions),
        "task_count": len(tasks),
        "resumed": bool(args.resume),
        "checkpoint_rows": len(checkpoint_ids),
        "remaining_rows": len(tasks_to_run),
        "dry_run": bool(args.dry_run),
        "type_filter": type_filter,
        "version_filter": version_filter,
    }
    write_json(run_dir / "collect_meta.json", meta)

    total = len(tasks)
    completed = len(checkpoint_ids)
    phase_error_count = 0
    phase_started_at = utc_now_iso()
    phase_started_perf = time.perf_counter()
    progress_file = resolve_progress_file(args.progress_file)

    emit_phase_progress(
        progress_file=progress_file,
        phase="collect",
        status="running",
        total=total,
        completed=completed,
        checkpointed=len(checkpoint_ids),
        errors=phase_error_count,
        started_at_utc=phase_started_at,
        started_perf=phase_started_perf,
        run_id=run_id,
        run_dir=str(run_dir),
        message="Collecting formalizations",
    )

    if args.dry_run:
        print(f"DRY RUN: {len(tasks_to_run)} tasks to process "
              f"({len(texts)} texts × {len(versions)} versions × {num_runs} runs)",
              flush=True)
        if args.dry_run and not tasks_to_run:
            print("Nothing to do (all checkpointed).", flush=True)
            emit_phase_progress(
                progress_file=progress_file,
                phase="collect",
                status="done",
                total=total,
                completed=completed,
                checkpointed=len(checkpoint_ids),
                errors=phase_error_count,
                started_at_utc=phase_started_at,
                started_perf=phase_started_perf,
                run_id=run_id,
                run_dir=str(run_dir),
                message="Collect complete",
            )
            return 0

    parallelism = collect_cfg.get("parallelism", 1)
    print(f"Collecting: {len(tasks_to_run)} tasks "
          f"({total} total, {completed} checkpointed, "
          f"parallelism={parallelism})", flush=True)

    records: list[dict[str, Any]] = []
    io_lock = threading.Lock()

    def _process_collect(task: dict[str, Any]) -> dict[str, Any]:
        record = collect_one(
            task,
            base_dir=base_dir,
            model=model,
            timeout=timeout,
            dry_run=bool(args.dry_run),
        )
        record["status"] = "error" if record.get("error") else "ok"
        return record

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, parallelism)
    ) as executor:
        futures = {
            executor.submit(_process_collect, task): task
            for task in tasks_to_run
        }
        for future in concurrent.futures.as_completed(futures):
            record = future.result()
            with io_lock:
                completed += 1
                records.append(record)
                append_jsonl(partial_path, record)
                status = record["status"]
                if status == "error":
                    phase_error_count += 1
                error_suffix = (
                    f" error={record['error']}" if status == "error" else ""
                )
                print(
                    f"[collect {completed}/{total}] {status} "
                    f"version={record['version_id']} text={record['text_id']} "
                    f"run={record['run_index']}{error_suffix}",
                    flush=True,
                )
                emit_phase_progress(
                    progress_file=progress_file,
                    phase="collect",
                    status="running",
                    total=total,
                    completed=completed,
                    checkpointed=len(checkpoint_ids),
                    errors=phase_error_count,
                    started_at_utc=phase_started_at,
                    started_perf=phase_started_perf,
                    run_id=run_id,
                    run_dir=str(run_dir),
                    message=(
                        f"{record['version_id']} / {record['text_id']} "
                        f"(run {record['run_index']})"
                    ),
                )

    all_records: list[dict[str, Any]] = []
    if partial_path.exists():
        all_records = read_jsonl(partial_path)
    all_records.sort(key=lambda r: (
        str(r.get("version_id", "")),
        str(r.get("text_id", "")),
        int(r.get("run_index", 0)),
    ))
    write_jsonl(final_path, all_records)

    error_count = sum(1 for r in all_records if r.get("error"))
    stats = {
        "total_records": len(all_records),
        "error_count": error_count,
        "success_count": len(all_records) - error_count,
    }
    write_json(run_dir / "collect_stats.json", stats)

    print(f"\nCollection complete. {len(all_records)} records, "
          f"{error_count} errors.", flush=True)
    print(f"Artifacts: {run_dir}", flush=True)

    emit_phase_progress(
        progress_file=progress_file,
        phase="collect",
        status="error" if error_count > 0 else "done",
        total=total,
        completed=completed,
        checkpointed=len(checkpoint_ids),
        errors=error_count,
        started_at_utc=phase_started_at,
        started_perf=phase_started_perf,
        run_id=run_id,
        run_dir=str(run_dir),
        message="Collect complete",
    )

    if error_count > 0 and args.fail_on_error:
        return 2
    return 0


# --- grade subcommand ---

def grade_one(
    row: dict[str, Any],
    *,
    judge_model: str,
    timeout: int,
    dry_run: bool,
) -> dict[str, Any]:
    """Grade a single formalization via Socratic evaluation."""
    started_at = utc_now_iso()
    t0 = time.perf_counter()

    grade_row: dict[str, Any] = {
        "sample_id": row["sample_id"],
        "run_index": row.get("run_index"),
        "version_id": row["version_id"],
        "text_id": row["text_id"],
        "reasoning_type": row.get("reasoning_type", ""),
        "difficulty": row.get("difficulty", ""),
        "text": row.get("text", ""),
        "formalization": row.get("formalization", ""),
        "judge_model": judge_model,
        "judge_score": None,
        "judge_justification": "",
        "judge_raw_text": "",
        "judge_latency_ms": None,
        "judge_started_at_utc": started_at,
        "judge_finished_at_utc": None,
        "error": "",
    }

    try:
        if row.get("error"):
            raise RuntimeError(f"Cannot grade: source had error: {row['error']}")

        formalization = str(row.get("formalization", "")).strip()
        if not formalization:
            raise RuntimeError("Cannot grade empty formalization.")

        judge_prompt = JUDGE_USER_TEMPLATE.replace(
            "{text}", row.get("text", "")
        ).replace(
            "{formalization}", formalization
        )

        if dry_run:
            raw_text = json.dumps({
                "justification": "Dry run placeholder grade.",
                "score": 1,
            })
        else:
            raw_text = run_claude(
                judge_prompt,
                system_prompt=JUDGE_SYSTEM_PROMPT,
                model=judge_model,
                timeout=timeout,
            )

        grade_row["judge_raw_text"] = raw_text
        parsed = parse_json_output(raw_text)

        score = parsed.get("score")
        if not isinstance(score, int) or score not in (0, 1, 2):
            raise ValueError(f"Judge score must be 0, 1, or 2. Got: {score}")

        justification = parsed.get("justification", "")
        if not isinstance(justification, str) or not justification.strip():
            raise ValueError("Judge justification must be a non-empty string.")

        grade_row["judge_score"] = score
        grade_row["judge_justification"] = justification.strip()
    except Exception as exc:
        grade_row["error"] = str(exc)
    finally:
        grade_row["judge_latency_ms"] = int((time.perf_counter() - t0) * 1000)
        grade_row["judge_finished_at_utc"] = utc_now_iso()

    return grade_row


def run_grade(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    grade_cfg = config.get("grade", {})

    judge_model = args.judge_model or grade_cfg.get("judge_model", "claude-sonnet-4-6")
    timeout = grade_cfg.get("timeout_seconds", 300)

    if not args.responses_file:
        raise ValueError("--responses-file is required.")

    responses_path = pathlib.Path(args.responses_file)
    if not responses_path.exists():
        raise FileNotFoundError(f"Responses file not found: {responses_path}")

    rows = read_jsonl(responses_path)
    if not rows:
        raise ValueError("Responses file is empty.")

    run_dir = responses_path.parent
    grade_dir = run_dir / "grades"
    grade_id = args.grade_id or dt.datetime.now(dt.UTC).strftime(
        "%Y%m%d_%H%M%S"
    ) + f"_{to_slug(judge_model)}"

    grade_run_dir = grade_dir / grade_id
    if args.resume:
        if not grade_run_dir.exists():
            raise FileNotFoundError(f"Cannot resume: {grade_run_dir}")
    else:
        grade_run_dir.mkdir(parents=True, exist_ok=False)

    partial_path = grade_run_dir / "grades.partial.jsonl"
    final_path = grade_run_dir / "grades.jsonl"
    checkpoint_ids: set[str] = set()
    if args.resume:
        checkpoint_source = partial_path if partial_path.exists() else final_path
        if checkpoint_source.exists():
            checkpoint_ids = load_checkpoint_ids(checkpoint_source)
            if not partial_path.exists():
                import shutil
                shutil.copy2(checkpoint_source, partial_path)

    rows_to_grade = [
        r for r in rows
        if str(r.get("sample_id", "")).strip() not in checkpoint_ids
    ]

    meta = {
        "phase": "grade",
        "grade_id": grade_id,
        "judge_model": judge_model,
        "responses_file": str(responses_path.resolve()),
        "total_rows": len(rows),
        "checkpoint_rows": len(checkpoint_ids),
        "remaining_rows": len(rows_to_grade),
        "dry_run": bool(args.dry_run),
    }
    write_json(grade_run_dir / "grade_meta.json", meta)

    total = len(rows)
    completed = len(checkpoint_ids)
    phase_error_count = 0
    phase_started_at = utc_now_iso()
    phase_started_perf = time.perf_counter()
    progress_file = resolve_progress_file(args.progress_file)

    emit_phase_progress(
        progress_file=progress_file,
        phase="grade",
        status="running",
        total=total,
        completed=completed,
        checkpointed=len(checkpoint_ids),
        errors=phase_error_count,
        started_at_utc=phase_started_at,
        started_perf=phase_started_perf,
        run_id=run_dir.name,
        run_dir=str(run_dir),
        message="Grading formalizations",
    )

    parallelism = grade_cfg.get("parallelism", config.get("collect", {}).get("parallelism", 1))
    print(f"Grading: {len(rows_to_grade)} rows "
          f"({total} total, {completed} checkpointed, "
          f"parallelism={parallelism})", flush=True)

    io_lock = threading.Lock()

    def _process_grade(row: dict[str, Any]) -> dict[str, Any]:
        grade_row = grade_one(
            row,
            judge_model=judge_model,
            timeout=timeout,
            dry_run=bool(args.dry_run),
        )
        grade_row["status"] = "error" if grade_row.get("error") else "ok"
        return grade_row

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, parallelism)
    ) as executor:
        futures = {
            executor.submit(_process_grade, row): row
            for row in rows_to_grade
        }
        for future in concurrent.futures.as_completed(futures):
            grade_row = future.result()
            with io_lock:
                completed += 1
                append_jsonl(partial_path, grade_row)
                status = grade_row["status"]
                if status == "error":
                    phase_error_count += 1
                score_str = str(grade_row.get("judge_score", "?"))
                error_suffix = (
                    f" error={grade_row['error']}" if status == "error" else ""
                )
                print(
                    f"[grade {completed}/{total}] {status} score={score_str} "
                    f"version={grade_row['version_id']} "
                    f"text={grade_row['text_id']}{error_suffix}",
                    flush=True,
                )
                emit_phase_progress(
                    progress_file=progress_file,
                    phase="grade",
                    status="running",
                    total=total,
                    completed=completed,
                    checkpointed=len(checkpoint_ids),
                    errors=phase_error_count,
                    started_at_utc=phase_started_at,
                    started_perf=phase_started_perf,
                    run_id=run_dir.name,
                    run_dir=str(run_dir),
                    message=(
                        f"{grade_row['version_id']} / {grade_row['text_id']} "
                        f"score={score_str}"
                    ),
                )

    all_grades: list[dict[str, Any]] = []
    if partial_path.exists():
        all_grades = read_jsonl(partial_path)
    all_grades.sort(key=lambda r: (
        str(r.get("version_id", "")),
        str(r.get("text_id", "")),
        int(r.get("run_index", 0)),
    ))
    write_jsonl(final_path, all_grades)

    summary = summarize_grades(all_grades)
    write_json(grade_run_dir / "grade_summary.json", summary)

    error_count = sum(1 for r in all_grades if r.get("error"))
    print(f"\nGrading complete. {len(all_grades)} rows, {error_count} errors.",
          flush=True)
    print(f"Artifacts: {grade_run_dir}", flush=True)

    emit_phase_progress(
        progress_file=progress_file,
        phase="grade",
        status="error" if error_count > 0 else "done",
        total=total,
        completed=completed,
        checkpointed=len(checkpoint_ids),
        errors=error_count,
        started_at_utc=phase_started_at,
        started_perf=phase_started_perf,
        run_id=run_dir.name,
        run_dir=str(run_dir),
        message="Grade complete",
    )

    if error_count > 0 and args.fail_on_error:
        return 2
    return 0


def summarize_grades(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute per-version and per-type grade summaries."""
    by_version: dict[str, dict[str, Any]] = {}
    by_version_type: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for row in rows:
        vid = str(row.get("version_id", ""))
        if vid not in by_version:
            by_version[vid] = {
                "version_id": vid,
                "version_name": row.get("version_name", vid),
                "count": 0,
                "scored_count": 0,
                "score_0": 0,
                "score_1": 0,
                "score_2": 0,
                "avg_score": None,
                "interrogation_ready_rate": None,
                "error_count": 0,
            }

        stats = by_version[vid]
        stats["count"] += 1
        if row.get("error"):
            stats["error_count"] += 1

        score = row.get("judge_score")
        if score in (0, 1, 2):
            score_int = int(score)
            stats["scored_count"] += 1
            stats[f"score_{score_int}"] += 1
            rtype = str(row.get("reasoning_type", ""))
            by_version_type[vid][rtype].append(score_int)

    leaderboard: list[dict[str, Any]] = []
    for vid, stats in by_version.items():
        scored = stats["scored_count"]
        if scored > 0:
            total_score = stats["score_0"] * 0 + stats["score_1"] * 1 + stats["score_2"] * 2
            stats["avg_score"] = round(total_score / scored, 4)
            stats["interrogation_ready_rate"] = round(stats["score_2"] / scored, 4)

        technique_scores = by_version_type[vid]
        stats["type_breakdown"] = {
            rtype: round(sum(scores) / len(scores), 4)
            for rtype, scores in sorted(technique_scores.items())
            if scores
        }
        leaderboard.append(stats)

    leaderboard.sort(
        key=lambda item: (
            item["avg_score"] if isinstance(item["avg_score"], (int, float)) else -1,
        ),
        reverse=True,
    )

    return {
        "leaderboard": leaderboard,
        "total_records": len(rows),
        "total_scored": sum(1 for r in rows if r.get("judge_score") in (0, 1, 2)),
        "total_errors": sum(1 for r in rows if r.get("error")),
    }


# --- compare subcommand ---

def run_compare(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    compare_cfg = config.get("compare", {})
    grade_cfg = config.get("grade", {})

    judge_model = args.judge_model or grade_cfg.get("judge_model", "claude-sonnet-4-6")
    timeout = grade_cfg.get("timeout_seconds", 300)
    pairs = compare_cfg.get("pairs", [])

    if args.pair:
        pair_parts = args.pair.split(",")
        if len(pair_parts) != 2:
            raise ValueError("--pair must be 'version_a,version_b'")
        pairs = [pair_parts]

    if not pairs:
        raise ValueError("No comparison pairs specified in config or --pair.")

    if not args.responses_file:
        raise ValueError("--responses-file is required.")

    responses_path = pathlib.Path(args.responses_file)
    rows = read_jsonl(responses_path)

    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("version_id", "")), str(row.get("text_id", "")))
        by_key[key] = row

    run_dir = responses_path.parent
    compare_dir = run_dir / "comparisons"
    compare_id = args.compare_id or dt.datetime.now(dt.UTC).strftime("%Y%m%d_%H%M%S")
    compare_run_dir = compare_dir / compare_id
    compare_run_dir.mkdir(parents=True, exist_ok=True)

    partial_path = compare_run_dir / "comparisons.partial.jsonl"
    final_path = compare_run_dir / "comparisons.jsonl"

    checkpoint_ids = load_checkpoint_ids(partial_path) if partial_path.exists() else set()

    # Build comparison tasks
    text_ids = sorted({str(r.get("text_id", "")) for r in rows})
    tasks: list[dict[str, Any]] = []
    for pair in pairs:
        version_a, version_b = pair[0], pair[1]
        for text_id in text_ids:
            sample_id = f"cmp__{version_a}__{version_b}__{text_id}"
            if sample_id in checkpoint_ids:
                continue
            row_a = by_key.get((version_a, text_id))
            row_b = by_key.get((version_b, text_id))
            if not row_a or not row_b:
                continue
            tasks.append({
                "sample_id": sample_id,
                "version_a": version_a,
                "version_b": version_b,
                "text_id": text_id,
                "text": row_a.get("text", ""),
                "formalization_a": row_a.get("formalization", ""),
                "formalization_b": row_b.get("formalization", ""),
                "reasoning_type": row_a.get("reasoning_type", ""),
            })

    total = len(tasks) + len(checkpoint_ids)
    completed = len(checkpoint_ids)
    phase_error_count = 0
    phase_started_at = utc_now_iso()
    phase_started_perf = time.perf_counter()
    progress_file = resolve_progress_file(args.progress_file)

    emit_phase_progress(
        progress_file=progress_file,
        phase="compare",
        status="running",
        total=total,
        completed=completed,
        checkpointed=len(checkpoint_ids),
        errors=phase_error_count,
        started_at_utc=phase_started_at,
        started_perf=phase_started_perf,
        run_id=run_dir.name,
        run_dir=str(run_dir),
        message="Running pairwise comparisons",
    )

    parallelism = (
        args.parallelism
        or compare_cfg.get("parallelism")
        or config.get("collect", {}).get("parallelism", 1)
    )
    print(
        f"Comparing: {len(tasks)} tasks "
        f"({total} total, {len(checkpoint_ids)} checkpointed, "
        f"across {len(pairs)} pairs, "
        f"(parallelism={parallelism})",
        flush=True,
    )

    io_lock = threading.Lock()

    def _process_compare(task: dict[str, Any]) -> dict[str, Any]:
        # Randomize presentation order
        coin = random.random() < 0.5
        if coin:
            fa, fb = task["formalization_a"], task["formalization_b"]
            order = "original"
        else:
            fa, fb = task["formalization_b"], task["formalization_a"]
            order = "swapped"

        prompt = COMPARE_USER_TEMPLATE.replace(
            "{text}", task["text"]
        ).replace(
            "{formalization_a}", fa
        ).replace(
            "{formalization_b}", fb
        )

        result: dict[str, Any] = {
            "sample_id": task["sample_id"],
            "version_a": task["version_a"],
            "version_b": task["version_b"],
            "text_id": task["text_id"],
            "reasoning_type": task["reasoning_type"],
            "presentation_order": order,
            "judge_model": judge_model,
            "winner_raw": None,
            "winner_normalized": None,
            "score": None,
            "justification": "",
            "error": "",
        }

        try:
            if args.dry_run:
                raw = json.dumps({"justification": "Dry run.", "winner": "tie"})
            else:
                raw = run_claude(
                    prompt,
                    system_prompt=COMPARE_SYSTEM_PROMPT,
                    model=judge_model,
                    timeout=timeout,
                )

            parsed = parse_json_output(raw)
            winner_raw = str(parsed.get("winner", "")).strip().upper()
            result["winner_raw"] = winner_raw
            result["justification"] = str(parsed.get("justification", "")).strip()

            # Normalize winner based on presentation order
            if winner_raw == "TIE":
                result["winner_normalized"] = "tie"
                result["score"] = 0
            elif winner_raw == "A":
                if order == "original":
                    result["winner_normalized"] = task["version_a"]
                    result["score"] = 1  # version_a wins
                else:
                    result["winner_normalized"] = task["version_b"]
                    result["score"] = -1  # version_b wins
            elif winner_raw == "B":
                if order == "original":
                    result["winner_normalized"] = task["version_b"]
                    result["score"] = -1
                else:
                    result["winner_normalized"] = task["version_a"]
                    result["score"] = 1
            else:
                raise ValueError(f"Invalid winner value: {winner_raw}")

        except Exception as exc:
            result["error"] = str(exc)

        result["status"] = "error" if result.get("error") else "ok"
        return result

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, parallelism)
    ) as executor:
        futures = {
            executor.submit(_process_compare, task): task
            for task in tasks
        }
        for future in concurrent.futures.as_completed(futures):
            task = futures[future]
            result = future.result()
            with io_lock:
                completed += 1
                append_jsonl(partial_path, result)
                status = result["status"]
                if status == "error":
                    phase_error_count += 1
                winner = result.get("winner_normalized", "?")
                error_suffix = (
                    f" error={result['error']}" if status == "error" else ""
                )
                print(
                    f"[compare {completed}/{total}] {status} "
                    f"{task['version_a']} vs {task['version_b']} "
                    f"text={task['text_id']} winner={winner}{error_suffix}",
                    flush=True,
                )
                emit_phase_progress(
                    progress_file=progress_file,
                    phase="compare",
                    status="running",
                    total=total,
                    completed=completed,
                    checkpointed=len(checkpoint_ids),
                    errors=phase_error_count,
                    started_at_utc=phase_started_at,
                    started_perf=phase_started_perf,
                    run_id=run_dir.name,
                    run_dir=str(run_dir),
                    message=(
                        f"{task['version_a']} vs {task['version_b']} "
                        f"/ {task['text_id']} -> {winner}"
                    ),
                )

    all_comparisons: list[dict[str, Any]] = []
    if partial_path.exists():
        all_comparisons = read_jsonl(partial_path)
    all_comparisons.sort(key=lambda r: (
        str(r.get("version_a", "")),
        str(r.get("version_b", "")),
        str(r.get("text_id", "")),
    ))
    write_jsonl(final_path, all_comparisons)

    summary = summarize_comparisons(all_comparisons)
    write_json(compare_run_dir / "compare_summary.json", summary)
    error_count = sum(1 for row in all_comparisons if row.get("error"))

    print(f"\nComparison complete. {len(all_comparisons)} rows.", flush=True)
    print(f"Artifacts: {compare_run_dir}", flush=True)

    emit_phase_progress(
        progress_file=progress_file,
        phase="compare",
        status="error" if error_count > 0 else "done",
        total=total,
        completed=completed,
        checkpointed=len(checkpoint_ids),
        errors=error_count,
        started_at_utc=phase_started_at,
        started_perf=phase_started_perf,
        run_id=run_dir.name,
        run_dir=str(run_dir),
        message="Compare complete",
    )

    return 0


def summarize_comparisons(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize pairwise comparison results."""
    by_pair: dict[str, dict[str, Any]] = {}

    for row in rows:
        if row.get("error"):
            continue
        pair_key = f"{row.get('version_a', '')} vs {row.get('version_b', '')}"
        if pair_key not in by_pair:
            by_pair[pair_key] = {
                "version_a": row.get("version_a", ""),
                "version_b": row.get("version_b", ""),
                "a_wins": 0,
                "b_wins": 0,
                "ties": 0,
                "total": 0,
                "scores": [],
            }
        stats = by_pair[pair_key]
        stats["total"] += 1
        score = row.get("score", 0)
        stats["scores"].append(score)
        if score > 0:
            stats["a_wins"] += 1
        elif score < 0:
            stats["b_wins"] += 1
        else:
            stats["ties"] += 1

    pair_summaries: list[dict[str, Any]] = []
    for pair_key, stats in by_pair.items():
        avg_score = (
            round(sum(stats["scores"]) / len(stats["scores"]), 4)
            if stats["scores"] else None
        )
        pair_summaries.append({
            "pair": pair_key,
            "version_a": stats["version_a"],
            "version_b": stats["version_b"],
            "a_wins": stats["a_wins"],
            "b_wins": stats["b_wins"],
            "ties": stats["ties"],
            "total": stats["total"],
            "avg_score": avg_score,
            "a_win_rate": round(stats["a_wins"] / stats["total"], 4) if stats["total"] else None,
        })

    return {
        "pair_summaries": pair_summaries,
        "total_comparisons": len(rows),
        "total_errors": sum(1 for r in rows if r.get("error")),
    }


# --- aggregate subcommand ---

def run_aggregate(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    compare_cfg = config.get("compare", {})

    run_dir = pathlib.Path(args.run_dir)
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    progress_file = resolve_progress_file(args.progress_file)
    phase_started_at = utc_now_iso()
    phase_started_perf = time.perf_counter()
    phase_total = 1

    emit_phase_progress(
        progress_file=progress_file,
        phase="aggregate",
        status="running",
        total=phase_total,
        completed=0,
        checkpointed=0,
        errors=0,
        started_at_utc=phase_started_at,
        started_perf=phase_started_perf,
        run_id=run_dir.name,
        run_dir=str(run_dir),
        message="Building aggregate summary",
    )

    try:
        grades_path = None
        grades_rel = None
        grade_dirs = sorted((run_dir / "grades").iterdir()) if (run_dir / "grades").exists() else []
        for gd in grade_dirs:
            candidate = gd / "grades.jsonl"
            if candidate.exists():
                grades_path = candidate
                grades_rel = str(gd.relative_to(run_dir))
                break
        if not grades_path:
            raise FileNotFoundError("No grades.jsonl found in run directory.")

        grade_rows = read_jsonl(grades_path)
        grade_summary = summarize_grades(grade_rows)

        compare_summary: dict[str, Any] = {}
        comparisons_rel = None
        compare_dirs = sorted(
            (run_dir / "comparisons").iterdir()
        ) if (run_dir / "comparisons").exists() else []
        for cd in compare_dirs:
            candidate = cd / "comparisons.jsonl"
            if candidate.exists():
                compare_rows = read_jsonl(candidate)
                compare_summary = summarize_comparisons(compare_rows)
                comparisons_rel = str(cd.relative_to(run_dir))
                break

        ablation_impact: list[dict[str, Any]] = []
        if compare_summary.get("pair_summaries"):
            for pair in compare_summary["pair_summaries"]:
                vb = pair.get("version_b", "")
                if vb.startswith("v3_no_"):
                    section = vb.replace("v3_no_", "")
                    ablation_impact.append({
                        "section": section,
                        "version_a": pair["version_a"],
                        "version_b": pair["version_b"],
                        "a_wins": pair["a_wins"],
                        "b_wins": pair["b_wins"],
                        "ties": pair["ties"],
                        "total": pair["total"],
                        "avg_score": pair["avg_score"],
                        "net_impact": pair["a_wins"] - pair["b_wins"],
                        "impact_label": (
                            "section helps" if pair["a_wins"] > pair["b_wins"]
                            else "section hurts" if pair["b_wins"] > pair["a_wins"]
                            else "no net effect"
                        ),
                    })

        per_type: dict[str, dict[str, float]] = {}
        for entry in grade_summary.get("leaderboard", []):
            vid = entry["version_id"]
            per_type[vid] = entry.get("type_breakdown", {})

        aggregate = {
            "leaderboard": grade_summary.get("leaderboard", []),
            "per_type_breakdown": per_type,
            "comparison_pairs": compare_summary.get("pair_summaries", []),
            "ablation_impact": ablation_impact,
            "total_formalizations": grade_summary.get("total_records", 0),
            "total_comparisons": compare_summary.get("total_comparisons", 0),
        }

        agg_dir = run_dir / "aggregate"
        agg_dir.mkdir(parents=True, exist_ok=True)
        write_json(agg_dir / "aggregate_summary.json", aggregate)

        # Leaderboard CSV
        _write_leaderboard_csv(agg_dir / "leaderboard.csv", grade_summary.get("leaderboard", []))

        # Run manifest for the viewer (subdirectory discovery)
        manifest = {"run_id": run_dir.name}
        if grades_rel:
            manifest["grades_dir"] = grades_rel
        if comparisons_rel:
            manifest["comparisons_dir"] = comparisons_rel
        write_json(run_dir / "run_manifest.json", manifest)

        print(f"Aggregate complete.", flush=True)
        print(f"Artifacts: {agg_dir}", flush=True)
        _print_leaderboard(grade_summary.get("leaderboard", []))

        if ablation_impact:
            print("\nAblation Impact:")
            for ai in sorted(ablation_impact, key=lambda x: x.get("net_impact", 0), reverse=True):
                print(
                    f"  {ai['section']:30s}  "
                    f"net={ai['net_impact']:+d}  "
                    f"(full wins {ai['a_wins']}, ablated wins {ai['b_wins']}, "
                    f"ties {ai['ties']})  → {ai['impact_label']}",
                    flush=True,
                )

        emit_phase_progress(
            progress_file=progress_file,
            phase="aggregate",
            status="done",
            total=phase_total,
            completed=phase_total,
            checkpointed=0,
            errors=0,
            started_at_utc=phase_started_at,
            started_perf=phase_started_perf,
            run_id=run_dir.name,
            run_dir=str(run_dir),
            message="Aggregate complete",
        )
        return 0
    except Exception as exc:
        emit_phase_progress(
            progress_file=progress_file,
            phase="aggregate",
            status="error",
            total=phase_total,
            completed=phase_total,
            checkpointed=0,
            errors=1,
            started_at_utc=phase_started_at,
            started_perf=phase_started_perf,
            run_id=run_dir.name,
            run_dir=str(run_dir),
            message=str(exc),
        )
        raise


def _write_leaderboard_csv(
    path: pathlib.Path,
    leaderboard: list[dict[str, Any]],
) -> None:
    fieldnames = [
        "rank", "version_id", "version_name", "avg_score",
        "interrogation_ready_rate", "score_0", "score_1", "score_2",
        "scored_count", "error_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for rank, entry in enumerate(leaderboard, 1):
            writer.writerow({
                "rank": rank,
                "version_id": entry["version_id"],
                "version_name": entry.get("version_name", ""),
                "avg_score": entry.get("avg_score", ""),
                "interrogation_ready_rate": entry.get("interrogation_ready_rate", ""),
                "score_0": entry.get("score_0", 0),
                "score_1": entry.get("score_1", 0),
                "score_2": entry.get("score_2", 0),
                "scored_count": entry.get("scored_count", 0),
                "error_count": entry.get("error_count", 0),
            })


def _print_leaderboard(leaderboard: list[dict[str, Any]]) -> None:
    print("\nLeaderboard:")
    print(f"{'Rank':<6}{'Version':<40}{'Avg':>6}{'IR%':>8}"
          f"{'0':>5}{'1':>5}{'2':>5}{'Err':>5}")
    print("-" * 80)
    for rank, entry in enumerate(leaderboard, 1):
        avg = entry.get("avg_score")
        avg_str = f"{avg:.2f}" if isinstance(avg, (int, float)) else "n/a"
        ir = entry.get("interrogation_ready_rate")
        ir_str = f"{ir:.2%}" if isinstance(ir, (int, float)) else "n/a"
        print(
            f"{rank:<6}{entry['version_id']:<40}{avg_str:>6}{ir_str:>8}"
            f"{entry.get('score_0', 0):>5}{entry.get('score_1', 0):>5}"
            f"{entry.get('score_2', 0):>5}{entry.get('error_count', 0):>5}"
        )


# --- CLI ---

def _load_config(path: str) -> dict[str, Any]:
    config_path = pathlib.Path(path)
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _split_csv(value: str) -> list[str]:
    if not value or not value.strip():
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear Reason formalization quality evaluation pipeline."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- collect --
    collect = subparsers.add_parser(
        "collect",
        help="Formalize test texts under each prompt version.",
    )
    collect.add_argument("--config", default="config.json")
    collect.add_argument("--corpus", default="",
                         help="Path to test_corpus.json (default from config).")
    collect.add_argument("--versions", default="",
                         help="Path to prompt_versions.json (default from config).")
    collect.add_argument("--model", default="",
                         help="Model for formalization (default from config).")
    collect.add_argument("--output-dir", default="runs")
    collect.add_argument("--run-id", default="")
    collect.add_argument("--num-runs", type=int, default=0,
                         help="Number of independent repeats (default from config).")
    collect.add_argument("--version-filter", default="",
                         help="Comma-separated version IDs to include.")
    collect.add_argument("--type-filter", default="",
                         help="Comma-separated reasoning type IDs to include.")
    collect.add_argument("--corpus-extra", default="",
                         help="Additional corpus file(s) to merge, comma-separated.")
    collect.add_argument("--limit", type=int, default=0,
                         help="Max texts per reasoning type (0 = all). Useful for smoke tests.")
    collect.add_argument("--dry-run", action="store_true")
    collect.add_argument("--resume", action="store_true")
    collect.add_argument("--fail-on-error", action="store_true", default=True)
    collect.add_argument("--no-fail-on-error", dest="fail_on_error",
                         action="store_false")
    collect.add_argument(
        "--progress-file",
        default="",
        help="Optional JSON file to receive live phase progress updates.",
    )

    # -- grade --
    grade = subparsers.add_parser(
        "grade",
        help="Socratic evaluation of collected formalizations.",
    )
    grade.add_argument("--config", default="config.json")
    grade.add_argument("--responses-file", default="",
                       help="Path to formalizations.jsonl from a collect run.")
    grade.add_argument("--judge-model", default="")
    grade.add_argument("--grade-id", default="")
    grade.add_argument("--dry-run", action="store_true")
    grade.add_argument("--resume", action="store_true")
    grade.add_argument("--fail-on-error", action="store_true", default=True)
    grade.add_argument("--no-fail-on-error", dest="fail_on_error",
                       action="store_false")
    grade.add_argument(
        "--progress-file",
        default="",
        help="Optional JSON file to receive live phase progress updates.",
    )

    # -- compare --
    compare = subparsers.add_parser(
        "compare",
        help="Pairwise blinded comparison of prompt versions.",
    )
    compare.add_argument("--config", default="config.json")
    compare.add_argument("--responses-file", default="",
                         help="Path to formalizations.jsonl.")
    compare.add_argument("--judge-model", default="")
    compare.add_argument("--pair", default="",
                         help="Single pair to compare: 'version_a,version_b'.")
    compare.add_argument("--compare-id", default="")
    compare.add_argument("--parallelism", type=int, default=0,
                         help="Max concurrent compare tasks (default from config).")
    compare.add_argument("--dry-run", action="store_true")
    compare.add_argument("--fail-on-error", action="store_true", default=True)
    compare.add_argument("--no-fail-on-error", dest="fail_on_error",
                         action="store_false")
    compare.add_argument(
        "--progress-file",
        default="",
        help="Optional JSON file to receive live phase progress updates.",
    )

    # -- aggregate --
    aggregate = subparsers.add_parser(
        "aggregate",
        help="Aggregate grades and comparisons into leaderboard.",
    )
    aggregate.add_argument("--config", default="config.json")
    aggregate.add_argument("--run-dir", required=True,
                           help="Path to a collect run directory.")
    aggregate.add_argument(
        "--progress-file",
        default="",
        help="Optional JSON file to receive live phase progress updates.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "collect":
        return run_collect(args)
    elif args.command == "grade":
        return run_grade(args)
    elif args.command == "compare":
        return run_compare(args)
    elif args.command == "aggregate":
        return run_aggregate(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
