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


def test_perform_review_writeup_invokes_tectonic(tmp_path):
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
    cmd = mock_sub.call_args[0][0]
    assert "tectonic" in cmd[0] or "tectonic" in str(cmd)


# ---------------------------------------------------------------------------
# _latex_safe
# ---------------------------------------------------------------------------

from ai_scientist.perform_review_writeup import _latex_safe


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
