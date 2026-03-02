"""Tests for research_api — calls live APIs."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from research_api import search_semantic_scholar, search_arxiv, search_papers

import pytest


def test_semantic_scholar_returns_results():
    results = search_semantic_scholar("large language model reasoning", limit=5)
    assert len(results) >= 1
    paper = results[0]
    assert "title" in paper
    assert "abstract" in paper
    assert "year" in paper
    assert "url" in paper


def test_arxiv_returns_results():
    results = search_arxiv("transformer architecture", limit=5)
    assert len(results) >= 1


def test_output_schema():
    results = search_papers("neural networks", 3)
    assert len(results) >= 1
    for paper in results:
        assert "title" in paper
        assert "abstract" in paper
        assert "year" in paper
        assert "url" in paper
        assert isinstance(paper["title"], str)
        assert isinstance(paper["year"], int)


def test_graceful_empty_on_bad_query():
    results = search_papers("xyzzy_no_results_expected_garbage_query_42", 1)
    assert isinstance(results, list)
