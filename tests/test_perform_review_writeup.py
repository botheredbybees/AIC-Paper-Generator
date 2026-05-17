# tests/test_perform_review_writeup.py
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock


from ai_scientist.perform_review_writeup import (
    cluster_themes,
    fill_placeholder,
    build_tier3_abstracts_text,
    build_tier2_fulltext_text,
    _scrub_undefined_cites,
    _valid_bib_keys,
)

# ---------------------------------------------------------------------------
# cluster_themes
# ---------------------------------------------------------------------------

def test_cluster_themes_returns_list_of_strings():
    abstracts = [{"title": f"Paper {i}", "abstract": "Arts improve wellbeing.", "year": 2020, "authors": []} for i in range(5)]
    mock_response = "1. Wellbeing outcomes\n2. Community arts\n3. Therapeutic methods\n4. Qualitative studies\n5. Participatory design"

    with patch("ai_scientist.perform_review_writeup.get_response_from_llm", return_value=(mock_response, 0)), \
         patch("ai_scientist.perform_review_writeup.create_client", return_value=(MagicMock(), "test-model")):
        themes = cluster_themes(abstracts, model="ollama/qwen2.5:14b")

    assert isinstance(themes, list)
    assert len(themes) >= 3
    assert all(isinstance(t, str) for t in themes)


def test_cluster_themes_handles_empty_abstracts():
    with patch("ai_scientist.perform_review_writeup.get_response_from_llm", return_value=("1. General theme", 0)), \
         patch("ai_scientist.perform_review_writeup.create_client", return_value=(MagicMock(), "test-model")):
        themes = cluster_themes([], model="ollama/qwen2.5:14b")
    assert isinstance(themes, list)


# ---------------------------------------------------------------------------
# fill_placeholder
# ---------------------------------------------------------------------------

def test_fill_placeholder_returns_string():
    with patch("ai_scientist.perform_review_writeup.get_response_from_llm", return_value=("Generated content.", 0)), \
         patch("ai_scientist.perform_review_writeup.create_client", return_value=(MagicMock(), "test-model")):
        result = fill_placeholder(
            placeholder="INTRODUCTION_PLACEHOLDER",
            context="Some synthesis text.",
            instruction="Write an introduction.",
            model="ollama/qwen2.5:14b",
        )
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# build_tier3_abstracts_text
# ---------------------------------------------------------------------------

def test_build_tier3_abstracts_text_formats_correctly():
    papers = [
        {"title": "Arts and Health", "abstract": "Great study.", "year": 2022,
         "authors": [{"name": "Smith, J."}]},
        {"title": "Music Therapy", "abstract": "Good outcomes.", "year": 2021,
         "authors": [{"name": "Jones, A."}]},
    ]
    text = build_tier3_abstracts_text(papers)
    assert "Arts and Health" in text
    assert "Smith" in text
    assert "2022" in text
    assert "Great study." in text


def test_build_tier3_abstracts_text_handles_empty():
    assert build_tier3_abstracts_text([]) == ""


# ---------------------------------------------------------------------------
# build_tier2_fulltext_text
# ---------------------------------------------------------------------------

def test_build_tier2_fulltext_text_includes_citation_keys():
    tier2 = {
        "Smith2022": {"Discussion": "[Smith2022] Participants felt joy."},
        "Jones2021": {"Findings": "[Jones2021] Themes of connection emerged."},
    }
    text = build_tier2_fulltext_text(tier2)
    assert "Smith2022" in text
    assert "Jones2021" in text
    assert "felt joy" in text


def test_build_tier2_fulltext_text_handles_empty():
    assert build_tier2_fulltext_text({}) == ""


# ---------------------------------------------------------------------------
# perform_review_writeup integration (mocked LLM + tectonic)
# ---------------------------------------------------------------------------

from ai_scientist.perform_review_writeup import perform_review_writeup


def _make_clean_idea() -> dict:
    return {
        "Name": "arts_wellbeing",
        "Title": "Arts-Based Interventions for Wellbeing in Older Adults",
        "Short Hypothesis": "Participatory arts improve social wellbeing.",
        "Related Work": "Prior work on clowning and music therapy.",
        "Abstract": "This paper proposes a systematic review.",
        "Experiments": ["Conduct interviews", "Focus groups"],
        "Risk Factors and Limitations": ["Small sample size"],
    }


def test_perform_review_writeup_replaces_all_placeholders(tmp_path):
    idea = _make_clean_idea()

    mock_llm_response = "Generated LaTeX content for this section."

    with patch("ai_scientist.perform_review_writeup.get_response_from_llm",
               return_value=(mock_llm_response, 0)), \
         patch("ai_scientist.perform_review_writeup.create_client",
               return_value=(MagicMock(), "test-model")), \
         patch("subprocess.run") as mock_sub:

        perform_review_writeup(
            base_folder=str(tmp_path),
            idea=idea,
            tier1_synthesis="Our synthesis shows arts improve wellbeing.",
            tier2_fulltext={"Smith2022": {"Discussion": "[Smith2022] Joy was reported."}},
            tier3_abstracts=[{"title": "A Study", "abstract": "Abstract text.", "year": 2022, "authors": []}],
            big_model="ollama/qwen2.5:14b",
            small_model="ollama/qwen2.5:14b",
        )

    tex_path = tmp_path / "template.tex"
    assert tex_path.exists()
    content = tex_path.read_text()
    for placeholder in [
        "TITLE_PLACEHOLDER", "AUTHOR_PLACEHOLDER", "KEYWORDS_PLACEHOLDER",
        "ABSTRACT_PLACEHOLDER", "INTRODUCTION_PLACEHOLDER", "LIT_REVIEW_PLACEHOLDER",
        "THEORY_PLACEHOLDER", "ANALYSIS_PLACEHOLDER", "PRACTICE_PLACEHOLDER",
        "CONCLUSION_PLACEHOLDER",
    ]:
        assert placeholder not in content, f"{placeholder} was not replaced"


def test_perform_review_writeup_invokes_pdflatex(tmp_path):
    idea = _make_clean_idea()

    with patch("ai_scientist.perform_review_writeup.get_response_from_llm",
               return_value=("content", 0)), \
         patch("ai_scientist.perform_review_writeup.create_client",
               return_value=(MagicMock(), "test-model")), \
         patch("subprocess.run") as mock_sub:

        perform_review_writeup(
            base_folder=str(tmp_path),
            idea=idea,
            tier1_synthesis="Synthesis.",
            tier2_fulltext={},
            tier3_abstracts=[],
            big_model="ollama/qwen2.5:14b",
            small_model="ollama/qwen2.5:14b",
        )

    assert mock_sub.called
    # All subprocess calls should be pdflatex (no tier3 abstracts → no bibtex run)
    for call in mock_sub.call_args_list:
        cmd = call[0][0]
        assert "pdflatex" in cmd[0], f"Expected pdflatex call, got: {cmd}"


# ---------------------------------------------------------------------------
# Template file integrity
# ---------------------------------------------------------------------------

_TEMPLATE_PATH = Path(__file__).parent.parent / "ai_scientist" / "blank_review_latex" / "template.tex"


def test_template_exists():
    assert _TEMPLATE_PATH.exists(), "blank_review_latex/template.tex must exist"


def test_template_does_not_require_biber():
    content = _TEMPLATE_PATH.read_text()
    assert "backend=biber" not in content, "template must not use backend=biber (not installed)"
    assert "style=apa" not in content or "biblatex" not in content, \
        "biblatex apa style requires biber — use natbib+apalike instead"


def test_template_uses_natbib_not_biblatex():
    content = _TEMPLATE_PATH.read_text()
    assert r"\usepackage{natbib}" in content or r"\usepackage[" in content and "natbib" in content
    assert r"\usepackage[" not in content or "biblatex" not in content


def test_template_does_not_have_nocite_star():
    content = _TEMPLATE_PATH.read_text()
    assert r"\nocite{*}" not in content, \
        "template must not use \\nocite{*} — only cited papers should appear in the reference list"


def test_template_compiles_with_pdflatex(tmp_path):
    """Smoke-compile the template with placeholder content and a real .bib entry,
    then verify the PDF exists."""
    import subprocess, shutil
    src = Path(__file__).parent.parent / "ai_scientist" / "blank_review_latex"
    for f in src.iterdir():
        shutil.copy2(f, tmp_path / f.name)

    tex = (tmp_path / "template.tex").read_text()
    for ph in [
        "TITLE_PLACEHOLDER", "AUTHOR_PLACEHOLDER", "KEYWORDS_PLACEHOLDER",
        "ABSTRACT_PLACEHOLDER", "INTRODUCTION_PLACEHOLDER", "LIT_REVIEW_PLACEHOLDER",
        "THEORY_PLACEHOLDER", "ANALYSIS_PLACEHOLDER", "PRACTICE_PLACEHOLDER",
        "CONCLUSION_PLACEHOLDER",
    ]:
        tex = tex.replace(ph, "Placeholder text for testing.")
    (tmp_path / "template.tex").write_text(tex)

    # Write a minimal .bib so the reference list is non-empty
    (tmp_path / "references.bib").write_text(
        "@article{test2024,\n  title={Test Article},\n  author={Test Author},\n  year={2024},\n}\n"
    )

    # pdflatex → bibtex → pdflatex → pdflatex
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "template.tex"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=120,
    )
    subprocess.run(
        ["bibtex", "template"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=60,
    )
    for _ in range(2):
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "template.tex"],
            cwd=str(tmp_path), capture_output=True, text=True, timeout=120,
        )
    assert result.returncode == 0, (
        f"pdflatex failed (exit {result.returncode}):\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert (tmp_path / "template.pdf").exists()


# ---------------------------------------------------------------------------
# _latex_safe
# ---------------------------------------------------------------------------

from ai_scientist.perform_review_writeup import (
    _latex_safe, _cite_key, build_tier3_abstracts_text, _sanitize_bib_entry,
)


def test_latex_safe_escapes_ampersand():
    assert _latex_safe("Smith & Jones") == r"Smith \& Jones"


def test_latex_safe_escapes_percent():
    assert _latex_safe("50% compliance") == r"50\% compliance"


def test_latex_safe_escapes_backslash_without_double_escaping():
    result = _latex_safe("C:\\Users")
    assert result == r"C:\textbackslash{}Users"
    # braces from \textbackslash{} must NOT be further escaped
    assert r"\{" not in result.replace(r"\textbackslash{}", "REPLACED")


def test_latex_safe_plain_text_unchanged():
    assert _latex_safe("Hello world") == "Hello world"


def test_latex_safe_braces():
    result = _latex_safe("{hello}")
    assert result == r"\{hello\}"


def test_latex_safe_em_dash():
    assert _latex_safe("long—term") == "long---term"


def test_latex_safe_en_dash():
    assert _latex_safe("2020–2024") == "2020--2024"


def test_latex_safe_curly_quotes():
    assert _latex_safe("“hello”") == "``hello''"
    assert _latex_safe("‘hello’") == "`hello'"


def test_latex_safe_ellipsis():
    assert _latex_safe("and so…") == "and so..."


def test_latex_safe_unicode_does_not_introduce_double_escaped_backslash():
    # em-dash replacement is "---" which contains no LaTeX special chars
    result = _latex_safe("a—b")
    assert "\\" not in result


def test_latex_safe_preserves_cite_command():
    result = _latex_safe(r"see \cite{smith2022} for details")
    assert r"\cite{smith2022}" in result


def test_latex_safe_cite_braces_not_escaped():
    result = _latex_safe(r"\cite{rehfeld2018}")
    assert r"\{" not in result
    assert r"\}" not in result
    assert r"\cite{rehfeld2018}" in result


def test_latex_safe_cite_preserved_alongside_special_chars():
    result = _latex_safe(r"50% of studies \cite{guh2009} show & effects")
    assert r"\cite{guh2009}" in result
    assert r"\%" in result
    assert r"\&" in result


# ---------------------------------------------------------------------------
# _cite_key
# ---------------------------------------------------------------------------


def test_cite_key_from_bibtex_field():
    paper = {"citationStyles": {"bibtex": "@article{rehfeld2018,\n  title={Test},\n}"}}
    assert _cite_key(paper) == "rehfeld2018"


def test_cite_key_generated_from_author_year():
    paper = {"authors": [{"name": "Karl Rehfeld"}], "year": 2018}
    assert _cite_key(paper) == "rehfeld2018"


def test_cite_key_strips_non_alphanumeric():
    paper = {"authors": [{"name": "O'Brien"}], "year": 2020}
    assert _cite_key(paper) == "obrien2020"


# ---------------------------------------------------------------------------
# build_tier3_abstracts_text cite-key prefixes
# ---------------------------------------------------------------------------


def test_tier3_text_includes_cite_key():
    papers = [{"authors": [{"name": "Karl Rehfeld"}], "year": 2018,
               "title": "DMT study", "abstract": "Abstract text."}]
    text = build_tier3_abstracts_text(papers)
    assert "[rehfeld2018]" in text
    assert "DMT study" in text


def test_tier3_text_empty_returns_empty_string():
    assert build_tier3_abstracts_text([]) == ""


# ---------------------------------------------------------------------------
# _sanitize_bib_entry
# ---------------------------------------------------------------------------


def test_sanitize_bib_escapes_ampersand():
    entry = '@article{key,\n  journal = {Arts & Health},\n}'
    result = _sanitize_bib_entry(entry)
    assert r"\&" in result
    assert " & " not in result


def test_sanitize_bib_replaces_curly_quotes():
    entry = '@article{key,\n  title = {“Mini-mental state”},\n}'
    result = _sanitize_bib_entry(entry)
    assert "“" not in result
    assert "”" not in result
    assert "``" in result
    assert "''" in result


def test_sanitize_bib_replaces_en_dash():
    entry = '@article{key,\n  title = {2020–2024},\n}'
    result = _sanitize_bib_entry(entry)
    assert "–" not in result
    assert "--" in result


def test_sanitize_bib_replaces_unicode_hyphen():
    entry = '@article{key,\n  title = {well‐being},\n}'
    result = _sanitize_bib_entry(entry)
    assert "‐" not in result
    assert "well-being" in result


def test_sanitize_bib_does_not_double_escape_already_escaped_amp():
    entry = r'@article{key,  title = {A \& B}}'
    result = _sanitize_bib_entry(entry)
    # \& should appear exactly once, not \\&
    assert result.count(r"\&") == 1


# ---------------------------------------------------------------------------
# _valid_bib_keys and _scrub_undefined_cites
# ---------------------------------------------------------------------------

_SAMPLE_BIB = """
@article{kontos2016, title={...}, author={...}}
@inproceedings{harris2019, title={...}, author={...}}
@article{wang2018, title={...}, author={...}}
"""

def test_valid_bib_keys_extracts_keys():
    keys = _valid_bib_keys(_SAMPLE_BIB)
    assert keys == {"kontos2016", "harris2019", "wang2018"}


def test_scrub_removes_entirely_undefined_key():
    latex = r"Text \citep{fakecite} more text."
    cleaned, removed = _scrub_undefined_cites(latex, {"kontos2016"})
    assert r"\citep" not in cleaned
    assert "fakecite" in removed


def test_scrub_removes_undefined_key_from_multi_key_cite():
    latex = r"Text \citep{kontos2016, fakecite} more text."
    cleaned, removed = _scrub_undefined_cites(latex, {"kontos2016"})
    assert r"\citep{kontos2016}" in cleaned
    assert "fakecite" in removed


def test_scrub_preserves_valid_keys():
    latex = r"Text \citep{kontos2016} and \citet{harris2019} more."
    cleaned, removed = _scrub_undefined_cites(latex, {"kontos2016", "harris2019"})
    assert cleaned == latex
    assert removed == []


def test_scrub_removes_literal_key_placeholder():
    latex = r"Use \citep{key} here."
    cleaned, removed = _scrub_undefined_cites(latex, {"kontos2016"})
    assert r"\citep" not in cleaned
    assert "key" in removed


def test_scrub_case_sensitive_mismatch():
    # LLM wrote Harris2019 but BibTeX has harris2019
    latex = r"\citep{Harris2019}"
    cleaned, removed = _scrub_undefined_cites(latex, {"harris2019"})
    assert r"\citep" not in cleaned
    assert "Harris2019" in removed
