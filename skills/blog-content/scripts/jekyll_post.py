#!/usr/bin/env python3
"""Generate a Jekyll blog post with YAML frontmatter from stdin body text."""

import argparse
import datetime
import re
import sys
import unicodedata


def slugify(title):
    """Convert a title to a URL-friendly slug.

    Normalizes Unicode to ASCII, lowercases, replaces non-alphanumeric
    characters with hyphens, collapses runs of hyphens, and strips
    leading/trailing hyphens.
    """
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text


def make_filename(date, slug):
    """Return the Jekyll post filename: YYYY-MM-DD-slug.md."""
    return f"{date}-{slug}.md"


def format_frontmatter(title, date, tags, excerpt, author):
    """Return a YAML frontmatter block string.

    ``tags`` is a list of strings. Tags containing spaces are quoted;
    simple tags are rendered without quotes.
    """
    def _format_tag(t):
        if " " in t:
            return f'"{t}"'
        return t

    tag_items = ", ".join(_format_tag(t) for t in tags)
    return (
        "---\n"
        "layout: post\n"
        f'title: "{title}"\n'
        f"date: {date} 08:00:00 +0700\n"
        f"author: {author}\n"
        f"tags: [{tag_items}]\n"
        f'excerpt: "{excerpt}"\n'
        "---"
    )


def assemble_post(frontmatter, body):
    """Combine frontmatter and body into a complete post string."""
    return f"{frontmatter}\n\n{body.strip()}\n"


def main():
    parser = argparse.ArgumentParser(description="Generate a Jekyll blog post.")
    parser.add_argument("--title", required=True, help="Post title")
    parser.add_argument("--tags", default="", help="Comma-separated tags")
    parser.add_argument("--author", default="Meutia", help="Author name")
    parser.add_argument("--excerpt", default="", help="Brief one-line summary")
    parser.add_argument("--date", default=None, help="Post date (YYYY-MM-DD, default today)")
    args = parser.parse_args()

    date = args.date or datetime.date.today().isoformat()
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    body = sys.stdin.read()

    slug = slugify(args.title)
    filename = make_filename(date, slug)
    frontmatter = format_frontmatter(args.title, date, tags, args.excerpt, args.author)
    post = assemble_post(frontmatter, body)

    print(f"# Suggested filename: {filename}")
    print(post, end="")


if __name__ == "__main__":
    main()
