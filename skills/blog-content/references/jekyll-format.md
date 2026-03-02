# Jekyll Post Format Reference

## File Naming Convention

All posts reside in the `_posts/` directory and must follow the naming pattern:

```
YYYY-MM-DD-slug.md
```

- **YYYY-MM-DD** -- ISO-8601 date (e.g. `2026-03-10`)
- **slug** -- Lowercase, hyphen-separated title (e.g. `how-llms-learn-to-reason`)

Example: `_posts/2026-03-10-how-llms-learn-to-reason.md`

## Frontmatter Field Reference

| Field      | Type     | Required | Description                                       |
|------------|----------|----------|---------------------------------------------------|
| `layout`   | string   | yes      | Page layout template (see below)                  |
| `title`    | string   | yes      | Post title, double-quoted                         |
| `date`     | datetime | yes      | Publish date with time and timezone offset         |
| `author`   | string   | yes      | Author display name                               |
| `tags`     | list     | yes      | Categorisation tags                               |
| `excerpt`  | string   | yes      | One-line summary, double-quoted                   |

## Valid Layout Values (algowayss_web)

| Layout   | Use Case                       |
|----------|--------------------------------|
| `post`   | Standard blog article          |
| `page`   | Static page (About, Contact)   |

Most content uses `layout: post`.

## Tag Formatting Rules

Tags are written as a YAML inline list:

```yaml
tags: [ai, research, llm]
```

- Simple single-word tags need **no** quotes.
- Tags that contain spaces must be quoted: `tags: [ai, "machine learning"]`.
- Keep tags lowercase for consistency.

## Complete Example Post

```markdown
---
layout: post
title: "How LLMs Learn to Reason"
date: 2026-03-10 08:00:00 +0700
author: Meutia
tags: [ai, research, llm]
excerpt: "A look at emergent reasoning capabilities in large language models."
---

## Introduction

Large language models have demonstrated surprising reasoning abilities that
were not explicitly trained into them.

## Chain-of-Thought Prompting

By encouraging a model to "think step by step", researchers have found
significant accuracy improvements on math and logic benchmarks.

## Conclusion

Reasoning in LLMs remains an active and exciting area of research.

## References

- Wei et al., "Chain-of-Thought Prompting Elicits Reasoning in Large Language
  Models", NeurIPS 2022.
```

## ALGOWAY-Specific Conventions

1. **Author** -- Default author for generated posts is `Meutia`.
2. **Timezone** -- All dates use `+0700` (WIB / Western Indonesia Time).
3. **Excerpt** -- Every post must include an `excerpt` field; it is used for
   social-media previews and the blog index page.
4. **Time** -- The time component is always `08:00:00`.
5. **Tags** -- Keep tags concise and reusable across posts (e.g. `ai`,
   `research`, `trading`, `infra`).
