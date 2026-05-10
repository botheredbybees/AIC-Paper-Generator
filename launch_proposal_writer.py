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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a research proposal PDF from an AI Scientist ideas JSON"
    )
    parser.add_argument("--load_ideas", required=True,
                        help="Path to ideas JSON produced by generate_ideas_from_mcp.py")
    parser.add_argument("--idea_idx", type=int, default=0,
                        help="Index of the idea to process (default: 0)")
    parser.add_argument("--model_writeup", default="ollama/qwen2.5:14b",
                        help="Ollama model for paper writing (maps to big_model)")
    parser.add_argument("--model_citation", default="ollama/qwen2.5:14b",
                        help="Ollama model for citation gathering (maps to small_model)")
    parser.add_argument("--num_cite_rounds", type=int, default=10,
                        help="Semantic Scholar citation rounds (skipped if citations pre-populated)")
    parser.add_argument("--writeup-type", default="icbinb",
                        choices=["icbinb", "normal"],
                        help="icbinb = 4-page, normal = 8-page")
    parser.add_argument("--attempt_id", type=int, default=0,
                        help="Disambiguates parallel runs")
    parser.add_argument("--skip_review", action="store_true", default=True,
                        help="Skip LLM peer review (default: True — no figures in proposal mode)")
    parser.add_argument("--no-skip-review", dest="skip_review", action="store_false",
                        help="Enable LLM peer review")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_ideas = Path(args.load_ideas).resolve()
    os.chdir(Path(__file__).parent)

    try:
        with open(load_ideas, encoding="utf-8") as f:
            ideas = json.load(f)
    except FileNotFoundError:
        print(f"Error: ideas file not found: {load_ideas}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {load_ideas}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(ideas, list):
        print(f"Error: {load_ideas} must contain a JSON array, got {type(ideas).__name__}", file=sys.stderr)
        sys.exit(1)

    if args.idea_idx >= len(ideas):
        print(f"Error: --idea_idx {args.idea_idx} is out of range "
              f"(JSON contains {len(ideas)} idea(s))", file=sys.stderr)
        sys.exit(1)

    idea = ideas[args.idea_idx]
    print(f"Processing idea {args.idea_idx}: {idea.get('Name', 'unknown')}")

    folder, clean_idea = setup_experiment_folder("experiments", idea, args.attempt_id)
    print(f"Experiment folder: {folder}")

    bibtex_entries = idea.get("_s2_bibtex") or []
    prepopulate_citations(folder, bibtex_entries, args.num_cite_rounds)
    if bibtex_entries:
        print(f"Pre-populated {len(bibtex_entries)} citation(s) from Semantic Scholar")
    else:
        print("No pre-populated citations — gather_citations() will run its full loop")

    idea_md_path = os.path.join(folder, "idea.md")
    write_idea_md(clean_idea, idea_md_path)
    print(f"Wrote {idea_md_path}")

    with open(os.path.join(folder, "idea.json"), "w", encoding="utf-8") as f:
        json.dump(clean_idea, f, indent=2)

    if args.writeup_type == "icbinb":
        from ai_scientist.perform_icbinb_writeup import gather_citations, perform_writeup
        page_limit = 4

        print("Gathering citations...")
        citations_text = gather_citations(
            base_folder=folder,
            num_cite_rounds=args.num_cite_rounds,
            small_model=args.model_citation,
        )

        print("Writing paper...")
        perform_writeup(
            base_folder=folder,
            citations_text=citations_text,
            num_cite_rounds=args.num_cite_rounds,
            small_model=args.model_citation,
            big_model=args.model_writeup,
            page_limit=page_limit,
        )
    else:
        from ai_scientist.perform_writeup import perform_writeup  # type: ignore[import]
        page_limit = 8

        print("Writing paper...")
        perform_writeup(
            base_folder=folder,
            num_cite_rounds=args.num_cite_rounds,
            small_model=args.model_citation,
            big_model=args.model_writeup,
            page_limit=page_limit,
        )

    if not args.skip_review:
        import glob
        from ai_scientist.llm import create_client
        from ai_scientist.perform_llm_review import load_paper, perform_review

        pdfs = sorted(glob.glob(os.path.join(folder, "*.pdf")))
        if pdfs:
            pdf_path = pdfs[-1]
            paper_content = load_paper(pdf_path)
            client, client_model = create_client(args.model_writeup)
            review = perform_review(paper_content, client_model, client)
            review_path = os.path.join(folder, "review.json")
            with open(review_path, "w", encoding="utf-8") as f:
                json.dump(review, f, indent=2)
            print(f"Review saved to {review_path}")
        else:
            print("No PDF found to review.")


if __name__ == "__main__":
    main()
