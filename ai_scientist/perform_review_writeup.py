# ai_scientist/perform_review_writeup.py
"""
Fill the blank_review_latex/template.tex placeholders with qualitatively-toned
LLM output and compile via tectonic.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from ai_scientist.llm import create_client, get_response_from_llm

_REVIEW_LATEX_DIR = Path(__file__).parent / "blank_review_latex"

_QUALITATIVE_SYSTEM = (
    "You are a qualitative researcher in Creative Arts and Health writing an academic "
    "literature review. Use a descriptive, interpretive tone. Synthesise participant "
    "experiences, intervention methodologies, and thematic gaps. Avoid quantitative "
    "framing. Do not fabricate citations — only reference material explicitly provided. "
    "Write in LaTeX-safe plain text: do not use \\section{}, \\cite{}, or other LaTeX "
    "commands unless the instruction specifically requests it."
)


# ---------------------------------------------------------------------------
# Thematic pre-clustering
# ---------------------------------------------------------------------------

def cluster_themes(abstracts: list[dict], model: str) -> list[str]:
    """
    Run a small-model pass over all abstracts to identify 5-7 recurring themes.
    Returns a list of theme strings (numbered list items stripped of numbers).
    """
    if not abstracts:
        return ["Arts-based interventions", "Wellbeing outcomes", "Qualitative methodology"]

    abstract_block = "\n".join(
        f"- {p.get('title', 'Unknown')} ({p.get('year', '?')}): "
        f"{(p.get('abstract') or '')[:200]}"
        for p in abstracts[:50]  # cap at 50 to keep prompt manageable
    )

    prompt = (
        "Given these paper abstracts from a literature search in Creative Arts and Health, "
        "identify 5-7 recurring thematic clusters. Return a numbered list only - "
        "one cluster name and a single-sentence description per line.\n\n"
        f"{abstract_block}"
    )

    client, client_model = create_client(model)
    response, _ = get_response_from_llm(
        prompt=prompt,
        client=client,
        model=client_model,
        system_message=_QUALITATIVE_SYSTEM,
        temperature=0.3,
    )

    themes = []
    for line in response.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading number + punctuation: "1. Theme name" -> "Theme name"
        cleaned = re.sub(r"^\d+[.)]\s*", "", line)
        if cleaned:
            themes.append(cleaned)
    return themes or ["Arts-based interventions", "Wellbeing outcomes", "Qualitative methodology"]


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------

def build_tier3_abstracts_text(papers: list[dict]) -> str:
    """Format Tier 3 (S2 abstracts) as a readable block for LLM context."""
    if not papers:
        return ""
    lines = []
    for p in papers:
        authors = p.get("authors") or []
        first = (authors[0].get("name") or "Author") if authors else "Author"
        year = p.get("year") or "?"
        title = p.get("title") or "Unknown"
        abstract = (p.get("abstract") or "")[:300]
        lines.append(f"- {first} ({year}). {title}. {abstract}")
    return "\n".join(lines)


def build_tier2_fulltext_text(tier2: dict[str, dict]) -> str:
    """Format Tier 2 (manual PDF + OA fulltext) as a readable block for LLM context."""
    if not tier2:
        return ""
    blocks = []
    for citation_key, sections in tier2.items():
        for section_name, text in sections.items():
            blocks.append(f"### {citation_key} --- {section_name}\n{text}")
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Placeholder filling
# ---------------------------------------------------------------------------

def fill_placeholder(
    placeholder: str,
    context: str,
    instruction: str,
    model: str,
) -> str:
    """Call the LLM to generate content for a single template placeholder."""
    prompt = f"{instruction}\n\nContext:\n{context}\n\nRespond with the section text only - no headings, no preamble."
    client, client_model = create_client(model)
    response, _ = get_response_from_llm(
        prompt=prompt,
        client=client,
        model=client_model,
        system_message=_QUALITATIVE_SYSTEM,
        temperature=0.7,
    )
    return response.strip()


# ---------------------------------------------------------------------------
# BibTeX reference generation
# ---------------------------------------------------------------------------

def _make_bibtex(papers: list[dict]) -> str:
    """Generate a minimal references.bib from S2 paper dicts."""
    from generate_ideas_from_mcp import bibtex_from_s2_paper  # reuse existing utility
    entries = []
    seen: set[str] = set()
    for p in papers:
        entry = bibtex_from_s2_paper(p)
        if entry not in seen:
            seen.add(entry)
            entries.append(entry)
    return "\n\n".join(entries)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def perform_review_writeup(
    base_folder: str,
    idea: dict,
    tier1_synthesis: str,
    tier2_fulltext: dict,
    tier3_abstracts: list,
    big_model: str,
    small_model: str,
) -> None:
    """
    Fill blank_review_latex/template.tex placeholders using tiered context,
    then compile to PDF via tectonic.
    """
    print(f"[Review] Starting qualitative writeup in {base_folder}")

    # Copy LaTeX template to experiment folder
    latex_dest = Path(base_folder)
    for src_file in _REVIEW_LATEX_DIR.iterdir():
        shutil.copy2(src_file, latex_dest / src_file.name)

    template_path = latex_dest / "template.tex"
    template = template_path.read_text(encoding="utf-8")

    # --- Thematic pre-clustering (small model) ---
    print(f"[Review] Running thematic pre-clustering ({len(tier3_abstracts)} abstracts)...")
    themes = cluster_themes(tier3_abstracts, model=small_model)
    themes_text = "\n".join(f"- {t}" for t in themes)
    print(f"[Review] Themes identified: {themes}")

    tier2_text = build_tier2_fulltext_text(tier2_fulltext)
    tier3_text = build_tier3_abstracts_text(tier3_abstracts)

    # --- Direct substitutions (no LLM call) ---
    template = template.replace("TITLE_PLACEHOLDER", _latex_safe(idea.get("Title", "")))
    template = template.replace("AUTHOR_PLACEHOLDER", "Research Proposal")
    template = template.replace("ABSTRACT_PLACEHOLDER", _latex_safe(idea.get("Abstract", "")))

    # --- LLM-generated sections ---
    sections = {
        "KEYWORDS_PLACEHOLDER": fill_placeholder(
            "KEYWORDS_PLACEHOLDER",
            context=f"Title: {idea.get('Title', '')}\nDomain: arts and health\nThemes: {themes_text}",
            instruction="Generate 5-8 APA 7 keywords for this paper, comma-separated.",
            model=small_model,
        ),
        "INTRODUCTION_PLACEHOLDER": fill_placeholder(
            "INTRODUCTION_PLACEHOLDER",
            context=f"MCP Synthesis (ground truth):\n{tier1_synthesis}\n\nOpen question:\n{idea.get('Short Hypothesis', '')}",
            instruction=(
                "Write an Introduction section (~300 words) that frames the open question, "
                "establishes the significance of arts-based health research, and previews the review structure. "
                "Ground the argument in the synthesis provided."
            ),
            model=big_model,
        ),
        "LIT_REVIEW_PLACEHOLDER": fill_placeholder(
            "LIT_REVIEW_PLACEHOLDER",
            context=(
                f"Thematic clusters:\n{themes_text}\n\n"
                f"Evidence (Tier 2 - full text):\n{tier2_text[:3000]}\n\n"
                f"Field map (Tier 3 - abstracts):\n{tier3_text[:4000]}"
            ),
            instruction=(
                "Write a Literature Review and Synthesis section (~600 words) organised around "
                "the thematic clusters listed above. For each cluster, summarise the evidence and "
                "name any methodological gaps. Prioritise Tier 2 full-text evidence over abstracts."
            ),
            model=big_model,
        ),
        "THEORY_PLACEHOLDER": fill_placeholder(
            "THEORY_PLACEHOLDER",
            context=f"Hypothesis: {idea.get('Short Hypothesis', '')}\nKey findings: {', '.join(idea.get('Related Work', '').split('.')[:3])}",
            instruction=(
                "Write a Theoretical and Creative Framework section (~250 words) explaining "
                "how arts practice intersects with health theory for this research question."
            ),
            model=big_model,
        ),
        "ANALYSIS_PLACEHOLDER": fill_placeholder(
            "ANALYSIS_PLACEHOLDER",
            context=tier2_text[:5000] or tier3_text[:3000],
            instruction=(
                "Write a Thematic Analysis section (~400 words) that qualitatively synthesises "
                "participant experiences, intervention methodologies, and practitioner perspectives "
                "found in the provided source material."
            ),
            model=big_model,
        ),
        "PRACTICE_PLACEHOLDER": fill_placeholder(
            "PRACTICE_PLACEHOLDER",
            context="\n".join(str(e) for e in (idea.get("Experiments") or [])),
            instruction=(
                "Write a Practice-Based Implications section (~250 words) translating the proposed "
                "research methods into actionable guidance for community-based arts practitioners."
            ),
            model=big_model,
        ),
        "CONCLUSION_PLACEHOLDER": fill_placeholder(
            "CONCLUSION_PLACEHOLDER",
            context=(
                f"Limitations: {', '.join(str(r) for r in (idea.get('Risk Factors and Limitations') or []))}\n"
                f"Themes: {themes_text}"
            ),
            instruction=(
                "Write a Conclusion section (~200 words) summarising the key contributions, "
                "acknowledging limitations, and proposing future research directions."
            ),
            model=big_model,
        ),
    }

    for placeholder, content in sections.items():
        template = template.replace(placeholder, _latex_safe(content))

    template_path.write_text(template, encoding="utf-8")

    # --- Write references.bib ---
    bib_path = latex_dest / "references.bib"
    bib_content = _make_bibtex(tier3_abstracts)
    if bib_content:
        bib_path.write_text(bib_content, encoding="utf-8")

    # --- Compile with tectonic ---
    print(f"[Review] Compiling PDF with tectonic...")
    result = subprocess.run(
        ["tectonic", str(template_path)],
        cwd=str(latex_dest),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[Review] WARNING: tectonic exited {result.returncode}")
        print(result.stderr[:500])
    else:
        pdf = latex_dest / "template.pdf"
        print(f"[Review] PDF: {pdf}")


def _latex_safe(text: str) -> str:
    """Escape special LaTeX characters in plain text."""
    replacements = [
        ("\\", "\\textbackslash{}"),
        ("&", "\\&"),
        ("%", "\\%"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("_", "\\_"),
        ("{", "\\{"),
        ("}", "\\}"),
        ("~", "\\textasciitilde{}"),
        ("^", "\\textasciicircum{}"),
    ]
    for char, escaped in replacements:
        text = text.replace(char, escaped)
    return text
