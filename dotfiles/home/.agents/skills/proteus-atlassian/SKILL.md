---
name: proteus-atlassian
description: Use when accessing Jira or Confluence through Teamwork Graph CLI inside Proteus, including searches, issue changes, comments, and page creation or editing.
---

Use the installed `twg`, `twg-jira`, and `twg-confluence` skills for command and product guidance.

Use basic product commands by default. Inspect `twg help <command>` before choosing a command; commands marked `[Enriched]` consume Rovo credits and require an explicit user request for enriched operations. A request to search or read content alone does not authorize enrichment. If basic commands cannot answer the request, explain the limitation and ask before using enrichment.

Use the enrolled default site and the project or space selected by the task. The CLI acts as the owner's personal Atlassian identity with their existing permissions; the supported workflows are not a technical permission boundary.

If authorization needs repair, ask the owner to run `./enroll twg` from the Proteus repository in an interactive macOS terminal. OAuth credentials remain inside the VM; never request tokens in chat.
