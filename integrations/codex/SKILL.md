---
name: mempalace
description: Use for nontrivial coding, repo investigation, configuration, debugging, planning, or multi-turn tasks to consult and update MemPalace memory through MCP.
---

# MemPalace Working Memory

Use MemPalace as durable working memory for Codex.

## When to Use

- At the start of nontrivial repo, coding, debugging, infrastructure, or planning work.
- When the current directory is a repo that may have prior decisions, preferences, or project notes.
- When the user asks about past work, prior decisions, preferences, or anything that sounds like it may already be remembered.
- Before broad edits, branch/history operations, or PR/review work where prior constraints matter.

Skip it for tiny one-shot terminal requests where memory cannot affect the answer.

## Search First

- Prefer MCP tools when available: `mempalace_search`, `mempalace_kg_query`, `mempalace_list_drawers`, and `mempalace_diary_read`.
- Keep semantic search queries short and keyword-heavy.
- Filter by wing when the project name is clear; otherwise search likely project names plus `user` preferences.
- Treat memory as context, not proof. Verify repo facts against files before editing or making strong claims.

## Save What Matters

- If the user states a durable preference, project rule, decision, or correction, save it.
- If you learn a repo-specific workflow, tricky failure, verification command, branch constraint, or important result that will matter later, save it.
- Use `mempalace_check_duplicate` before durable `mempalace_add_drawer` writes.
- Use `mempalace_diary_write` for compact session progress and handoff notes.
- Include exact dates, repo paths, source files, commands, and verification results when relevant.

Do not store secrets, credentials, or unverified speculation.
