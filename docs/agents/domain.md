# Domain Docs

Proteus is a single-context repository.

## Before exploring

Read:

- `CONTEXT.md` at the repository root.
- Relevant ADRs under `docs/adr/`.

If either location does not exist, proceed silently. Domain documentation is created lazily when terms or decisions are resolved.

## Vocabulary

Use terms as defined in `CONTEXT.md` when naming domain concepts in issues, proposals, tests, and implementation notes. Avoid synonyms that the glossary rejects.

If a required concept is missing, reconsider whether it belongs to the domain model or note the gap for `/domain-modeling`.

## Architecture decisions

Surface conflicts with existing ADRs instead of silently overriding them.
