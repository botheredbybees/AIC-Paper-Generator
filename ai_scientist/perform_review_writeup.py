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
    "framing. Do not fabricate citations — only cite papers explicitly provided in the "
    "context. Use \\citep{key} for parenthetical citations (Author, Year) and \\citet{key} "
    "for narrative citations where the author name appears in the sentence. The key is shown "
    "in [brackets] before each reference. Do not use any other LaTeX commands."
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

def _cite_key(paper: dict) -> str:
    """Generate the BibTeX cite key for a paper (mirrors bibtex_from_s2_paper logic)."""
    styles = paper.get("citationStyles") or {}
    if styles.get("bibtex"):
        m = re.match(r'@\w+\{([^,]+),', styles["bibtex"])
        if m:
            return m.group(1)
    authors = paper.get("authors") or []
    year = str(paper.get("year") or "0000")
    first_last = ""
    if authors:
        name_parts = (authors[0].get("name") or "").split()
        first_last = name_parts[-1] if name_parts else "unknown"
    return re.sub(r"[^a-z0-9]", "", f"{first_last.lower()}{year}")


def build_tier3_abstracts_text(papers: list[dict]) -> str:
    """Format Tier 3 (S2 abstracts) as a readable block for LLM context.
    Each entry is prefixed with [cite_key] so the LLM can use \\citep{key}.
    """
    if not papers:
        return ""
    lines = []
    for p in papers:
        key = _cite_key(p)
        authors = p.get("authors") or []
        first = (authors[0].get("name") or "Author") if authors else "Author"
        year = p.get("year") or "?"
        title = p.get("title") or "Unknown"
        abstract = (p.get("abstract") or "")[:300]
        lines.append(f"[{key}] {first} ({year}). {title}. {abstract}")
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

# Characters that break LaTeX when they appear in .bib field values.
# Applied AFTER bibtex_from_s2_paper so we catch both S2-supplied and
# generated entries.  Order matters: escape \ before & to avoid double-escaping.
_BIB_SANITIZE = [
    ("—", "---"),   # em dash
    ("–", "--"),    # en dash
    ("‐", "-"),     # unicode hyphen
    ("‑", "-"),     # non-breaking hyphen
    ("“", "``"),    # left double quote
    ("”", "''"),    # right double quote
    ("‘", "`"),     # left single quote
    ("’", "'"),     # right single quote
    (" ", " "),     # non-breaking space
    ("&", r"\&"),        # unescaped ampersand (fatal in LaTeX tables/titles)
]


def _sanitize_bib_entry(entry: str) -> str:
    for old, new in _BIB_SANITIZE:
        entry = entry.replace(old, new)
    return entry


def _make_bibtex(papers: list[dict]) -> str:
    """Generate a minimal references.bib from S2 paper dicts."""
    # Lazy import to avoid circular imports; requires repo root on sys.path
    from generate_ideas_from_mcp import bibtex_from_s2_paper  # reuse existing utility
    entries = []
    seen: set[str] = set()
    for p in papers:
        entry = _sanitize_bib_entry(bibtex_from_s2_paper(p))
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
            context=(
                f"MCP Synthesis (ground truth):\n{tier1_synthesis}\n\n"
                f"Open question:\n{idea.get('Short Hypothesis', '')}\n\n"
                f"Key references (cite with \\cite{{key}}):\n{tier3_text[:2000]}"
            ),
            instruction=(
                "Write an Introduction section (~300 words) that frames the open question, "
                "establishes the significance of arts-based health research, and previews the review structure. "
                "Ground the argument in the synthesis provided. "
                "Cite relevant papers using \\citep{key} where [key] is shown before each reference."
            ),
            model=big_model,
        ),
        "LIT_REVIEW_PLACEHOLDER": fill_placeholder(
            "LIT_REVIEW_PLACEHOLDER",
            context=(
                f"Thematic clusters:\n{themes_text}\n\n"
                f"Evidence (Tier 2 - full text):\n{tier2_text[:3000]}\n\n"
                f"Field map (Tier 3 - abstracts with cite keys):\n{tier3_text[:4000]}"
            ),
            instruction=(
                "Write a Literature Review and Synthesis section (~600 words) organised around "
                "the thematic clusters listed above. For each cluster, summarise the evidence and "
                "name any methodological gaps. Prioritise Tier 2 full-text evidence over abstracts. "
                "Cite papers using \\citep{key} where [key] appears in [brackets] before each reference."
            ),
            model=big_model,
        ),
        "THEORY_PLACEHOLDER": fill_placeholder(
            "THEORY_PLACEHOLDER",
            context=f"Hypothesis: {idea.get('Short Hypothesis', '')}\nKey findings: {', '.join(idea.get('Related Work', '').split('.')[:3])}",
            instruction=(
                "Write a Theoretical and Creative Framework section (~250 words) explaining "
                "how arts practice intersects with health theory for this research question. "
                "Do not include any citation commands."
            ),
            model=big_model,
        ),
        "ANALYSIS_PLACEHOLDER": fill_placeholder(
            "ANALYSIS_PLACEHOLDER",
            context=(
                f"Source material (full text):\n{tier2_text[:4000]}\n\n"
                f"Reference list (cite with \\cite{{key}}):\n{tier3_text[:2000]}"
            ),
            instruction=(
                "Write a Thematic Analysis section (~400 words) that qualitatively synthesises "
                "participant experiences, intervention methodologies, and practitioner perspectives "
                "found in the provided source material. "
                "Cite papers using \\citep{key} where [key] appears in [brackets] in the reference list. "
                "Only cite keys that appear in the reference list — do not invent keys."
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

    # --- Scrub citation keys not present in references.bib ---
    if bib_content:
        valid_keys = _valid_bib_keys(bib_content)
        cleaned, removed = _scrub_undefined_cites(template, valid_keys)
        if removed:
            print(f"[Review] Scrubbed {len(removed)} undefined citation key(s): {removed}")
            template_path.write_text(cleaned, encoding="utf-8")

    # --- Compile with pdflatex (two passes for natbib) ---
    print(f"[Review] Compiling PDF with pdflatex...")
    for _pass in range(2):
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "template.tex"],
            cwd=str(latex_dest),
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        print(f"[Review] WARNING: pdflatex exited {result.returncode}")
        if result.stdout:
            print("[Review] stdout:\n" + result.stdout)
        if result.stderr:
            print("[Review] stderr:\n" + result.stderr)
        log_path = latex_dest / "compile.log"
        log_path.write_text(
            f"=== stdout ===\n{result.stdout}\n=== stderr ===\n{result.stderr}",
            encoding="utf-8",
        )
        print(f"[Review] Full log saved to {log_path}")
    else:
        pdf = latex_dest / "template.pdf"
        print(f"[Review] PDF: {pdf}")


def _valid_bib_keys(bib_text: str) -> set[str]:
    """Extract citation keys from a BibTeX string."""
    return set(re.findall(r'@\w+\{([^,\s]+)', bib_text))


def _scrub_undefined_cites(latex: str, valid_keys: set[str]) -> tuple[str, list[str]]:
    r"""Remove \citep/\citet/\cite commands whose keys are all undefined.

    For citations with multiple keys (e.g. \citep{a,b,c}), strips only the
    undefined keys; removes the entire command if none remain.
    Returns (cleaned_latex, list_of_removed_keys).
    """
    removed: list[str] = []

    def _filter(m: re.Match) -> str:
        cmd = m.group(1)   # citep / citet / cite
        keys = [k.strip() for k in m.group(2).split(",")]
        good = [k for k in keys if k in valid_keys]
        bad = [k for k in keys if k not in valid_keys]
        removed.extend(bad)
        if not good:
            return ""
        return f"\\{cmd}{{{', '.join(good)}}}"

    cleaned = re.sub(r'\\(cite[pt]?)\{([^}]+)\}', _filter, latex)
    return cleaned, removed


_LATEX_ESCAPE_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Common Unicode typographic characters that LLMs produce but 8-bit TeX fonts can't render.
# Applied before special-char escaping so none of these introduce backslashes.
_UNICODE_TO_LATEX = [
    ("—", "---"),   # em dash
    ("–", "--"),    # en dash
    ("‘", "`"),     # left single quote
    ("’", "'"),     # right single quote
    ("“", "``"),    # left double quote
    ("”", "''"),    # right double quote
    ("…", "..."),   # ellipsis
    (" ", " "),     # non-breaking space
    ("•", "-"),     # bullet
]


_CITE_RE = re.compile(r'\\cite[pt]?\{[^}]+\}')


def _latex_safe(text: str) -> str:
    """Escape special LaTeX characters, preserving \\citep/\\citet/\\cite{key} commands."""
    # Stash \cite[pt]{...} commands so their braces aren't escaped
    stash: dict[str, str] = {}

    def _stash(m: re.Match) -> str:
        tok = f"\x00{len(stash)}\x00"
        stash[tok] = m.group()
        return tok

    text = _CITE_RE.sub(_stash, text)
    for uni, replacement in _UNICODE_TO_LATEX:
        text = text.replace(uni, replacement)
    text = re.sub(r'[\\&%$#_{}~^]', lambda m: _LATEX_ESCAPE_MAP[m.group()], text)
    for tok, cmd in stash.items():
        text = text.replace(tok, cmd)
    return text
