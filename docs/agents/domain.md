# Domain docs

How the engineering skills use this repo's domain documentation when they explore the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root, if it exists.
- **`docs/adr/`**. Read the ADRs that touch the area you are about to work in.

If any of these files is missing, **proceed silently** and carry on with the task. Leave their creation to the producer skill. The producer skill (`/grill-with-docs`) creates them when a term or decision gets resolved.

## File structure

Single-context repo:

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-*.md
│   └── 0002-*.md
├── core/
├── models/
└── ...
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Use the glossary term itself, never a synonym listed under its `_Avoid_` line.

If the concept you need isn't in the glossary yet, ask why. Either you are inventing language the project does not use, so reconsider, or there is a real gap, so note it for `/grill-with-docs`.

## Flag ADR conflicts

If your output contradicts an existing ADR, say so openly, for example:

> _Contradicts ADR-0007, but worth reopening because..._
