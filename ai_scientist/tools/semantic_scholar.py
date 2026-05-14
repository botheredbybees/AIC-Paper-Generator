import os
import requests
import time
import warnings
from typing import Dict, List, Optional, Union

import backoff

from ai_scientist.tools.base_tool import BaseTool


def on_backoff(details: Dict) -> None:
    print(
        f"Backing off {details['wait']:0.1f} seconds after {details['tries']} tries "
        f"calling function {details['target'].__name__} at {time.strftime('%X')}"
    )


def _not_rate_limited(exc: requests.exceptions.HTTPError) -> bool:
    """Give up immediately on errors other than 429 (rate limit)."""
    return exc.response is not None and exc.response.status_code != 429


class SemanticScholarSearchTool(BaseTool):
    def __init__(
        self,
        name: str = "SearchSemanticScholar",
        description: str = (
            "Search for relevant literature using Semantic Scholar. "
            "Provide a search query to find relevant papers."
        ),
        max_results: int = 10,
    ):
        parameters = [
            {
                "name": "query",
                "type": "str",
                "description": "The search query to find relevant papers.",
            }
        ]
        super().__init__(name, description, parameters)
        self.max_results = max_results
        self.S2_API_KEY = os.getenv("S2_API_KEY")
        if not self.S2_API_KEY:
            warnings.warn(
                "No Semantic Scholar API key found. Requests will be subject to stricter rate limits. "
                "Set the S2_API_KEY environment variable for higher limits."
            )

    def use_tool(self, query: str) -> Optional[str]:
        papers = self.search_for_papers(query)
        if papers:
            return self.format_papers(papers)
        else:
            return "No papers found."

    @backoff.on_exception(
        backoff.expo,
        (requests.exceptions.HTTPError, requests.exceptions.ConnectionError),
        on_backoff=on_backoff,
        max_tries=4,
    )
    def search_for_papers(self, query: str) -> Optional[List[Dict]]:
        if not query:
            return None
        
        headers = {}
        if self.S2_API_KEY:
            headers["X-API-KEY"] = self.S2_API_KEY
        
        rsp = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            headers=headers,
            params={
                "query": query,
                "limit": self.max_results,
                "fields": "title,authors,venue,year,abstract,citationCount",
            },
        )
        print(f"Response Status Code: {rsp.status_code}")
        print(f"Response Content: {rsp.text[:500]}")
        rsp.raise_for_status()
        results = rsp.json()
        total = results.get("total", 0)
        if total == 0:
            return None

        papers = results.get("data", [])
        # Sort papers by citationCount in descending order
        papers.sort(key=lambda x: x.get("citationCount", 0), reverse=True)
        return papers

    def format_papers(self, papers: List[Dict]) -> str:
        paper_strings = []
        for i, paper in enumerate(papers):
            authors = ", ".join(
                [author.get("name", "Unknown") for author in paper.get("authors", [])]
            )
            paper_strings.append(
                f"""{i + 1}: {paper.get("title", "Unknown Title")}. {authors}. {paper.get("venue", "Unknown Venue")}, {paper.get("year", "Unknown Year")}.
Number of citations: {paper.get("citationCount", "N/A")}
Abstract: {paper.get("abstract", "No abstract available.")}"""
            )
        return "\n\n".join(paper_strings)


@backoff.on_exception(
    backoff.constant, requests.exceptions.HTTPError, on_backoff=on_backoff,
    max_tries=8, giveup=_not_rate_limited, interval=1.5,
)
def search_for_papers(query, result_limit=10) -> Union[None, List[Dict]]:
    S2_API_KEY = os.getenv("S2_API_KEY")
    headers = {}
    if not S2_API_KEY:
        warnings.warn(
            "No Semantic Scholar API key found. Requests will be subject to stricter rate limits."
        )
    else:
        headers["X-API-KEY"] = S2_API_KEY
    
    if not query:
        return None
    
    rsp = requests.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        headers=headers,
        params={
            "query": query,
            "limit": result_limit,
            "fields": "title,authors,venue,year,abstract,citationStyles,citationCount,externalIds",
        },
    )
    print(f"Response Status Code: {rsp.status_code}")
    print(
        f"Response Content: {rsp.text[:500]}"
    )  # Print the first 500 characters of the response content
    rsp.raise_for_status()
    results = rsp.json()
    total = results["total"]
    time.sleep(1.0)
    if not total:
        return None

    papers = results["data"]
    return papers


# ---------------------------------------------------------------------------
# DOI lookup
# ---------------------------------------------------------------------------


@backoff.on_exception(
    backoff.constant, requests.exceptions.HTTPError, on_backoff=on_backoff,
    max_tries=8, giveup=_not_rate_limited, interval=1.5,
)
def fetch_paper_by_doi(doi: str) -> dict | None:
    """Fetch a single S2 paper by DOI. Returns the paper dict or None if not found (404)."""
    S2_API_KEY = os.getenv("S2_API_KEY")
    headers = {"X-API-KEY": S2_API_KEY} if S2_API_KEY else {}
    rsp = requests.get(
        f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi.strip()}",
        headers=headers,
        params={"fields": _S2_TRAVERSAL_FIELDS},
    )
    if rsp.status_code == 404:
        return None
    rsp.raise_for_status()
    time.sleep(1.0)
    return rsp.json()


# ---------------------------------------------------------------------------
# Citation / reference traversal
# ---------------------------------------------------------------------------

_S2_TRAVERSAL_FIELDS = (
    "title,authors,year,venue,abstract,citationCount,"
    "isOpenAccess,openAccessPdf,externalIds"
)


@backoff.on_exception(
    backoff.constant, requests.exceptions.HTTPError, on_backoff=on_backoff,
    max_tries=8, giveup=_not_rate_limited, interval=1.5,
)
def fetch_paper_citations(paper_id: str, limit: int = 50) -> list[dict]:
    """Return papers that cite paper_id (forward citations)."""
    S2_API_KEY = os.getenv("S2_API_KEY")
    headers = {"X-API-KEY": S2_API_KEY} if S2_API_KEY else {}
    rsp = requests.get(
        f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations",
        headers=headers,
        params={"limit": limit, "fields": _S2_TRAVERSAL_FIELDS},
    )
    rsp.raise_for_status()
    data = rsp.json().get("data") or []
    time.sleep(1.0)
    return [item.get("citingPaper", item) for item in data if item.get("citingPaper")]


@backoff.on_exception(
    backoff.constant, requests.exceptions.HTTPError, on_backoff=on_backoff,
    max_tries=8, giveup=_not_rate_limited, interval=1.5,
)
def fetch_paper_references(paper_id: str, limit: int = 50) -> list[dict]:
    """Return papers cited by paper_id (backward references)."""
    S2_API_KEY = os.getenv("S2_API_KEY")
    headers = {"X-API-KEY": S2_API_KEY} if S2_API_KEY else {}
    rsp = requests.get(
        f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/references",
        headers=headers,
        params={"limit": limit, "fields": _S2_TRAVERSAL_FIELDS},
    )
    rsp.raise_for_status()
    data = rsp.json().get("data") or []
    time.sleep(1.0)
    return [item.get("citedPaper", item) for item in data if item.get("citedPaper")]


# ---------------------------------------------------------------------------
# UTAS library URL builder
# ---------------------------------------------------------------------------

_UTAS_EZPROXY = "https://ezproxy.utas.edu.au/login?url=https://doi.org/{doi}"
_UTAS_PRIMO_BASE = (
    "https://utas.primo.exlibrisgroup.com/discovery/search"
    "?vid=61UOT_INST:61UOT_INST&tab=LibraryCatalog"
    "&search_scope=MyInstitution&lang=en"
)


def utas_library_url(doi: str | None, title: str | None = None) -> str:
    """
    Return a clickable UTAS library URL.
    If doi: returns an EZproxy link directly to the DOI.
    If title only: returns a UTAS Primo search pre-populated with the title.
    """
    from urllib.parse import quote
    if doi:
        return _UTAS_EZPROXY.format(doi=doi.strip())
    if title:
        encoded = quote(title.strip(), safe="")
        return f"{_UTAS_PRIMO_BASE}&query=any,contains,{encoded}&bquery={encoded}"
    return _UTAS_PRIMO_BASE
