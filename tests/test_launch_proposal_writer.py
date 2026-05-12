import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from launch_proposal_writer import prepopulate_citations, setup_experiment_folder, write_idea_md, write_synthetic_summaries, PROPOSAL_NOTE


def _make_idea(**overrides) -> dict:
    base = {
        "Name": "test_idea",
        "Title": "A Test Title",
        "Short Hypothesis": "A hypothesis.",
        "Related Work": "Some prior work.",
        "Abstract": "An abstract.",
        "Experiments": ["Experiment 1"],
        "Risk Factors and Limitations": ["Risk 1"],
        "_mcp_topic": {
            "slug": "test-topic",
            "key_findings": ["Finding 1"],
            "body": "Body text.",
            "sources": ["source-1"],
        },
        "_s2_bibtex": ["@article{x, title={X}}"],
    }
    base.update(overrides)
    return base


def test_setup_experiment_folder_creates_directory(tmp_path):
    folder, clean_idea = setup_experiment_folder(str(tmp_path), _make_idea(), attempt_id=0)

    assert os.path.isdir(folder)
    assert "test_idea" in folder
    assert "proposal" in folder
    assert "_proposal_0" in folder


def test_setup_experiment_folder_strips_private_keys(tmp_path):
    _, clean_idea = setup_experiment_folder(str(tmp_path), _make_idea(), attempt_id=0)

    assert "_mcp_topic" not in clean_idea
    assert "_s2_bibtex" not in clean_idea
    assert clean_idea["Name"] == "test_idea"
    assert clean_idea["Title"] == "A Test Title"


def test_setup_experiment_folder_writes_topic_data_json(tmp_path):
    folder, _ = setup_experiment_folder(str(tmp_path), _make_idea(), attempt_id=0)

    topic_path = Path(folder) / "topic_data.json"
    assert topic_path.exists()
    data = json.loads(topic_path.read_text())
    assert data["slug"] == "test-topic"
    assert data["key_findings"] == ["Finding 1"]


def test_setup_experiment_folder_no_mcp_topic(tmp_path):
    """Ideas without _mcp_topic should produce an empty topic_data.json."""
    idea = _make_idea()
    del idea["_mcp_topic"]
    folder, clean_idea = setup_experiment_folder(str(tmp_path), idea, attempt_id=0)

    topic_path = Path(folder) / "topic_data.json"
    assert topic_path.exists()
    data = json.loads(topic_path.read_text())
    assert data == {}


def test_setup_experiment_folder_all_private_keys_stripped(tmp_path):
    """Any _-prefixed key is stripped, not just the two known ones."""
    idea = _make_idea(_future_key="should be stripped")
    _, clean_idea = setup_experiment_folder(str(tmp_path), idea, attempt_id=0)
    assert "_future_key" not in clean_idea


def test_setup_experiment_folder_attempt_id_in_name(tmp_path):
    folder1, _ = setup_experiment_folder(str(tmp_path), _make_idea(), attempt_id=0)
    folder2, _ = setup_experiment_folder(str(tmp_path), _make_idea(), attempt_id=1)

    assert folder1 != folder2
    assert "0" in Path(folder1).name
    assert "1" in Path(folder2).name


def test_prepopulate_citations_writes_bib_and_progress(tmp_path):
    entries = [
        "@article{smith2021, title={Test}, author={Smith}, year={2021}}",
        "@inproceedings{jones2022, title={Another}, year={2022}}",
    ]
    prepopulate_citations(str(tmp_path), entries, num_rounds=10)

    bib = (tmp_path / "cached_citations.bib").read_text()
    assert "@article{smith2021" in bib
    assert "@inproceedings{jones2022" in bib

    progress = json.loads((tmp_path / "citations_progress.json").read_text())
    assert progress["completed_rounds"] == 10


def test_prepopulate_citations_skips_when_no_entries(tmp_path):
    prepopulate_citations(str(tmp_path), [], num_rounds=10)

    assert not (tmp_path / "cached_citations.bib").exists()
    assert not (tmp_path / "citations_progress.json").exists()


def test_prepopulate_citations_deduplicates_entries(tmp_path):
    entries = [
        "@article{a, title={A}}",
        "@article{a, title={A}}",  # duplicate
        "@article{b, title={B}}",
    ]
    prepopulate_citations(str(tmp_path), entries, num_rounds=5)

    bib = (tmp_path / "cached_citations.bib").read_text()
    assert bib.count("@article{a") == 1
    assert bib.count("@article{b") == 1
    assert bib.index("@article{a") < bib.index("@article{b")


def test_prepopulate_citations_bib_separator(tmp_path):
    """Entries must be separated by exactly two newlines."""
    entries = ["@article{a, title={A}}", "@article{b, title={B}}"]
    prepopulate_citations(str(tmp_path), entries, num_rounds=5)

    bib = (tmp_path / "cached_citations.bib").read_text()
    parts = bib.split("\n\n")
    assert len(parts) == 2
    assert parts[0].startswith("@article{a")
    assert parts[1].startswith("@article{b")


def test_prepopulate_citations_single_entry_no_separator(tmp_path):
    """Single entry should not have a trailing separator."""
    prepopulate_citations(str(tmp_path), ["@article{x, title={X}}"], num_rounds=1)

    bib = (tmp_path / "cached_citations.bib").read_text()
    assert "\n\n" not in bib
    assert bib.startswith("@article{x")


def test_write_idea_md_contains_idea_fields(tmp_path):
    idea = {
        "Name": "elder_clowning",
        "Title": "Mechanisms of Therapeutic Clowning",
        "Short Hypothesis": "Clowning reduces isolation.",
        "Related Work": "Prior work on clowning.",
        "Abstract": "An abstract.",
        "Experiments": ["Conduct interviews", "Observational study"],
        "Risk Factors and Limitations": ["Small N"],
    }
    out = str(tmp_path / "idea.md")
    write_idea_md(idea, out)

    content = Path(out).read_text()
    assert "Mechanisms of Therapeutic Clowning" in content
    assert "Clowning reduces isolation." in content
    assert "Conduct interviews" in content


def test_write_idea_md_appends_proposal_note(tmp_path):
    idea = {
        "Name": "x", "Title": "T", "Short Hypothesis": "H",
        "Related Work": "R", "Abstract": "A",
        "Experiments": [], "Risk Factors and Limitations": [],
    }
    out = str(tmp_path / "idea.md")
    write_idea_md(idea, out)

    content = Path(out).read_text()
    assert "## Writing Instructions" in content
    assert "research proposal" in content.lower()
    assert "Do not fabricate" in content
    assert content.count("## Writing Instructions") == 1


def test_write_idea_md_proposal_note_comes_after_idea_content(tmp_path):
    idea = {
        "Name": "x", "Title": "My Title", "Short Hypothesis": "H",
        "Related Work": "R", "Abstract": "A",
        "Experiments": [], "Risk Factors and Limitations": [],
    }
    out = str(tmp_path / "idea.md")
    write_idea_md(idea, out)

    content = Path(out).read_text()
    title_pos = content.index("My Title")
    note_pos = content.index("## Writing Instructions")
    assert title_pos < note_pos


# ---------------------------------------------------------------------------
# write_synthetic_summaries (Option B)
# ---------------------------------------------------------------------------

def test_write_synthetic_summaries_creates_both_files(tmp_path):
    topic = {
        "body": "Arts improve wellbeing.",
        "key_findings": ["Finding 1", "Finding 2"],
        "open_questions": ["How?"],
    }
    write_synthetic_summaries(str(tmp_path), topic)

    research_path = tmp_path / "logs" / "0-run" / "research_summary.json"
    baseline_path = tmp_path / "logs" / "0-run" / "baseline_summary.json"
    assert research_path.exists()
    assert baseline_path.exists()


def test_write_synthetic_summaries_research_schema(tmp_path):
    topic = {
        "body": "Body text here.",
        "key_findings": ["Finding A"],
        "open_questions": ["Q1?"],
    }
    write_synthetic_summaries(str(tmp_path), topic)
    data = json.loads((tmp_path / "logs" / "0-run" / "research_summary.json").read_text())

    assert "best node" in data
    node = data["best node"]
    assert node["overall_plan"] == "Body text here."
    assert "Finding A" in node["analysis"]
    assert "Q1?" in node["analysis"]
    assert node["metric"] == {}


def test_write_synthetic_summaries_baseline_is_placeholder(tmp_path):
    write_synthetic_summaries(str(tmp_path), {"body": "x", "key_findings": []})
    data = json.loads((tmp_path / "logs" / "0-run" / "baseline_summary.json").read_text())

    node = data["best node"]
    assert "proposal" in node["overall_plan"].lower()
    assert node["metric"] == {}


def test_write_synthetic_summaries_empty_topic(tmp_path):
    """Should not raise even when topic fields are missing."""
    write_synthetic_summaries(str(tmp_path), {})
    research = json.loads((tmp_path / "logs" / "0-run" / "research_summary.json").read_text())
    assert "best node" in research


def test_write_synthetic_summaries_no_open_questions(tmp_path):
    topic = {"body": "B", "key_findings": ["F1", "F2"]}
    write_synthetic_summaries(str(tmp_path), topic)
    data = json.loads((tmp_path / "logs" / "0-run" / "research_summary.json").read_text())
    analysis = data["best node"]["analysis"]
    assert "F1" in analysis
    assert "F2" in analysis
    assert "Open research questions" not in analysis


# ---------------------------------------------------------------------------
# --writeup-type review routing
# ---------------------------------------------------------------------------

from unittest.mock import patch


def test_review_writeup_type_calls_perform_review_writeup(tmp_path):
    """launch_proposal_writer routes --writeup-type review to perform_review_writeup."""
    import json
    from launch_proposal_writer import main

    idea = {
        "Name": "arts_review", "Title": "Arts and Health Review",
        "Short Hypothesis": "H.", "Related Work": "R.", "Abstract": "A.",
        "Experiments": ["E1"], "Risk Factors and Limitations": ["L1"],
        "_mcp_topic": {"body": "Synthesis.", "key_findings": [], "open_questions": [], "sources": []},
        "_s2_papers": [],
        "_s2_bibtex": [],
        "_paywalled": [],
        "_oa_fulltext": {},
    }
    ideas_file = tmp_path / "ideas.json"
    ideas_file.write_text(json.dumps([idea]))

    with patch("launch_proposal_writer.perform_review_writeup") as mock_rw, \
         patch("launch_proposal_writer.write_idea_md"), \
         patch("launch_proposal_writer.write_synthetic_summaries"), \
         patch("sys.argv", [
             "prog",
             "--load_ideas", str(ideas_file),
             "--idea_idx", "0",
             "--writeup-type", "review",
             "--model_writeup", "ollama/qwen2.5:14b",
             "--model_citation", "ollama/qwen2.5:14b",
         ]):
        main()

    mock_rw.assert_called_once()
