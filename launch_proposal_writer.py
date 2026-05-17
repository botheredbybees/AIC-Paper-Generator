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
        --model_writeup ollama/qwen2.5-coder:14b \
        --model_citation ollama/qwen2.5-coder:14b
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

# Optional import — module may not exist yet; imported here so tests can patch
# `launch_proposal_writer.perform_review_writeup` without error.
try:
    from ai_scientist.perform_review_writeup import perform_review_writeup  # noqa: F401
except ImportError:
    perform_review_writeup = None  # type: ignore[assignment]


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
# Option B: synthetic experiment summaries from MCP topic data
# ---------------------------------------------------------------------------

def write_synthetic_summaries(folder: str, topic_data: dict) -> None:
    """Populate logs/0-run/{research,baseline}_summary.json from MCP topic data.

    Gives the writeup LLM structured "findings" to report instead of empty
    dicts, making the generated paper substantively richer.

    Schema expected by filter_experiment_summaries():
        {"best node": {"overall_plan": str, "analysis": str, "metric": {}}}
    """
    logs_dir = os.path.join(folder, "logs", "0-run")
    os.makedirs(logs_dir, exist_ok=True)

    body = topic_data.get("body", "")
    key_findings: list[str] = topic_data.get("key_findings", [])
    open_questions: list[str] = topic_data.get("open_questions", [])

    analysis_lines = [f"- {f}" for f in key_findings]
    if open_questions:
        analysis_lines += ["", "Open research questions:"] + [f"- {q}" for q in open_questions]
    analysis_text = "\n".join(analysis_lines)

    research_summary = {
        "best node": {
            "overall_plan": body,
            "analysis": analysis_text,
            "metric": {},
        }
    }
    baseline_summary = {
        "best node": {
            "overall_plan": "No baseline experiment conducted (proposal mode).",
            "analysis": "This is a research proposal; no empirical baseline results are available.",
            "metric": {},
        }
    }

    with open(os.path.join(logs_dir, "research_summary.json"), "w", encoding="utf-8") as f:
        json.dump(research_summary, f, indent=2)
    with open(os.path.join(logs_dir, "baseline_summary.json"), "w", encoding="utf-8") as f:
        json.dump(baseline_summary, f, indent=2)


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
    parser.add_argument("--model_writeup", default="ollama/qwen2.5-coder:14b",
                        help="Ollama model for paper writing (maps to big_model)")
    parser.add_argument("--model_citation", default="ollama/qwen2.5-coder:14b",
                        help="Ollama model for citation gathering (maps to small_model)")
    parser.add_argument("--model_vlm", default="ollama/qwen2.5vl:7b",
                        help="Vision-capable Ollama model for figure/caption review")
    parser.add_argument("--num_cite_rounds", type=int, default=10,
                        help="Semantic Scholar citation rounds (skipped if citations pre-populated)")
    parser.add_argument("--writeup-type", default="icbinb",
                        choices=["icbinb", "normal", "review"],
                        help="icbinb = 4-page, normal = 8-page, review = APA 7 qualitative lit review")
    parser.add_argument("--attempt_id", type=int, default=0,
                        help="Disambiguates parallel runs")
    parser.add_argument("--skip_review", action="store_true", default=True,
                        help="Skip LLM peer review (default: True — no figures in proposal mode)")
    parser.add_argument("--no-skip-review", dest="skip_review", action="store_false",
                        help="Enable LLM peer review")
    parser.add_argument("--list-ideas", action="store_true",
                        help="Print the ideas in --load_ideas with their index and title, then exit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_ideas = Path(args.load_ideas).resolve()
    os.chdir(Path(__file__).parent)

    print(f"[STAGE 1/5] Loading ideas from {load_ideas}")
    try:
        with open(load_ideas, encoding="utf-8") as f:
            ideas = json.load(f)
    except FileNotFoundError:
        print(f"Error: ideas file not found: {load_ideas}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {load_ideas}: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.list_ideas:
        print(f"\n{'idx':<4}  {'name':<45}  title")
        print("-" * 100)
        for i, idea in enumerate(ideas):
            name = (idea.get("Name") or "")[:44]
            title = (idea.get("Title") or "")[:55]
            print(f"{i:<4}  {name:<45}  {title}")
        sys.exit(0)

    if not isinstance(ideas, list):
        print(f"Error: {load_ideas} must contain a JSON array, got {type(ideas).__name__}", file=sys.stderr)
        sys.exit(1)

    if args.idea_idx >= len(ideas):
        print(f"Error: --idea_idx {args.idea_idx} is out of range "
              f"(JSON contains {len(ideas)} idea(s))", file=sys.stderr)
        sys.exit(1)

    idea = ideas[args.idea_idx]
    print(f"  Idea [{args.idea_idx}/{len(ideas)-1}]: {idea.get('Name', 'unknown')!r}")

    print(f"\n[STAGE 2/5] Setting up experiment folder")
    folder, clean_idea = setup_experiment_folder("experiments", idea, args.attempt_id)
    print(f"  Folder: {folder}")

    bibtex_entries = idea.get("_s2_bibtex") or []
    prepopulate_citations(folder, bibtex_entries, args.num_cite_rounds)
    if bibtex_entries:
        print(f"  Pre-populated {len(bibtex_entries)} citation(s) from Semantic Scholar")
    else:
        print("  No pre-populated citations — gather_citations() will run its full loop")

    idea_md_path = os.path.join(folder, "idea.md")
    write_idea_md(clean_idea, idea_md_path)
    print(f"  Wrote idea.md and idea.json")

    with open(os.path.join(folder, "idea.json"), "w", encoding="utf-8") as f:
        json.dump(clean_idea, f, indent=2)

    topic_data = idea.get("_mcp_topic") or {}
    if topic_data:
        write_synthetic_summaries(folder, topic_data)
        print(f"  Wrote synthetic experiment summaries (Option B)")
    else:
        print(f"  No MCP topic data found — summaries will be empty")

    if args.writeup_type == "icbinb":
        from ai_scientist.perform_icbinb_writeup import gather_citations, perform_writeup
        page_limit = 4

        print(f"\n[STAGE 3/5] Gathering citations (model={args.model_citation}, "
              f"rounds={args.num_cite_rounds})")
        citations_text = gather_citations(
            base_folder=folder,
            num_cite_rounds=args.num_cite_rounds,
            small_model=args.model_citation,
        ) or ""
        print(f"  Citations gathered ({len(citations_text)} chars)")

        print(f"\n[STAGE 4/5] Writing {page_limit}-page paper "
              f"(writeup_model={args.model_writeup})")
        perform_writeup(
            base_folder=folder,
            citations_text=citations_text,
            num_cite_rounds=args.num_cite_rounds,
            small_model=args.model_citation,
            big_model=args.model_writeup,
            vlm_model=args.model_vlm,
            page_limit=page_limit,
        )
    elif args.writeup_type == "normal":
        from ai_scientist.perform_writeup import perform_writeup  # type: ignore[import]
        page_limit = 8

        print(f"\n[STAGE 3/5] Skipped (normal writeup manages citations internally)")
        print(f"\n[STAGE 4/5] Writing {page_limit}-page paper "
              f"(writeup_model={args.model_writeup})")
        perform_writeup(
            base_folder=folder,
            num_cite_rounds=args.num_cite_rounds,
            small_model=args.model_citation,
            big_model=args.model_writeup,
            vlm_model=args.model_vlm,
            page_limit=page_limit,
        )
    elif args.writeup_type == "review":
        import glob as _glob
        from ai_scientist.tools.pdf_reader import extract_sections

        print(f"\n[STAGE 3/5] Building tiered context for review writeup")

        # Tier 1: MCP synthesis
        tier1 = (idea.get("_mcp_topic") or {}).get("body", "")

        # Tier 2: manual PDFs from {stem}_pdfs/ folder alongside the ideas JSON
        pdf_dir = os.path.join(os.path.dirname(str(load_ideas)),
                               Path(load_ideas).stem + "_pdfs")
        tier2: dict = {}
        if os.path.isdir(pdf_dir):
            for pdf_path in _glob.glob(os.path.join(pdf_dir, "*.pdf")):
                citation_key = Path(pdf_path).stem
                sections = extract_sections(pdf_path, citation_key=citation_key)
                if sections:
                    tier2[citation_key] = sections
                    print(f"  [PDF] {citation_key}: {list(sections.keys())}")

        # Add OA fulltext from Stage 1 into Tier 2 (don't overwrite manual PDFs)
        for ck, sections in (idea.get("_oa_fulltext") or {}).items():
            if ck not in tier2:
                tier2[ck] = sections

        # Tier 3: all S2 abstracts
        tier3 = idea.get("_s2_papers") or []

        print(f"  Tier 1: {len(tier1)} chars synthesis")
        print(f"  Tier 2: {len(tier2)} full-text source(s)")
        print(f"  Tier 3: {len(tier3)} abstract(s)")

        print(f"\n[STAGE 4/5] Writing qualitative literature review "
              f"(writeup_model={args.model_writeup})")
        if perform_review_writeup is None:
            print("Error: ai_scientist/perform_review_writeup.py is missing or failed to import.", file=sys.stderr)
            sys.exit(1)
        perform_review_writeup(
            base_folder=folder,
            idea=clean_idea,
            tier1_synthesis=tier1,
            tier2_fulltext=tier2,
            tier3_abstracts=tier3,
            big_model=args.model_writeup,
            small_model=args.model_citation,
        )

    print(f"\n[STAGE 5/5] Post-processing")
    import glob
    pdfs = sorted(glob.glob(os.path.join(folder, "*.pdf")))
    if pdfs:
        print(f"  PDF produced: {pdfs[-1]}")
    else:
        print("  WARNING: no PDF found — check LaTeX logs in the experiment folder")

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
