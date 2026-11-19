# Domain docs

How the engineering skills should read this repo's domain docs.

## Before exploring, read these

- `GLOSSARY.md` at the repo root.
- `docs/decisions.md`: one file of decisions in force, each under a heading keyed by its ADR number (`## 0031 ...`). Read the entries that touch the area you are about to work in.

If one is missing, proceed silently.

## Recording a new decision

Add an entry to `docs/decisions.md` with the next free number (`## NNNN Title`, 1-3 sentences: the decision and why). Do not create `docs/adr/`. When a decision is superseded, edit or remove its entry and say so in the "Dropped numbers" list at the end. History lives in git.

## Use the glossary's vocabulary

When your output names a domain concept (issue title, refactor proposal, hypothesis, test name), use the term as `GLOSSARY.md` defines it, never a synonym on an `_Avoid_` line. If the concept is missing, either you are inventing language (reconsider) or there is a real gap (note it for `/domain-modeling`).

## Flag decision conflicts

If your output contradicts a decision, say so: "Contradicts 0027, but worth reopening because..."
