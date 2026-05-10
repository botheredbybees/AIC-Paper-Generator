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
    client, model = create_client("ollama/qwen3.5:9b-q8_0")
    assert "192.168.1.20" in str(client.base_url)
    assert model == "ollama/qwen3.5:9b-q8_0"


def test_create_client_ollama_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    client, model = create_client("ollama/qwen3.5:9b-q8_0")
    assert "localhost:11434" in str(client.base_url)


from generate_ideas_from_mcp import bibtex_from_s2_paper


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

    mock_search_result = MagicMock()
    mock_search_result.content = [MagicMock(text=json.dumps(search_payload))]

    mock_get_result = MagicMock()
    mock_get_result.content = [MagicMock(text=json.dumps(full_payload))]

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(
        side_effect=[mock_search_result, mock_get_result]
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
        mock_cc.return_value = (MagicMock(), "ollama/qwen3.5:9b-q8_0")
        mock_llm.return_value = (llm_response, [])

        idea = translate_to_idea(
            topic=topic,
            open_question="What mechanisms make it effective for older adults?",
            s2_papers=s2_papers,
            model="ollama/qwen3.5:9b-q8_0",
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
        mock_cc.return_value = (MagicMock(), "ollama/qwen3.5:9b-q8_0")
        mock_llm.return_value = ("This is not JSON at all.", [])

        result = translate_to_idea(topic, "A question?", [], "ollama/qwen3.5:9b-q8_0")

    assert result is None


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
