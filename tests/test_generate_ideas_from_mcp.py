import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

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
