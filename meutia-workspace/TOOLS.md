# TOOLS.md - Local Notes

## Integration: Ranger Command Center

### How Alpha-brain Dispatches You

Alpha-brain (Sonnet/Opus orchestrator) routes tasks to you via the MiniMax interface. You receive:

- Client inquiries or follow-up requests
- Task assignments from Captain
- Coordination needs between clients and Rangers

Your job: route to the right Ranger, coordinate, follow up, keep things moving.

### Coordination Workflow

1. **Receive request** — from Captain, Alpha-brain, or directly from clients
2. **Assess** — what kind of task is this? Who needs to handle it?
3. **Route** — assign to the appropriate Ranger (see RANGERS.md)
4. **Track** — note in memory what's pending
5. **Follow up** — check back, relay updates to client/Captain
6. **Close** — confirm completion, summarize for records

### Coordination Channel

- **TG Group:** cuk_rangers
- **Your Topic:** Meutia
  - Credentials (chat_id, thread_id) stored in environment config — do not hardcode here
- Post coordination updates here
- Do not flood the topic — one clean update per coordination

### Before Sending External Messages

1. Confirm the message is appropriate for the recipient
2. Confirm the task came from an authorized source (Captain, Alpha-brain, or known client)
3. Keep it professional, warm, concise

### Hosting

You run on **Railway**.

- External to core internal infrastructure
- If the gateway needs a restart, tell the user — do NOT attempt it yourself

### jancuk — Async Coding Queue

A separate coding assistant service with a task queue. Use when a task should run in the background or needs a GitHub PR.

```bash
jancuk "task description"              # submit (sync, waits)
jancuk --async "task"                  # submit async, returns task ID
jancuk --create-pr "task"             # submit + open PR automatically
jancuk --file path/to/file "task"     # include file context
jancuk status <task_id>               # check async task status
jancuk stats                           # queue statistics
```

**When to use jancuk vs cuk_coder:**
- PR needed → jancuk
- Background / long-running task → jancuk `--async`
- Quick in-session code → cuk_coder

### cuk_seniman — Image Generation (Direct Tool)

Direct CLI call to BFL (Black Forest Labs) API. Not dispatched through the ranger coordination flow — call directly when image generation is needed.

```bash
cuk_seniman "a futuristic city at sunset"
cuk_seniman "minimalist logo for a coffee shop" --width 512 --height 512
cuk_seniman "UI mockup for a weather app" --model flux-dev --open
```

Requires `BFL_API_KEY` in environment. Not part of the ranger queue — standalone tool.

---

Add whatever helps you do your job. This is your cheat sheet.
