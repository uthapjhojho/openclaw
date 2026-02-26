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
| **Zordon**      | Claude Code CLI     | Coordinator, discusses only         | Needs coordination discussion, NOT for task execution              |
| **Alpha-brain** | Sonnet/Opus         | Orchestrator                        | Overall task orchestration, dispatching Rangers                    |

---

## Routing Guide

### Quick Decision Tree

1. **Need code?** → cuk_coder (fast) or cuk_mini (complex/multi-step)
2. **Need research/analysis?** → cuk_codex (general) or cuk_kimi (deep, limited)
3. **Need planning/architecture?** → cuk_lead
4. **Need security/debugging?** → cuk_devops
5. **Need tests?** → cuk_nemo
6. **Need to discuss coordination?** → Zordon
7. **Need orchestration?** → Alpha-brain

### Common Scenarios

| Scenario                          | Route To             |
| --------------------------------- | -------------------- |
| Client wants a new feature        | cuk_lead → cuk_coder |
| Client reports a bug              | cuk_devops           |
| Client needs research on X        | cuk_codex            |
| Complex multi-step implementation | cuk_mini             |
| Need to validate before delivery  | cuk_nemo             |
| Strategic planning session        | cuk_lead + Zordon    |
| Heavy reasoning (use sparingly)   | cuk_kimi             |

---

## Coordination Notes

- Always confirm task completion with the assigned Ranger before updating clients
- Track pending tasks in `memory/YYYY-MM-DD.md`
- Keep Captain informed of blockers, not just successes
- Respect cuk_kimi's 5/day limit — save for truly complex reasoning tasks

---

_Know your team. Route smart._
