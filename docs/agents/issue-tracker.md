# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`
- **Read an issue**: `gh issue view <number> --comments`, also fetching labels.
- **List issues**: use `gh issue list` with appropriate state and label filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply or remove labels**: use `gh issue edit`.
- **Close an issue**: `gh issue close <number> --comment "..."`

Infer the repository from `git remote -v`; `gh` does this automatically inside the clone.

## Pull requests as a triage surface

**PRs as a request surface: no.**

GitHub shares one number space across issues and pull requests. Resolve an ambiguous reference by trying `gh pr view` before `gh issue view`.

## Publishing

When a skill says to publish to the issue tracker, create a GitHub issue.

When a skill says to fetch a ticket, read the full issue body, comments, and labels.

## Wayfinding operations

Use one issue labelled `wayfinder:map` as the map and GitHub sub-issues as tickets. Represent blocking edges with GitHub issue dependencies where available, falling back to a `Blocked by` line. Claim work by assigning the ticket to the current user.
