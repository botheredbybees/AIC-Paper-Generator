#!/usr/bin/env python3
"""
launch_proposal_writer.py

Convert an AI Scientist ideas JSON (produced by generate_ideas_from_mcp.py)
into a 4-page ICBINB PDF research proposal using the existing AI Scientist
writeup machinery, bypassing the experiment execution phase.

Usage:
    python launch_proposal_writer.py \
        --load_ideas ai_scientist/ideas/elder_clowning.json \
        --idea_idx 0 \
        --model_writeup ollama/qwen2.5:14b \
        --model_citation ollama/qwen2.5:14b
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# NOTE: os.chdir(Path(__file__).parent) is called inside main() to avoid
# mutating the working directory at import time.


# ---------------------------------------------------------------------------
# Experiment folder setup
# ---------------------------------------------------------------------------

def setup_experiment_folder(
    experiments_base: str,
    idea: dict,
    attempt_id: int,
) -> tuple[str, dict]:
    """Create the experiment folder, write topic_data.json, return (folder, clean_idea)."""
    clean_idea = {k: v for k, v in idea.items() if not k.startswith("_")}
    topic_data = idea.get("_mcp_topic") or {}

    date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    folder = os.path.join(
        experiments_base,
        f"{date}_{clean_idea['Name']}_proposal_{attempt_id}",
    )
    os.makedirs(folder, exist_ok=True)

    with open(os.path.join(folder, "topic_data.json"), "w", encoding="utf-8") as f:
        json.dump(topic_data, f, indent=2)

    return folder, clean_idea


# ---------------------------------------------------------------------------
# Citation pre-population
# ---------------------------------------------------------------------------

def prepopulate_citations(
    folder: str,
    bibtex_entries: list[str],
    num_rounds: int,
) -> None:
    """Write cached_citations.bib + citations_progress.json to skip gather_citations() loop."""
    if not bibtex_entries:
        return

    os.makedirs(folder, exist_ok=True)
    seen: set[str] = set()
    unique_entries: list[str] = []
    for entry in bibtex_entries:
        if entry not in seen:
            seen.add(entry)
            unique_entries.append(entry)

    with open(os.path.join(folder, "cached_citations.bib"), "w", encoding="utf-8") as f:
        f.write("\n\n".join(unique_entries))

    with open(os.path.join(folder, "citations_progress.json"), "w", encoding="utf-8") as f:
        json.dump({"completed_rounds": num_rounds}, f)


# ---------------------------------------------------------------------------
# idea.md generation
# ---------------------------------------------------------------------------

PROPOSAL_NOTE = """
## Writing Instructions

This is a research proposal. No experiments have been conducted yet.
Write this paper as a structured literature review and research proposal:
present the open question, synthesise the existing evidence base, and
propose a concrete methodology. Do not fabricate experimental results.
Frame any results-like content as expected or projected outcomes.
Use the future tense for proposed work.
"""


def write_idea_md(idea: dict, output_path: str) -> None:
    """Write idea to markdown using bfts_utils, then append the proposal note."""
    from ai_scientist.treesearch.bfts_utils import idea_to_markdown

    # Third arg (load_code) is a required positional — pass None to skip code injection.
    idea_to_markdown(idea, output_path, None)

    with open(output_path, "a", encoding="utf-8") as f:
        f.write(PROPOSAL_NOTE)
