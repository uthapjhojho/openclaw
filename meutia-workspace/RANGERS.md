# RANGERS.md - Your Team

_Full roster and routing guide. Know who to call for what._

## Ranger Roster

| Ranger          | Model               | Specialty                           | Use When...                                                        |
| --------------- | ------------------- | ----------------------------------- | ------------------------------------------------------------------ |
| **cuk_lead**    | MiniMax-M2.5        | Planning, architecture, code review | Need architectural decisions, project planning, technical strategy |
| **cuk_coder**   | GLM-5               | Fast code generation                | Need quick code, refactoring, straightforward implementation       |
| **cuk_codex**   | gpt-oss-120b        | Deep research, reasoning            | Complex research, deep analysis, reasoning through hard problems   |
| **cuk_devops**  | DeepSeek V3.2       | Security, debugging, bulk tasks     | Security issues, debugging, infrastructure tasks, bulk operations  |
| **cuk_mini**    | Qwen3 32B           | Agentic, multi-step                 | Multi-step tasks, agentic workflows, complex chains of work        |
| **cuk_kimi**    | Kimi-K2.5           | Deep reasoning                      | Heavy reasoning tasks (5/day limit — use sparingly)                |
| **cuk_nemo**    | Nemotron-3-Nano-30B | Test automation                     | Need tests written, validation, QA automation                      |
| **cuk_infra**   | nanobot (ops skill) | General ops                         | Anything operational that isn't code or research (file ops, system tasks, service management) |
| **Zordon**      | Claude Code CLI     | Coordinator, discusses only         | Needs coordination discussion, NOT for task execution              |
| **Alpha-brain** | Sonnet/Opus         | Orchestrator                        | Overall task orchestration, dispatching Rangers                    |

---

## Routing Guide

### Quick Decision Tree

1. **Need code (quick/sync)?** → cuk_coder (fast) or cuk_mini (complex/multi-step)
2. **Need code (async, needs a PR)?** → jancuk
3. **Need research/analysis?** → cuk_codex (general) or cuk_kimi (deep, limited)
4. **Need planning/architecture?** → cuk_lead
5. **Need security/debugging?** → cuk_devops
6. **Need operational/system tasks?** → cuk_infra
7. **Need tests?** → cuk_nemo
8. **Need to discuss coordination?** → Zordon
9. **Need orchestration?** → Alpha-brain

### Common Scenarios

| Scenario                          | Route To             |
| --------------------------------- | -------------------- |
| Client wants a new feature        | cuk_lead → cuk_coder |
| Client wants a feature + PR       | cuk_lead → jancuk    |
| Client reports a bug              | cuk_devops           |
| Client needs research on X        | cuk_codex            |
| Complex multi-step implementation | cuk_mini             |
| Need to validate before delivery  | cuk_nemo             |
| System/ops task (non-code)        | cuk_infra            |
| Strategic planning session        | cuk_lead + Zordon    |
| Heavy reasoning (use sparingly)   | cuk_kimi             |

### jancuk vs cuk_coder

| | jancuk | cuk_coder |
|--|--------|-----------|
| **Mode** | Async, queue-based | Synchronous |
| **PR creation** | Yes (`--create-pr`) | No |
| **Best for** | Background tasks, PRs needed, long-running code jobs | Quick in-session code generation |
| **Status check** | `jancuk status <id>` | N/A (blocks until done) |

---

## Coordination Notes

- Always confirm task completion with the assigned Ranger before updating clients
- Track pending tasks in `memory/YYYY-MM-DD.md`
- Keep Captain informed of blockers, not just successes
- Respect cuk_kimi's 5/day limit — save for truly complex reasoning tasks

---

_Know your team. Route smart._
