#!/usr/bin/env python3
"""Header-based section removal utility for ablation testing.

Removes named sections from a markdown prompt file, identified by
bold headers (**Header**:) or ### markdown headers. Used to produce
ablated variants of the Clear Reason prompt for controlled experiments.

Usage:
    python3 scripts/ablate.py <prompt_file> <section_id>
    python3 scripts/ablate.py <prompt_file> <section_id> --output-dir out/
    python3 scripts/ablate.py --list
"""

from __future__ import annotations

import argparse
import os
import re
import sys

ABLATION_HEADERS = {
    "constitutive_ambiguity": "**Constitutive Ambiguity Check**:",
    "causal_conjunction": "**causal connections disguised as conjunctions**",
    "form_recognition": "**Form Recognition**:",
    "pre_stripping_diagnostic": "**Pre-Stripping Diagnostic**:",
    "text_type_determination": "**Text-Type Determination**:",
    "default_determination": "**Default Determination**",
    "exformation_inventory": "### Exformation Inventory",
    "circumference_check": "**Circumference Check**:",
    "deep_audit": "**Deep Audit**",
}


def _header_level(line: str) -> int | None:
    """Return the effective header level of a line, or None if not a header.

    - ``### ...`` style headers use their native level (e.g. 3).
    - ``**Bold**:`` style headers are treated as level 4.
    """
    md_match = re.match(r"^(#{1,6})\s", line)
    if md_match:
        return len(md_match.group(1))

    if re.match(r"^\*\*[^*]+\*\*", line):
        return 4

    return None


def ablate_section(prompt_text: str, section_header: str) -> str:
    """Remove a named section from the prompt text.

    A "section" is one contiguous block: the header line and all
    non-header content following it, up to (but not including) the
    next line that is itself a header of *any* kind — regardless of
    level.  This means each ablation removes exactly one block of
    content without consuming sibling or child sections.

    Header detection: ``### ...`` markdown headers and ``**Bold**:``
    patterns at the start of a line are both recognised as headers.

    Args:
        prompt_text: The full markdown prompt as a string.
        section_header: The literal header text that starts the section
            to remove (e.g. ``"**Deep Audit**"``).

    Returns:
        The prompt text with the target section removed and any
        resulting runs of multiple blank lines collapsed to a single
        blank line.

    Raises:
        ValueError: If *section_header* is not found in the prompt.
    """
    lines = prompt_text.split("\n")

    start_idx: int | None = None
    for i, line in enumerate(lines):
        if section_header in line:
            start_idx = i
            break

    if start_idx is None:
        raise ValueError(
            f"Section header not found in prompt: {section_header!r}"
        )

    # Walk forward from the line after the header.  Stop at the first
    # line that is itself a header of any kind — don't use level
    # comparison, which would cause higher-level headers (like ###) to
    # swallow subordinate headers (like **Bold**:) that are actually
    # separate ablation targets.
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if _header_level(lines[i]) is not None:
            end_idx = i
            break

    result_lines = lines[:start_idx] + lines[end_idx:]

    # Collapse runs of 3+ consecutive blank lines into a single blank line.
    cleaned: list[str] = []
    blank_run = 0
    for line in result_lines:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                cleaned.append(line)
        else:
            blank_run = 0
            cleaned.append(line)

    return "\n".join(cleaned)


def get_ablated_prompt(prompt_path: str, section_id: str) -> str:
    """Read a prompt file and return it with the named section removed.

    Args:
        prompt_path: Path to the markdown prompt file.
        section_id: Key into :data:`ABLATION_HEADERS` identifying which
            section to remove.

    Returns:
        The ablated prompt text.

    Raises:
        KeyError: If *section_id* is not a recognised ablation target.
        FileNotFoundError: If *prompt_path* does not exist.
        ValueError: If the header is not found in the file contents.
    """
    if section_id not in ABLATION_HEADERS:
        available = ", ".join(sorted(ABLATION_HEADERS))
        raise KeyError(
            f"Unknown section_id {section_id!r}. "
            f"Available sections: {available}"
        )

    with open(prompt_path, "r", encoding="utf-8") as fh:
        prompt_text = fh.read()

    header = ABLATION_HEADERS[section_id]
    return ablate_section(prompt_text, header)


def generate_ablation_file(
    prompt_path: str, section_id: str, output_dir: str
) -> str:
    """Write an ablated prompt variant to disk.

    The output file is named ``v3_no_<section_id>.md`` inside
    *output_dir*.

    Args:
        prompt_path: Path to the source markdown prompt file.
        section_id: Key into :data:`ABLATION_HEADERS`.
        output_dir: Directory to write the ablated file into.

    Returns:
        The absolute path of the written file.
    """
    ablated = get_ablated_prompt(prompt_path, section_id)

    os.makedirs(output_dir, exist_ok=True)
    filename = f"v3_no_{section_id}.md"
    out_path = os.path.join(output_dir, filename)

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(ablated)

    return os.path.abspath(out_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remove a named section from a markdown prompt for ablation testing.",
    )
    parser.add_argument(
        "prompt_file",
        nargs="?",
        help="Path to the markdown prompt file.",
    )
    parser.add_argument(
        "section_id",
        nargs="?",
        help="Ablation section identifier (see --list).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Write ablated prompt to this directory instead of stdout.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_sections",
        help="List available section IDs and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list_sections:
        for sid, header in sorted(ABLATION_HEADERS.items()):
            print(f"  {sid:30s} {header}")
        return 0

    if not args.prompt_file or not args.section_id:
        parser.error("prompt_file and section_id are required (or use --list)")

    try:
        if args.output_dir:
            path = generate_ablation_file(
                args.prompt_file, args.section_id, args.output_dir
            )
            print(path)
        else:
            ablated = get_ablated_prompt(args.prompt_file, args.section_id)
            print(ablated)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
