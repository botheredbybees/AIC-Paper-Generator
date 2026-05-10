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
