#!/usr/bin/env python3
"""Research API: search Semantic Scholar and arXiv for academic papers."""

import argparse
import json
import socket
import sys
import xml.etree.ElementTree as ET

import requests
from requests.adapters import HTTPAdapter

TIMEOUT = 15

# ---------------------------------------------------------------------------
# IPv4 adapter (Railway compatibility)
# ---------------------------------------------------------------------------

class IPv4HTTPAdapter(HTTPAdapter):
    """HTTP Adapter that forces IPv4 connections for Railway compatibility."""

    def init_poolmanager(self, *args, **kwargs):
        import urllib3.util.connection as urllib3_conn

        _orig_create_connection = urllib3_conn.create_connection

        def patched_create_connection(address, *args, **kwargs):
            host, port = address
            for res in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
                af, socktype, proto, canonname, sa = res
                try:
                    sock = socket.socket(af, socktype, proto)
                    sock.settimeout(kwargs.get("timeout", TIMEOUT))
                    sock.connect(sa)
                    return sock
                except socket.error:
                    try:
                        sock.close()
                    except Exception:
                        pass
                    continue
            raise socket.error(f"Could not connect to {host}:{port} via IPv4")

        urllib3_conn.create_connection = patched_create_connection
        super().init_poolmanager(*args, **kwargs)


def _create_session() -> requests.Session:
    """Create a requests.Session that forces IPv4."""
    session = requests.Session()
    adapter = IPv4HTTPAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ---------------------------------------------------------------------------
# Semantic Scholar
# ---------------------------------------------------------------------------

def search_semantic_scholar(query: str, limit: int = 5) -> list[dict]:
    """Search Semantic Scholar and return a list of paper dicts."""
    try:
        session = _create_session()
        resp = session.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "fields": "title,abstract,authors,year,citationCount,externalIds,url",
                "limit": limit,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    papers = []
    for item in data.get("data", []):
        # Build URL: prefer direct url, fall back to arXiv ID
        url = item.get("url") or ""
        if not url:
            ext_ids = item.get("externalIds") or {}
            arxiv_id = ext_ids.get("ArXiv")
            if arxiv_id:
                url = f"https://arxiv.org/abs/{arxiv_id}"

        authors = [a.get("name", "") for a in (item.get("authors") or [])]

        papers.append({
            "title": item.get("title", ""),
            "abstract": item.get("abstract") or "",
            "authors": authors,
            "year": item.get("year") or 0,
            "url": url,
            "citations": item.get("citationCount") or 0,
        })
    return papers


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

ARXIV_NS = "http://www.w3.org/2005/Atom"


def search_arxiv(query: str, limit: int = 5) -> list[dict]:
    """Search arXiv and return a list of paper dicts."""
    try:
        session = _create_session()
        resp = session.get(
            "https://export.arxiv.org/api/query",
            params={
                "search_query": f"all:{query}",
                "max_results": limit,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except Exception:
        return []

    papers = []
    for entry in root.findall(f"{{{ARXIV_NS}}}entry"):
        title_el = entry.find(f"{{{ARXIV_NS}}}title")
        summary_el = entry.find(f"{{{ARXIV_NS}}}summary")
        published_el = entry.find(f"{{{ARXIV_NS}}}published")
        id_el = entry.find(f"{{{ARXIV_NS}}}id")

        title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
        abstract = (summary_el.text or "").strip().replace("\n", " ") if summary_el is not None else ""
        url = (id_el.text or "").strip() if id_el is not None else ""

        year = 0
        if published_el is not None and published_el.text:
            try:
                year = int(published_el.text[:4])
            except (ValueError, IndexError):
                pass

        authors = []
        for author_el in entry.findall(f"{{{ARXIV_NS}}}author"):
            name_el = author_el.find(f"{{{ARXIV_NS}}}name")
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        papers.append({
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "year": year,
            "url": url,
            "citations": 0,
        })
    return papers


# ---------------------------------------------------------------------------
# Merged search
# ---------------------------------------------------------------------------

def search_papers(query: str, limit: int = 5) -> list[dict]:
    """Search both sources, merge and deduplicate by title similarity."""
    ss_results = search_semantic_scholar(query, limit)
    arxiv_results = search_arxiv(query, limit)

    merged = []
    seen_titles: set[str] = set()

    for paper in ss_results + arxiv_results:
        key = paper["title"].lower().strip()
        if key and key in seen_titles:
            continue
        seen_titles.add(key)
        merged.append(paper)

    return merged


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search academic papers")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", type=int, default=5, help="Max results per source")
    args = parser.parse_args()

    results = search_papers(args.query, args.limit)
    print(json.dumps(results, indent=2))
