import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from launch_proposal_writer import prepopulate_citations, setup_experiment_folder


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
