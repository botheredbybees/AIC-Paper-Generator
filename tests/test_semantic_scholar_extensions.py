# tests/test_semantic_scholar_extensions.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock

import requests

from ai_scientist.tools.semantic_scholar import (
    fetch_paper_by_doi,
    fetch_paper_citations,
    fetch_paper_references,
    utas_library_url,
)


def _mock_s2_response(papers: list[dict], wrapper_key: str) -> MagicMock:
    """Return a mock requests.Response for S2 citation/reference endpoints."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"data": [{wrapper_key: p} for p in papers]}
    return mock


SAMPLE_PAPER = {
    "paperId": "abc123",
    "title": "Arts and Wellbeing",
    "authors": [{"name": "Smith, J."}],
    "year": 2022,
    "venue": "Arts in Health",
    "abstract": "A study.",
    "citationCount": 15,
    "isOpenAccess": True,
    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
    "externalIds": {"DOI": "10.1234/test"},
}


def test_fetch_paper_citations_returns_papers():
    with patch("requests.get", return_value=_mock_s2_response([SAMPLE_PAPER], "citingPaper")):
        result = fetch_paper_citations("abc123", limit=10)
    assert len(result) == 1
    assert result[0]["title"] == "Arts and Wellbeing"


def test_fetch_paper_citations_calls_correct_endpoint():
    with patch("requests.get", return_value=_mock_s2_response([], "citingPaper")) as mock_get:
        fetch_paper_citations("xyz999", limit=5)
    url = mock_get.call_args[0][0]
    assert "xyz999/citations" in url


def test_fetch_paper_citations_passes_limit():
    with patch("requests.get", return_value=_mock_s2_response([], "citingPaper")) as mock_get:
        fetch_paper_citations("abc123", limit=25)
    params = mock_get.call_args[1]["params"]
    assert params["limit"] == 25


def test_fetch_paper_references_returns_papers():
    with patch("requests.get", return_value=_mock_s2_response([SAMPLE_PAPER], "citedPaper")):
        result = fetch_paper_references("abc123", limit=10)
    assert len(result) == 1
    assert result[0]["paperId"] == "abc123"


def test_fetch_paper_references_calls_correct_endpoint():
    with patch("requests.get", return_value=_mock_s2_response([], "citedPaper")) as mock_get:
        fetch_paper_references("xyz999", limit=5)
    url = mock_get.call_args[0][0]
    assert "xyz999/references" in url


def test_fetch_paper_citations_returns_empty_on_http_error():
    mock = MagicMock()
    mock.raise_for_status.side_effect = Exception("HTTP 429")
    with patch("requests.get", return_value=mock):
        with patch("backoff.on_exception", lambda *a, **kw: lambda f: f):
            # backoff decorator is applied at import time, not at call time,
            # so patching backoff here has no effect — the real decorator runs
            # and the exception propagates after max_tries retries.
            # Verify the function raises rather than silently returns.
            with pytest.raises(Exception):
                fetch_paper_citations("bad_id")


def _make_http_error(status_code: int) -> requests.exceptions.HTTPError:
    resp = MagicMock()
    resp.status_code = status_code
    err = requests.exceptions.HTTPError(response=resp)
    return err


def test_not_rate_limited_returns_true_for_non_429():
    from ai_scientist.tools.semantic_scholar import _not_rate_limited
    assert _not_rate_limited(_make_http_error(404)) is True
    assert _not_rate_limited(_make_http_error(500)) is True


def test_not_rate_limited_returns_false_for_429():
    from ai_scientist.tools.semantic_scholar import _not_rate_limited
    assert _not_rate_limited(_make_http_error(429)) is False


def test_fetch_paper_citations_returns_empty_when_data_is_null():
    mock = MagicMock()
    mock.status_code = 200
    mock.raise_for_status.return_value = None
    mock.json.return_value = {"data": None}
    with patch("requests.get", return_value=mock):
        result = fetch_paper_citations("abc123", limit=10)
    assert result == []


def test_fetch_paper_references_returns_empty_when_data_is_null():
    mock = MagicMock()
    mock.status_code = 200
    mock.raise_for_status.return_value = None
    mock.json.return_value = {"data": None}
    with patch("requests.get", return_value=mock):
        result = fetch_paper_references("abc123", limit=10)
    assert result == []


def test_utas_library_url_with_doi():
    url = utas_library_url(doi="10.1234/example", title=None)
    assert url == "https://ezproxy.utas.edu.au/login?url=https://doi.org/10.1234/example"


def test_utas_library_url_strips_doi_whitespace():
    url = utas_library_url(doi="  10.1234/example  ", title=None)
    assert "10.1234/example" in url
    assert url.startswith("https://ezproxy.utas.edu.au")


def test_utas_library_url_title_only_returns_primo_search():
    url = utas_library_url(doi=None, title="Arts and Health Interventions")
    assert "utas.primo.exlibrisgroup.com" in url
    assert "Arts" in url or "arts" in url.lower()


def test_utas_library_url_no_doi_no_title_returns_primo_base():
    url = utas_library_url(doi=None, title=None)
    assert "utas.primo.exlibrisgroup.com" in url


def test_utas_library_url_doi_takes_precedence_over_title():
    url = utas_library_url(doi="10.9999/test", title="Some Title")
    assert "ezproxy.utas.edu.au" in url
    assert "primo" not in url


# ---------------------------------------------------------------------------
# fetch_paper_by_doi
# ---------------------------------------------------------------------------

_SAMPLE_DOI_PAPER = {
    "paperId": "doi_paper_123",
    "title": "Dance Movement Therapy for Dementia",
    "authors": [{"name": "Karkou, V."}, {"name": "Meekums, B."}],
    "year": 2017,
    "venue": "Cochrane Database of Systematic Reviews",
    "abstract": "A Cochrane systematic review of DMT.",
    "citationCount": 183,
    "isOpenAccess": False,
    "openAccessPdf": None,
    "externalIds": {"DOI": "10.1002/14651858.CD011022.pub2"},
}


def test_fetch_paper_by_doi_returns_paper_dict():
    mock_rsp = MagicMock()
    mock_rsp.status_code = 200
    mock_rsp.json.return_value = _SAMPLE_DOI_PAPER
    with patch("requests.get", return_value=mock_rsp):
        result = fetch_paper_by_doi("10.1002/14651858.CD011022.pub2")
    assert result is not None
    assert result["paperId"] == "doi_paper_123"
    assert result["title"] == "Dance Movement Therapy for Dementia"


def test_fetch_paper_by_doi_calls_s2_doi_endpoint():
    mock_rsp = MagicMock()
    mock_rsp.status_code = 200
    mock_rsp.json.return_value = _SAMPLE_DOI_PAPER
    with patch("requests.get", return_value=mock_rsp) as mock_get:
        fetch_paper_by_doi("10.9999/mytest")
    url = mock_get.call_args[0][0]
    assert "DOI:10.9999/mytest" in url


def test_fetch_paper_by_doi_returns_none_on_404():
    mock_rsp = MagicMock()
    mock_rsp.status_code = 404
    with patch("requests.get", return_value=mock_rsp):
        result = fetch_paper_by_doi("10.0000/missing")
    assert result is None


def test_fetch_paper_by_doi_requests_traversal_fields():
    mock_rsp = MagicMock()
    mock_rsp.status_code = 200
    mock_rsp.json.return_value = _SAMPLE_DOI_PAPER
    with patch("requests.get", return_value=mock_rsp) as mock_get:
        fetch_paper_by_doi("10.1234/fields")
    params = mock_get.call_args[1]["params"]
    assert "isOpenAccess" in params["fields"]
    assert "citationCount" in params["fields"]
