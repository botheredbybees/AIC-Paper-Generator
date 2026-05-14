# tests/test_pdf_reader.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _find_sections (pure function — no PDF I/O needed)
# ---------------------------------------------------------------------------

from ai_scientist.tools.pdf_reader import _find_sections, DEFAULT_SECTIONS


def test_find_sections_extracts_discussion():
    text = "Introduction\nsome intro text\n\nDiscussion\nThis is the discussion content.\nMore text here.\n\nConclusion\nDone."
    result = _find_sections(text, ["Discussion"], max_chars=4000, citation_key="")
    assert "Discussion" in result
    assert "discussion content" in result["Discussion"]


def test_find_sections_extracts_participant_voices():
    text = "Background\nsome text\n\nParticipant Voices\nParticipants described feeling joy.\n\nMethods\nWe did stuff."
    result = _find_sections(text, ["Participant Voices"], max_chars=4000, citation_key="")
    assert "Participant Voices" in result
    assert "feeling joy" in result["Participant Voices"]


def test_find_sections_extracts_narrative_synthesis():
    text = "Abstract\nText.\n\nNarrative Synthesis\nThemes emerged across studies.\n\nDiscussion\nMore."
    result = _find_sections(text, ["Narrative Synthesis"], max_chars=4000, citation_key="")
    assert "Narrative Synthesis" in result
    assert "Themes emerged" in result["Narrative Synthesis"]


def test_find_sections_case_insensitive():
    text = "DISCUSSION\nThis is case insensitive content.\n\nConclusion\nDone."
    result = _find_sections(text, ["Discussion"], max_chars=4000, citation_key="")
    assert "Discussion" in result
    assert "case insensitive" in result["Discussion"]


def test_find_sections_missing_section_omitted():
    text = "Introduction\nSome text.\n\nConclusion\nThe end."
    result = _find_sections(text, ["Discussion"], max_chars=4000, citation_key="")
    assert "Discussion" not in result


def test_find_sections_respects_max_chars():
    long_content = "word " * 2000   # ~10000 chars
    text = f"Discussion\n{long_content}\n\nConclusion\nDone."
    result = _find_sections(text, ["Discussion"], max_chars=200, citation_key="")
    assert "Discussion" in result
    assert len(result["Discussion"]) <= 200


def test_find_sections_citation_key_prefix():
    text = "Discussion\nSome findings here.\n\nConclusion\nDone."
    result = _find_sections(text, ["Discussion"], max_chars=4000, citation_key="Smith2022")
    assert result["Discussion"].startswith("[Smith2022]")


def test_find_sections_no_citation_key_no_prefix():
    text = "Results\nGood results.\n\nConclusion\nDone."
    result = _find_sections(text, ["Results"], max_chars=4000, citation_key="")
    assert not result["Results"].startswith("[")


def test_find_sections_stops_at_next_heading():
    text = "Discussion\nDiscussion text.\n\nResults\nResults text.\n\nConclusion\nDone."
    result = _find_sections(text, ["Discussion", "Results"], max_chars=4000, citation_key="")
    assert "Results" not in result["Discussion"]


def test_default_sections_includes_qualitative_headers():
    for expected in ["Participant Voices", "Narrative Synthesis", "Methodological Considerations", "Findings"]:
        assert expected in DEFAULT_SECTIONS


# ---------------------------------------------------------------------------
# extract_sections (integration — mocks fitz and requests)
# ---------------------------------------------------------------------------

from ai_scientist.tools.pdf_reader import extract_sections


def test_extract_sections_local_path(tmp_path):
    fake_pdf = tmp_path / "paper.pdf"
    fake_pdf.write_bytes(b"%PDF fake")

    with patch("ai_scientist.tools.pdf_reader._extract_text", return_value="Discussion\nGreat findings.\n\nConclusion\nDone."):
        result = extract_sections(str(fake_pdf), ["Discussion"], citation_key="Jones2021")

    assert "Discussion" in result
    assert result["Discussion"].startswith("[Jones2021]")


def test_extract_sections_url(tmp_path):
    fake_content = b"%PDF fake content"

    with patch("requests.get") as mock_get, \
         patch("ai_scientist.tools.pdf_reader._extract_text", return_value="Results\nPositive outcomes.\n\nConclusion\nDone."):
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = fake_content
        result = extract_sections("https://example.com/paper.pdf", ["Results"], citation_key="Brown2020")

    assert "Results" in result
    assert "[Brown2020]" in result["Results"]


def test_extract_sections_graceful_on_corrupt_pdf(tmp_path):
    bad_pdf = tmp_path / "bad.pdf"
    bad_pdf.write_bytes(b"not a pdf at all")

    with patch("ai_scientist.tools.pdf_reader._extract_text", side_effect=Exception("corrupt")):
        result = extract_sections(str(bad_pdf))

    assert result == {}


def test_extract_sections_graceful_on_network_error():
    with patch("requests.get", side_effect=Exception("network down")):
        result = extract_sections("https://example.com/paper.pdf")

    assert result == {}


def test_extract_sections_uses_default_sections_when_none_given(tmp_path):
    fake_pdf = tmp_path / "paper.pdf"
    fake_pdf.write_bytes(b"%PDF fake")

    with patch("ai_scientist.tools.pdf_reader._extract_text",
               return_value="Participant Voices\nPeople spoke.\n\nConclusion\nDone."):
        result = extract_sections(str(fake_pdf), citation_key="Ali2023")

    assert "Participant Voices" in result


# ---------------------------------------------------------------------------
# extract_doi_from_pdf
# ---------------------------------------------------------------------------

from ai_scientist.tools.pdf_reader import extract_doi_from_pdf


def _mock_fitz_doc(page_texts: list[str], metadata: dict | None = None):
    """Build a mock fitz document with the given per-page text content."""
    pages = []
    for text in page_texts:
        page = MagicMock()
        page.get_text.return_value = text
        pages.append(page)
    doc = MagicMock()
    doc.__len__ = MagicMock(return_value=len(pages))
    doc.__getitem__ = MagicMock(side_effect=lambda i: pages[i])
    doc.metadata = metadata or {}
    return doc


def test_extract_doi_from_pdf_finds_doi_in_page_text():
    doc = _mock_fitz_doc(["doi: 10.1002/14651858.CD011022.pub2\nSome abstract text."])
    with patch("fitz.open", return_value=doc):
        result = extract_doi_from_pdf("/fake/paper.pdf")
    assert result == "10.1002/14651858.CD011022.pub2"


def test_extract_doi_from_pdf_returns_none_when_no_doi():
    doc = _mock_fitz_doc(["No DOI here. Just plain text about something."])
    with patch("fitz.open", return_value=doc):
        result = extract_doi_from_pdf("/fake/paper.pdf")
    assert result is None


def test_extract_doi_from_pdf_strips_trailing_punctuation():
    doc = _mock_fitz_doc(["Cite this paper (doi:10.1234/test.paper). See methods."])
    with patch("fitz.open", return_value=doc):
        result = extract_doi_from_pdf("/fake/paper.pdf")
    assert result is not None
    assert not result.endswith(".")
    assert not result.endswith(")")


def test_extract_doi_from_pdf_case_insensitive():
    doc = _mock_fitz_doc(["DOI: 10.5678/uppercase-doi"])
    with patch("fitz.open", return_value=doc):
        result = extract_doi_from_pdf("/fake/paper.pdf")
    assert result == "10.5678/uppercase-doi"


def test_extract_doi_from_pdf_checks_multiple_pages():
    doc = _mock_fitz_doc([
        "Title page, no DOI.",
        "Abstract page.\nDOI: 10.9999/second-page",
        "Methods section.",
    ])
    with patch("fitz.open", return_value=doc):
        result = extract_doi_from_pdf("/fake/paper.pdf")
    assert result == "10.9999/second-page"
