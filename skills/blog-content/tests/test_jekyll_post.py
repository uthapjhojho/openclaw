#!/usr/bin/env python3
"""Unit tests for jekyll_post.py helper functions."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from jekyll_post import slugify, make_filename, format_frontmatter, assemble_post


class TestSlugify(unittest.TestCase):
    def test_slugify_basic(self):
        self.assertEqual(slugify("How LLMs Learn to Reason!"), "how-llms-learn-to-reason")

    def test_slugify_special_chars(self):
        result = slugify("AI & ML: Future?")
        self.assertEqual(result, "ai-ml-future")


class TestMakeFilename(unittest.TestCase):
    def test_make_filename(self):
        self.assertEqual(
            make_filename("2026-03-10", "how-llms-learn-to-reason"),
            "2026-03-10-how-llms-learn-to-reason.md",
        )


class TestFormatFrontmatter(unittest.TestCase):
    def test_format_frontmatter_fields(self):
        result = format_frontmatter(
            "Test Post", "2026-03-10", ["ai", "research"], "A test post.", "Meutia"
        )
        self.assertIn("layout: post", result)
        self.assertIn('title: "Test Post"', result)
        self.assertIn("author: Meutia", result)
        self.assertIn("tags: [ai, research]", result)
        self.assertIn('excerpt: "A test post."', result)
        self.assertIn("date: 2026-03-10", result)


class TestAssemblePost(unittest.TestCase):
    def test_assemble_post_structure(self):
        result = assemble_post("---\nlayout: post\n---", "Body text here")
        self.assertTrue(result.startswith("---"))
        self.assertIn("Body text here", result)
        self.assertIn("layout: post", result)


if __name__ == "__main__":
    unittest.main()
