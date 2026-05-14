---
name: mempalace
description: MemPalace — mine projects and conversations into a searchable memory palace. Use when asked about mempalace, memory palace, mining memories, searching memories, or palace setup.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# MemPalace

A searchable memory palace for AI — mine projects and conversations, then search them semantically.

## Prerequisites

Ensure `mempalace` is installed:

```bash
mempalace --version
```

## Usage

Available commands:

```bash
mempalace init <dir>              # Initialize palace from folder structure
mempalace mine <dir>              # Mine project files into the palace
mempalace mine <dir> --mode convos  # Mine conversation exports
mempalace search "<query>"        # Semantic search across all memories
mempalace search "<query>" --wing <wing>  # Filter by wing
mempalace status                  # Show wings, rooms, and drawer counts
mempalace wake-up                 # Show L0 + L1 context for the session
mempalace compress                # Compress drawers (~30x reduction)
```
