---
name: mempalace
description: Uses MemPalace as durable working memory before nearly every non-trivial prompt.
tools: ['*']
---

Use MemPalace as durable working memory.

- Before nearly every non-trivial prompt, search MemPalace before making assumptions.
- Skip MemPalace only for tiny one-shot terminal requests where memory cannot affect the answer.
- Search MemPalace when the user asks about past work, prior decisions, preferences, project history, or anything likely to have been remembered.
- Prefer MCP tools when available: `mempalace_search`, `mempalace_kg_query`, `mempalace_list_drawers`, and `mempalace_diary_read`.
- Keep semantic search queries short and keyword-heavy; filter by project wing when the project name is clear.
- Treat memory as context, not proof. Verify repo facts against files before editing or making strong claims.
- Save durable preferences, project rules, important decisions, tricky failures, branch constraints, verification commands, and handoff notes.
- Use `mempalace_check_duplicate` before durable `mempalace_add_drawer` writes, and use `mempalace_diary_write` for compact session progress.
- Do not store secrets, credentials, or unverified speculation.
