import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai_scientist.llm import create_client


def test_create_client_ollama_respects_base_url_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.20:11434")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    client, model = create_client("ollama/qwen2.5-coder:14b")
    assert "192.168.1.20" in str(client.base_url)
    assert model == "ollama/qwen2.5-coder:14b"


def test_create_client_ollama_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    client, model = create_client("ollama/qwen2.5-coder:14b")
    assert "localhost:11434" in str(client.base_url)


from generate_ideas_from_mcp import bibtex_from_s2_paper, write_library_html


def test_bibtex_uses_citation_styles_when_present():
    paper = {
        "citationStyles": {"bibtex": "@article{smith2021, title={Test}}"},
        "title": "Test", "authors": [], "year": 2021, "venue": "",
    }
    assert bibtex_from_s2_paper(paper) == "@article{smith2021, title={Test}}"


def test_bibtex_constructs_fallback_for_inproceedings():
    paper = {
        "citationStyles": {},
        "title": "Elder Clowning in Care Homes",
        "authors": [{"name": "Jane Smith"}, {"name": "Bob Jones"}],
        "year": 2023,
        "venue": "Arts in Psychotherapy",
    }
    result = bibtex_from_s2_paper(paper)
    assert "@inproceedings{smith2023" in result
    assert "Elder Clowning in Care Homes" in result
    assert "Jane Smith and Bob Jones" in result
    assert "2023" in result
    assert "Arts in Psychotherapy" in result


def test_bibtex_constructs_article_when_no_venue():
    paper = {
        "citationStyles": {},
        "title": "A Study",
        "authors": [{"name": "Alice Brown"}],
        "year": 2020,
        "venue": "",
    }
    result = bibtex_from_s2_paper(paper)
    assert result.startswith("@article{brown2020")
    assert "booktitle" not in result


def test_bibtex_handles_missing_authors():
    paper = {
        "citationStyles": {},
        "title": "Authorless Paper",
        "authors": [],
        "year": 2019,
        "venue": "",
    }
    result = bibtex_from_s2_paper(paper)
    assert "@article{" in result
    assert "Authorless Paper" in result
    assert "author = {Unknown}" in result


def test_bibtex_handles_none_fields():
    paper = {
        "citationStyles": {},
        "title": None,
        "authors": None,
        "year": None,
        "venue": None,
    }
    result = bibtex_from_s2_paper(paper)
    assert "@article{" in result
    assert "Unknown Title" in result
    assert "0000" in result


def test_bibtex_year_is_string_in_output():
    paper = {
        "citationStyles": {},
        "title": "A Study",
        "authors": [{"name": "Alice Brown"}],
        "year": 2022,
        "venue": "",
    }
    result = bibtex_from_s2_paper(paper)
    assert "year = {2022}" in result


def test_bibtex_key_generation_lowercase():
    paper = {
        "citationStyles": {},
        "title": "X",
        "authors": [{"name": "Van Der Berg"}],
        "year": 2020,
        "venue": "",
    }
    result = bibtex_from_s2_paper(paper)
    assert result.startswith("@article{berg2020")


def test_bibtex_fallback_includes_doi_fields_when_present():
    paper = {
        "citationStyles": {},
        "title": "Elder Clowning Study",
        "authors": [{"name": "Jane Smith"}],
        "year": 2021,
        "venue": "Arts in Psychotherapy",
        "externalIds": {"DOI": "10.1000/xyz123"},
    }
    result = bibtex_from_s2_paper(paper)
    assert "doi = {10.1000/xyz123}" in result
    assert r"note = {\url{https://doi.org/10.1000/xyz123}}" in result


def test_bibtex_fallback_omits_doi_fields_when_absent():
    paper = {
        "citationStyles": {},
        "title": "A Study",
        "authors": [{"name": "Alice Brown"}],
        "year": 2020,
        "venue": "",
    }
    result = bibtex_from_s2_paper(paper)
    assert "doi" not in result
    assert "note" not in result


def test_bibtex_citation_styles_gets_doi_injected():
    paper = {
        "citationStyles": {"bibtex": "@article{smith2021,\n  title={Test},\n}"},
        "externalIds": {"DOI": "10.9999/abc"},
        "title": "Test", "authors": [], "year": 2021, "venue": "",
    }
    result = bibtex_from_s2_paper(paper)
    assert "doi = {10.9999/abc}" in result
    assert r"note = {\url{https://doi.org/10.9999/abc}}" in result


def test_bibtex_citation_styles_doi_not_duplicated_if_already_present():
    """If S2's own bibtex already has a doi field, we don't add a second one."""
    paper = {
        "citationStyles": {"bibtex": "@article{smith2021,\n  title={Test},\n  doi={10.9999/abc},\n}"},
        "externalIds": {"DOI": "10.9999/abc"},
        "title": "Test", "authors": [], "year": 2021, "venue": "",
    }
    result = bibtex_from_s2_paper(paper)
    assert result.count("doi") == 1


# ---------------------------------------------------------------------------
# write_library_html tests
# ---------------------------------------------------------------------------

def _paper(title="Test Paper", year=2020, doi=None, venue="", authors=None, pdf_url=None):
    return {
        "title": title,
        "year": year,
        "authors": authors or [{"name": "Alice Smith"}],
        "venue": venue,
        "externalIds": {"DOI": doi} if doi else {},
        "openAccessPdf": {"url": pdf_url} if pdf_url else None,
    }


def test_write_library_html_creates_valid_html_file(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    assert out.exists()
    content = out.read_text()
    assert "<!DOCTYPE html>" in content
    assert "<html" in content


def test_write_library_html_paywalled_shows_full_title_and_year(tmp_path):
    p = _paper("Elder-Clowning in Long-Term Dementia Care", year=2016, doi="10.1000/x")
    out = tmp_path / "library.html"
    write_library_html([p], str(out))
    content = out.read_text()
    assert "Elder-Clowning in Long-Term Dementia Care" in content
    assert "(2016)" in content


def test_write_library_html_library_link_uses_ezproxy(tmp_path):
    p = _paper(doi="10.1000/test")
    out = tmp_path / "library.html"
    write_library_html([p], str(out))
    assert "ezproxy.utas.edu.au" in out.read_text()


def test_write_library_html_clipboard_button_has_suggested_filename(tmp_path):
    p = _paper("Elder Clowning Study", year=2023, authors=[{"name": "Jane Smith"}])
    out = tmp_path / "library.html"
    write_library_html([p], str(out))
    content = out.read_text()
    assert "btn-copy" in content
    assert "Jane_2023" in content  # first word of author name + year


def test_write_library_html_blocked_has_direct_url_button(tmp_path):
    p = _paper(pdf_url="https://example.com/paper.pdf")
    out = tmp_path / "library.html"
    write_library_html([], str(out), blocked_oa=[p])
    content = out.read_text()
    assert "btn-direct" in content
    assert "https://example.com/paper.pdf" in content


def test_write_library_html_paywalled_entry_has_no_direct_btn(tmp_path):
    p = _paper(doi="10.1/x")
    out = tmp_path / "library.html"
    write_library_html([p], str(out))
    assert "btn-direct" not in out.read_text()


def test_write_library_html_downloaded_papers_rendered_as_checkboxes(tmp_path):
    p = _paper("Downloaded Paper", year=2021)
    out = tmp_path / "library.html"
    pdfs = tmp_path / "pdfs"
    write_library_html([], str(out), downloaded=[(p, "smith2021.pdf")], pdfs_dir=pdfs)
    content = out.read_text()
    assert "dl-paper" in content
    assert "Downloaded Paper" in content
    assert 'type="checkbox"' in content


def test_write_library_html_downloaded_files_in_js_array(tmp_path):
    p = _paper(year=2021)
    out = tmp_path / "library.html"
    pdfs = tmp_path / "pdfs"
    write_library_html([], str(out), downloaded=[(p, "alice2021.pdf")], pdfs_dir=pdfs)
    content = out.read_text()
    assert "DL_FILES" in content
    assert "alice2021.pdf" in content


def test_write_library_html_rm_textarea_present_when_downloaded(tmp_path):
    p = _paper()
    out = tmp_path / "library.html"
    pdfs = tmp_path / "pdfs"
    write_library_html([], str(out), downloaded=[(p, "alice2020.pdf")], pdfs_dir=pdfs)
    assert "rm-cmd" in out.read_text()
    assert "updateRm" in out.read_text()


def test_write_library_html_no_downloaded_omits_dl_section(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    assert "dl-list" not in content
    assert "rm-cmd" not in content


def test_write_library_html_escapes_ampersand_in_title(tmp_path):
    p = _paper("Arts & Health Research", doi="10.1/x")
    out = tmp_path / "library.html"
    write_library_html([p], str(out))
    content = out.read_text()
    assert "&amp;" in content
    assert "Arts & Health" not in content


def test_write_library_html_pdfs_dir_path_used_in_rm_data(tmp_path):
    pdfs = tmp_path / "ai_scientist" / "ideas" / "pdfs"
    p = _paper()
    out = tmp_path / "library.html"
    write_library_html([], str(out), downloaded=[(p, "jones2020.pdf")], pdfs_dir=pdfs)
    assert str(pdfs) in out.read_text()


def _idea(idx=0, name="test_idea", title="Test Idea Title"):
    return {"Name": name, "Title": title}


def test_write_library_html_tab_bar_present(tmp_path):
    out = tmp_path / "library.html"
    ideas = [_idea(0, "clown_study", "Clown Study in Care Homes")]
    write_library_html([], str(out), ideas=ideas, ideas_path="ai_scientist/ideas/test.json")
    assert "tab-bar" in out.read_text()


def test_write_library_html_papers_tab_present(tmp_path):
    out = tmp_path / "library.html"
    ideas = [_idea()]
    write_library_html([], str(out), ideas=ideas, ideas_path="ai_scientist/ideas/test.json")
    content = out.read_text()
    assert "Papers" in content or "\U0001f4e5" in content


def test_write_library_html_launch_tab_present(tmp_path):
    out = tmp_path / "library.html"
    ideas = [_idea(0, "my_idea", "My Idea Title")]
    write_library_html([], str(out), ideas=ideas, ideas_path="ai_scientist/ideas/test.json")
    assert "Launch" in out.read_text()


def test_write_library_html_idea_radio_buttons_rendered(tmp_path):
    out = tmp_path / "library.html"
    ideas = [_idea(0, "idea_a", "Idea A"), _idea(1, "idea_b", "Idea B")]
    write_library_html([], str(out), ideas=ideas, ideas_path="ai_scientist/ideas/test.json")
    assert out.read_text().count('type="radio"') >= 2


def test_write_library_html_idea_titles_in_tab3(tmp_path):
    out = tmp_path / "library.html"
    ideas = [_idea(0, "idea_a", "Therapeutic Clowning Study"),
             _idea(1, "idea_b", "DMT Dementia Research")]
    write_library_html([], str(out), ideas=ideas, ideas_path="ai_scientist/ideas/test.json")
    content = out.read_text()
    assert "Therapeutic Clowning Study" in content
    assert "DMT Dementia Research" in content


def test_write_library_html_ideas_path_embedded(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/elder_clowning.json")
    assert "ai_scientist/ideas/elder_clowning.json" in out.read_text()


def test_write_library_html_ollama_url_embedded(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/test.json",
                       ollama_base_url="http://192.168.1.20:11434")
    assert "http://192.168.1.20:11434" in out.read_text()


def test_write_library_html_writeup_type_options(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/test.json")
    content = out.read_text()
    assert "icbinb" in content
    assert "review" in content
    assert "normal" in content


def test_write_library_html_launch_cmd_textarea(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/test.json")
    assert "launch-cmd" in out.read_text()


def test_write_library_html_no_ideas_omits_launch_tab(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    assert 'id="tab3-panel"' not in content
    assert "Launch writer" not in content


def test_write_library_html_generated_when_only_ideas(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/test.json")
    assert out.exists()


def test_write_library_html_localStorage_script_present(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/test.json")
    content = out.read_text()
    assert "localStorage" in content
    assert "activeTab" in content


def test_write_library_html_lastIdeasPath_written_on_load(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out), ideas=[_idea()],
                       ideas_path="ai_scientist/ideas/elder_clowning.json")
    content = out.read_text()
    assert "lastIdeasPath" in content


def test_write_library_html_supabase_constants_embedded(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out),
                       supabase_url="http://192.168.1.20:8000",
                       supabase_anon_key="eyJtestkey")
    content = out.read_text()
    assert "http://192.168.1.20:8000" in content
    assert "eyJtestkey" in content


def test_write_library_html_no_supabase_no_tag_fetch(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    assert "gen-tag-list" not in content
    assert "SUPABASE_URL" not in content


def test_write_library_html_tab1_active(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    # Tab 1 button must NOT have the disabled class or soon-badge
    assert 'class="tab-btn disabled"' not in content
    assert "soon-badge" not in content


def test_write_library_html_tab1_panel_present(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    assert 'id="tab1-panel"' in out.read_text()


def test_write_library_html_query_field_present(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    assert 'id="gen-query"' in out.read_text()


def test_write_library_html_domain_options(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    assert "intervention" in content
    assert "theory" in content
    assert "method" in content


def test_write_library_html_confidence_options(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    assert ">low<" in content
    assert ">medium<" in content
    assert ">high<" in content


def test_write_library_html_supabase_tag_fetch_js(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out),
                       supabase_url="http://192.168.1.20:8000",
                       supabase_anon_key="eyJtest")
    content = out.read_text()
    assert 'id="gen-tag-list"' in content
    assert "Content-Profile" in content
    assert "/rest/v1/tags" in content


def test_write_library_html_model_select_in_tab1(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    assert 'id="model-select-gen"' in out.read_text()


def test_write_library_html_output_path_field(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    assert 'id="gen-output"' in content
    assert "mcp_generated.json" in content


def test_write_library_html_tab1_localstorage_lastpath(tmp_path):
    out = tmp_path / "library.html"
    write_library_html([], str(out))
    content = out.read_text()
    # The output path field must update lastIdeasPath on input
    assert "lastIdeasPath" in content
    assert "gen-output" in content


from generate_ideas_from_mcp import fetch_mcp_topics, filter_topics_with_questions


def test_filter_topics_keeps_only_those_with_questions():
    topics = [
        {"slug": "a", "open_questions": ["Q1"]},
        {"slug": "b", "open_questions": []},
        {"slug": "c", "open_questions": None},
        {"slug": "d", "open_questions": ["Q2", "Q3"]},
    ]
    result = filter_topics_with_questions(topics)
    assert [t["slug"] for t in result] == ["a", "d"]


@pytest.mark.asyncio
async def test_fetch_mcp_topics_returns_full_topic_data():
    search_payload = [
        {
            "slug": "therapeutic-clowning",
            "title": "Therapeutic Clowning",
            "open_questions": ["What makes it effective?"],
            "domain": "intervention",
            "confidence": "high",
            "tags": [],
        }
    ]
    full_payload = {
        "slug": "therapeutic-clowning",
        "title": "Therapeutic Clowning",
        "domain": "intervention",
        "confidence": "high",
        "tags": [],
        "open_questions": ["What makes it effective?"],
        "key_findings": ["Reduces anxiety", "Improves mood"],
        "body": "Synthesis body text.",
        "sources": ["fxa303-week08-therapeutic-clowning"],
    }
    source_payload = {
        "slug": "fxa303-week08-therapeutic-clowning",
        "key_concepts": ["therapeutic clowning", "humor therapy", "older adults"],
    }

    mock_search_result = MagicMock()
    mock_search_result.content = [MagicMock(text=json.dumps(search_payload))]

    mock_get_result = MagicMock()
    mock_get_result.content = [MagicMock(text=json.dumps(full_payload))]

    mock_source_result = MagicMock()
    mock_source_result.content = [MagicMock(text=json.dumps(source_payload))]

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(
        side_effect=[mock_search_result, mock_get_result, mock_source_result]
    )

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)

    mock_transport_cm = AsyncMock()
    mock_transport_cm.__aenter__ = AsyncMock(
        return_value=(AsyncMock(), AsyncMock())
    )
    mock_transport_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("generate_ideas_from_mcp.sse_client", return_value=mock_transport_cm), \
         patch("generate_ideas_from_mcp.ClientSession", return_value=mock_session_cm):
        topics = await fetch_mcp_topics(
            query="therapeutic clowning",
            domain=None,
            confidence=None,
            limit=10,
            mcp_url="http://test:8765/sse",
        )

    assert len(topics) == 1
    assert topics[0]["slug"] == "therapeutic-clowning"
    assert topics[0]["key_findings"] == ["Reduces anxiety", "Improves mood"]
    assert "therapeutic clowning" in topics[0]["_key_concepts"]


@pytest.mark.asyncio
async def test_fetch_mcp_topics_handles_per_item_content():
    """FastMCP may return one TextContent per topic dict instead of a JSON array."""
    topic_a = {"slug": "a", "open_questions": ["Q1"], "title": "A"}
    topic_b = {"slug": "b", "open_questions": [], "title": "B"}
    full_a = {
        "slug": "a", "title": "A", "domain": "intervention", "confidence": "high",
        "tags": [], "open_questions": ["Q1"], "key_findings": ["F1"],
        "body": "Body.", "sources": ["src-1"],
    }

    # Two separate TextContent items — one per dict (per-item format)
    mock_search_result = MagicMock()
    mock_search_result.content = [
        MagicMock(text=json.dumps(topic_a)),
        MagicMock(text=json.dumps(topic_b)),
    ]

    mock_get_result = MagicMock()
    mock_get_result.content = [MagicMock(text=json.dumps(full_a))]

    source_a = {"slug": "src-1", "key_concepts": ["art therapy", "movement"]}
    mock_source_result = MagicMock()
    mock_source_result.content = [MagicMock(text=json.dumps(source_a))]

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(
        side_effect=[mock_search_result, mock_get_result, mock_source_result]
    )

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)

    mock_transport_cm = AsyncMock()
    mock_transport_cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
    mock_transport_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("generate_ideas_from_mcp.sse_client", return_value=mock_transport_cm), \
         patch("generate_ideas_from_mcp.ClientSession", return_value=mock_session_cm):
        topics = await fetch_mcp_topics("clowning", None, None, 10, "http://test:8765/sse")

    # Only topic_a passes the filter (has open_questions); topic_b is filtered out
    assert len(topics) == 1
    assert topics[0]["slug"] == "a"
    assert topics[0]["key_findings"] == ["F1"]
    # 1 search + 1 get_topic for a + 1 get_source for src-1 = 3 total
    assert mock_session.call_tool.call_count == 3


@pytest.mark.asyncio
async def test_fetch_mcp_topics_skips_invalid_json_items():
    """Content items with invalid JSON are silently skipped."""
    valid_topic = {"slug": "valid", "open_questions": ["Q"], "title": "Valid"}
    full_valid = {
        "slug": "valid", "title": "Valid", "domain": "theory", "confidence": "low",
        "tags": [], "open_questions": ["Q"], "key_findings": [], "body": "", "sources": [],
    }

    mock_search_result = MagicMock()
    mock_search_result.content = [
        MagicMock(text="this is not json"),
        MagicMock(text=json.dumps(valid_topic)),
    ]

    mock_get_result = MagicMock()
    mock_get_result.content = [MagicMock(text=json.dumps(full_valid))]

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(side_effect=[mock_search_result, mock_get_result])

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)

    mock_transport_cm = AsyncMock()
    mock_transport_cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
    mock_transport_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("generate_ideas_from_mcp.sse_client", return_value=mock_transport_cm), \
         patch("generate_ideas_from_mcp.ClientSession", return_value=mock_session_cm):
        topics = await fetch_mcp_topics("q", None, None, 10, "http://test:8765/sse")

    assert len(topics) == 1
    assert topics[0]["slug"] == "valid"


@pytest.mark.asyncio
async def test_fetch_mcp_topics_skips_topics_without_questions():
    search_payload = [
        {"slug": "no-q", "open_questions": [], "title": "No Questions"},
    ]

    mock_search_result = MagicMock()
    mock_search_result.content = [MagicMock(text=json.dumps(search_payload))]

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=mock_search_result)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)

    mock_transport_cm = AsyncMock()
    mock_transport_cm.__aenter__ = AsyncMock(
        return_value=(AsyncMock(), AsyncMock())
    )
    mock_transport_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("generate_ideas_from_mcp.sse_client", return_value=mock_transport_cm), \
         patch("generate_ideas_from_mcp.ClientSession", return_value=mock_session_cm):
        topics = await fetch_mcp_topics("clowning", None, None, 10, "http://test:8765/sse")

    assert topics == []
    # get_topic should NOT have been called for the filtered-out topic
    assert mock_session.call_tool.call_count == 1


from generate_ideas_from_mcp import attach_private_keys, translate_to_idea


def test_translate_to_idea_returns_valid_idea_dict():
    topic = {
        "title": "Therapeutic Clowning",
        "domain": "intervention",
        "confidence": "high",
        "key_findings": ["Reduces anxiety in medical settings"],
        "sources": ["fxa303-week08-therapeutic-clowning"],
    }
    s2_papers = [
        {
            "title": "Clowning in Pediatric Wards",
            "year": 2021,
            "venue": "Arts in Health",
            "citationCount": 45,
            "abstract": "Examines clowning effects on children.",
            "citationStyles": {},
            "authors": [{"name": "Alice Smith"}],
        }
    ]
    expected_json = {
        "Name": "elder_clowning_mechanisms",
        "Title": "Mechanisms of Therapeutic Clowning for Older Adults",
        "Short Hypothesis": "Therapeutic clowning reduces isolation.",
        "Related Work": "Pediatric clowning is studied (Smith 2021)...",
        "Abstract": "This proposal examines...",
        "Experiments": ["Semi-structured interviews with residents"],
        "Risk Factors and Limitations": ["Small sample size"],
    }
    llm_response = f"```json\n{json.dumps(expected_json)}\n```"

    with patch("generate_ideas_from_mcp.create_client") as mock_cc, \
         patch("generate_ideas_from_mcp.get_response_from_llm") as mock_llm:
        mock_cc.return_value = (MagicMock(), "ollama/qwen2.5-coder:14b")
        mock_llm.return_value = (llm_response, [])

        idea = translate_to_idea(
            topic=topic,
            open_question="What mechanisms make it effective for older adults?",
            s2_papers=s2_papers,
            model="ollama/qwen2.5-coder:14b",
        )

    assert idea is not None
    assert idea["Name"] == "elder_clowning_mechanisms"
    assert isinstance(idea["Experiments"], list)
    assert len(idea["Experiments"]) >= 1

    # Verify LLM was called with arts/health framing (not ML framing)
    call_kwargs = mock_llm.call_args
    prompt_text = call_kwargs[1]["prompt"] if call_kwargs[1] else call_kwargs[0][0]
    assert "arts and health" in prompt_text.lower()
    assert "Therapeutic Clowning" in prompt_text
    assert "Clowning in Pediatric Wards" in prompt_text


def test_translate_to_idea_returns_none_on_bad_llm_output():
    topic = {"title": "T", "domain": "d", "confidence": "low",
             "key_findings": [], "sources": []}

    with patch("generate_ideas_from_mcp.create_client") as mock_cc, \
         patch("generate_ideas_from_mcp.get_response_from_llm") as mock_llm:
        mock_cc.return_value = (MagicMock(), "ollama/qwen2.5-coder:14b")
        mock_llm.return_value = ("This is not JSON at all.", [])

        result = translate_to_idea(topic, "A question?", [], "ollama/qwen2.5-coder:14b")

    assert result is None


def test_translate_to_idea_returns_none_when_llm_returns_list():
    """LLM returning a JSON array instead of object should yield None."""
    topic = {"title": "T", "domain": "d", "confidence": "low",
             "key_findings": [], "sources": []}

    with patch("generate_ideas_from_mcp.create_client") as mock_cc, \
         patch("generate_ideas_from_mcp.get_response_from_llm") as mock_llm:
        mock_cc.return_value = (MagicMock(), "ollama/qwen2.5-coder:14b")
        mock_llm.return_value = ('```json\n[{"Name": "x"}]\n```', [])

        result = translate_to_idea(topic, "Q?", [], "ollama/qwen2.5-coder:14b")

    assert result is None


def test_translate_to_idea_handles_curly_braces_in_topic_data():
    """Topic fields with { } must not crash the format string."""
    topic = {
        "title": "PERMA {Wellbeing} Model",
        "domain": "theory",
        "confidence": "medium",
        "key_findings": ["PERMA = {Positive Emotion, ...}"],
        "sources": [],
    }
    expected_json = {
        "Name": "perma_model",
        "Title": "PERMA Wellbeing in Aged Care",
        "Short Hypothesis": "H.", "Related Work": "R.",
        "Abstract": "A.", "Experiments": ["E"], "Risk Factors and Limitations": ["R"],
    }

    with patch("generate_ideas_from_mcp.create_client") as mock_cc, \
         patch("generate_ideas_from_mcp.get_response_from_llm") as mock_llm:
        mock_cc.return_value = (MagicMock(), "ollama/qwen2.5-coder:14b")
        mock_llm.return_value = (f"```json\n{json.dumps(expected_json)}\n```", [])

        result = translate_to_idea(topic, "How does PERMA {apply}?", [], "ollama/qwen2.5-coder:14b")

    assert result is not None
    assert result["Name"] == "perma_model"


def test_attach_private_keys_does_not_mutate_original():
    idea = {"Name": "test", "Title": "T"}
    original_keys = set(idea.keys())

    topic = {"slug": "s"}
    attach_private_keys(idea, topic, [])

    assert set(idea.keys()) == original_keys


def test_attach_private_keys_with_empty_papers():
    idea = {"Name": "x"}
    result = attach_private_keys(idea, {"slug": "s"}, [])
    assert result["_s2_bibtex"] == []


def test_attach_private_keys_adds_mcp_topic_and_bibtex():
    idea = {
        "Name": "test", "Title": "T", "Short Hypothesis": "H",
        "Related Work": "R", "Abstract": "A",
        "Experiments": [], "Risk Factors and Limitations": [],
    }
    topic = {"slug": "test-topic", "key_findings": ["F1"], "body": "B", "sources": ["s1"]}
    s2_papers = [{"citationStyles": {"bibtex": "@article{x, title={X}}"}}]

    result = attach_private_keys(idea, topic, s2_papers)

    assert "_mcp_topic" in result
    assert result["_mcp_topic"]["slug"] == "test-topic"
    assert "_s2_bibtex" in result
    assert len(result["_s2_bibtex"]) == 1
    assert "@article{x" in result["_s2_bibtex"][0]
    # Original idea fields still present
    assert result["Name"] == "test"


# ---------------------------------------------------------------------------
# Recursive S2 expansion helpers
# ---------------------------------------------------------------------------

from generate_ideas_from_mcp import (
    expand_papers_recursively,
    classify_papers,
    write_library_list,
)


def _make_paper(paper_id: str, is_oa: bool = False, doi: str | None = None) -> dict:
    return {
        "paperId": paper_id,
        "title": f"Paper {paper_id}",
        "authors": [{"name": "Author A"}],
        "year": 2022,
        "abstract": "An abstract.",
        "citationCount": 10,
        "isOpenAccess": is_oa,
        "openAccessPdf": {"url": f"https://example.com/{paper_id}.pdf"} if is_oa else None,
        "externalIds": {"DOI": doi} if doi else {},
    }


def test_expand_papers_deduplicates_by_paper_id():
    seeds = [_make_paper("seed1"), _make_paper("seed2")]
    # Both seeds share the same citation
    shared = _make_paper("shared_citation")

    with patch("generate_ideas_from_mcp.fetch_paper_citations", return_value=[shared]), \
         patch("generate_ideas_from_mcp.fetch_paper_references", return_value=[]):
        result = expand_papers_recursively(seeds, max_papers=100)

    paper_ids = [p["paperId"] for p in result]
    assert paper_ids.count("shared_citation") == 1


def test_expand_papers_respects_max_cap():
    seeds = [_make_paper("seed1")]
    many_papers = [_make_paper(f"p{i}") for i in range(200)]

    with patch("generate_ideas_from_mcp.fetch_paper_citations", return_value=many_papers), \
         patch("generate_ideas_from_mcp.fetch_paper_references", return_value=[]):
        result = expand_papers_recursively(seeds, max_papers=50)

    assert len(result) <= 50


def test_expand_papers_includes_seeds():
    seeds = [_make_paper("seed1")]
    with patch("generate_ideas_from_mcp.fetch_paper_citations", return_value=[]), \
         patch("generate_ideas_from_mcp.fetch_paper_references", return_value=[]):
        result = expand_papers_recursively(seeds, max_papers=100)

    paper_ids = [p["paperId"] for p in result]
    assert "seed1" in paper_ids


def test_expand_papers_skips_citation_fetch_on_http_error():
    import requests
    seeds = [_make_paper("seed1")]
    err = requests.exceptions.HTTPError("429 rate limit")

    with patch("generate_ideas_from_mcp.fetch_paper_citations", side_effect=err), \
         patch("generate_ideas_from_mcp.fetch_paper_references", return_value=[]):
        result = expand_papers_recursively(seeds, max_papers=100)

    # Should still return the seed; error must not propagate
    assert any(p["paperId"] == "seed1" for p in result)


def test_expand_papers_skips_reference_fetch_on_http_error():
    import requests
    seeds = [_make_paper("seed1")]
    err = requests.exceptions.HTTPError("429 rate limit")

    with patch("generate_ideas_from_mcp.fetch_paper_citations", return_value=[]), \
         patch("generate_ideas_from_mcp.fetch_paper_references", side_effect=err):
        result = expand_papers_recursively(seeds, max_papers=100)

    assert any(p["paperId"] == "seed1" for p in result)


def test_classify_papers_splits_by_open_access():
    papers = [
        _make_paper("oa1", is_oa=True),
        _make_paper("oa2", is_oa=True),
        _make_paper("pw1", is_oa=False),
    ]
    oa, paywalled = classify_papers(papers)
    assert len(oa) == 2
    assert len(paywalled) == 1
    assert all(p["isOpenAccess"] for p in oa)
    assert not paywalled[0]["isOpenAccess"]


def test_write_library_list_creates_file(tmp_path):
    paywalled = [
        _make_paper("pw1", doi="10.1234/test"),
        _make_paper("pw2"),  # no DOI
    ]
    out = tmp_path / "to_fetch_from_library.md"
    write_library_list(paywalled, str(out))

    assert out.exists()
    content = out.read_text()
    assert "Paywalled Papers" in content


def test_write_library_list_doi_uses_ezproxy(tmp_path):
    paywalled = [_make_paper("pw1", doi="10.1234/test")]
    out = tmp_path / "to_fetch_from_library.md"
    write_library_list(paywalled, str(out))

    content = out.read_text()
    assert "ezproxy.utas.edu.au" in content
    assert "10.1234/test" in content


def test_write_library_list_no_doi_uses_primo(tmp_path):
    paywalled = [_make_paper("pw2")]  # no DOI
    out = tmp_path / "to_fetch_from_library.md"
    write_library_list(paywalled, str(out))

    content = out.read_text()
    assert "utas.primo.exlibrisgroup.com" in content


def test_write_library_list_suggested_filename(tmp_path):
    paywalled = [{"paperId": "x", "title": "Arts in Health Care",
                  "authors": [{"name": "Smith, J."}], "year": 2022,
                  "isOpenAccess": False, "externalIds": {"DOI": "10.1/x"},
                  "citationCount": 5, "abstract": "",
                  "openAccessPdf": None}]
    out = tmp_path / "to_fetch_from_library.md"
    write_library_list(paywalled, str(out))

    content = out.read_text()
    assert "Smith_2022" in content or "smith_2022" in content.lower()


# ---------------------------------------------------------------------------
# CLI flag wiring for --recursive and --fetch-fulltext
# ---------------------------------------------------------------------------

import argparse
from generate_ideas_from_mcp import parse_args, _main


def test_parse_args_recursive_defaults_false(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "--query", "test"])
    args = parse_args()
    assert args.recursive is False


def test_parse_args_recursive_flag_sets_true(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "--query", "test", "--recursive"])
    args = parse_args()
    assert args.recursive is True


def test_parse_args_max_papers_default(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "--query", "test"])
    args = parse_args()
    assert args.max_papers == 100


def test_parse_args_fetch_fulltext_defaults_false(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "--query", "test"])
    args = parse_args()
    assert args.fetch_fulltext is False


def test_ideas_json_has_s2_papers_key_after_recursive(tmp_path, monkeypatch):
    """When --recursive is used, ideas JSON gets _s2_papers, _paywalled, _oa_fulltext."""
    import json, asyncio
    from unittest.mock import AsyncMock, patch as upatch

    seed = _make_paper("seed1", is_oa=True, doi="10.1/x")
    topic = {
        "slug": "test-topic", "title": "Test Topic", "domain": "intervention",
        "confidence": "medium", "key_findings": ["F1"], "open_questions": ["Q1?"],
        "body": "Synthesis text.", "sources": [],
    }

    with upatch("generate_ideas_from_mcp.fetch_mcp_topics", new=AsyncMock(return_value=[topic])), \
         upatch("generate_ideas_from_mcp.search_for_papers", return_value=[seed]), \
         upatch("generate_ideas_from_mcp.expand_papers_recursively", return_value=[seed]), \
         upatch("generate_ideas_from_mcp.translate_to_idea", return_value={
             "Name": "test_idea", "Title": "T", "Short Hypothesis": "H",
             "Related Work": "R", "Abstract": "A",
             "Experiments": [], "Risk Factors and Limitations": [],
         }):
        output_file = tmp_path / "ideas.json"
        monkeypatch.setattr("sys.argv", [
            "prog", "--query", "test", "--recursive",
            "--output", str(output_file), "--mcp-url", "http://localhost:8765/sse",
        ])
        args = parse_args()
        asyncio.run(_main(args))

    ideas = json.loads(output_file.read_text())
    assert len(ideas) == 1
    assert "_s2_papers" in ideas[0]
    assert "_paywalled" in ideas[0]
    assert "_oa_fulltext" in ideas[0]


# ---------------------------------------------------------------------------
# fetch_source_key_concepts
# ---------------------------------------------------------------------------

from generate_ideas_from_mcp import fetch_source_key_concepts


@pytest.mark.asyncio
async def test_fetch_source_key_concepts_returns_concepts_from_source():
    source_record = {
        "slug": "fxa303-week08-clowning",
        "key_concepts": ["therapeutic clowning", "humor therapy", "older adults"],
    }
    mock_result = MagicMock()
    mock_result.content = [MagicMock(text=json.dumps(source_record))]
    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=mock_result)

    result = await fetch_source_key_concepts(["fxa303-week08-clowning"], mock_session)

    assert "therapeutic clowning" in result
    assert "humor therapy" in result
    assert "older adults" in result


@pytest.mark.asyncio
async def test_fetch_source_key_concepts_deduplicates_across_sources():
    source_a = {"slug": "a", "key_concepts": ["art therapy", "wellbeing"]}
    source_b = {"slug": "b", "key_concepts": ["wellbeing", "dementia"]}
    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(side_effect=[
        MagicMock(content=[MagicMock(text=json.dumps(source_a))]),
        MagicMock(content=[MagicMock(text=json.dumps(source_b))]),
    ])

    result = await fetch_source_key_concepts(["a", "b"], mock_session)

    assert result.count("wellbeing") == 1
    assert "art therapy" in result
    assert "dementia" in result


@pytest.mark.asyncio
async def test_fetch_source_key_concepts_returns_empty_for_no_slugs():
    mock_session = AsyncMock()
    result = await fetch_source_key_concepts([], mock_session)
    assert result == []
    mock_session.call_tool.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_source_key_concepts_skips_invalid_json():
    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(
        return_value=MagicMock(content=[MagicMock(text="not json")])
    )
    result = await fetch_source_key_concepts(["bad-slug"], mock_session)
    assert result == []


# ---------------------------------------------------------------------------
# parse_args — seed-doi / seed-pdf flags
# ---------------------------------------------------------------------------

from generate_ideas_from_mcp import parse_args


def test_parse_args_accepts_seed_doi():
    args = parse_args(["--seed-doi", "10.1002/14651858.CD011022.pub2",
                       "--query", "dementia movement therapy"])
    assert args.seed_doi == "10.1002/14651858.CD011022.pub2"


def test_parse_args_accepts_seed_pdf():
    args = parse_args(["--seed-pdf", "/home/user/paper.pdf",
                       "--query", "dementia movement therapy"])
    assert args.seed_pdf == "/home/user/paper.pdf"


def test_parse_args_query_optional_when_seed_doi_given():
    args = parse_args(["--seed-doi", "10.1002/test"])
    assert args.seed_doi == "10.1002/test"
    assert args.query is None


def test_parse_args_query_optional_when_seed_pdf_given():
    args = parse_args(["--seed-pdf", "/path/to/paper.pdf"])
    assert args.seed_pdf == "/path/to/paper.pdf"
    assert args.query is None


def test_parse_args_seed_doi_defaults_to_none():
    args = parse_args(["--query", "test query"])
    assert args.seed_doi is None


def test_parse_args_seed_pdf_defaults_to_none():
    args = parse_args(["--query", "test query"])
    assert args.seed_pdf is None


# ---------------------------------------------------------------------------
# extract_seed_pdf_sections
# ---------------------------------------------------------------------------

from generate_ideas_from_mcp import extract_seed_pdf_sections


def test_extract_seed_pdf_sections_returns_sections_keyed_by_paper_id():
    paper = {
        "paperId": "abc123",
        "authors": [{"name": "Karkou, V."}],
        "year": 2017,
    }
    mock_sections = {"Discussion": "[Karkou2017] DMT showed significant effects."}
    with patch("generate_ideas_from_mcp.extract_sections", return_value=mock_sections):
        result = extract_seed_pdf_sections("/path/to/paper.pdf", paper)
    assert result == {"abc123": mock_sections}


def test_extract_seed_pdf_sections_builds_citation_key_from_author_year():
    paper = {
        "paperId": "xyz999",
        "authors": [{"name": "Jane Smith"}, {"name": "Bob Jones"}],
        "year": 2022,
    }
    with patch("generate_ideas_from_mcp.extract_sections", return_value={"Results": "text"}) as mock_es:
        extract_seed_pdf_sections("/path/paper.pdf", paper)
    ck = mock_es.call_args[1].get("citation_key") or mock_es.call_args[0][1]
    assert ck == "Smith2022"


def test_extract_seed_pdf_sections_returns_empty_when_no_sections():
    paper = {"paperId": "abc123", "authors": [{"name": "Brown"}], "year": 2020}
    with patch("generate_ideas_from_mcp.extract_sections", return_value={}):
        result = extract_seed_pdf_sections("/path/paper.pdf", paper)
    assert result == {}


def test_extract_seed_pdf_sections_handles_missing_authors():
    paper = {"paperId": "abc123", "authors": [], "year": 2019}
    with patch("generate_ideas_from_mcp.extract_sections", return_value={"Discussion": "text"}):
        result = extract_seed_pdf_sections("/path/paper.pdf", paper)
    assert result == {"abc123": {"Discussion": "text"}}
