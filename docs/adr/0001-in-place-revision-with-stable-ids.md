# In-place revision with stable IDs; supersession reserved for replacement

Consolidation — folding newly ingested evidence into an existing synthetic document — happens routinely, so it cannot mint a new ID each time: that would churn identifiers and break the external-reference stability that justifies frontmatter IDs (PRD §6.5). We decided synthetic documents are revised **in place** via a dedicated mutation write path (`kb revise`, resolving the PRD's OQ6): the ID never changes, a revision updates body/frontmatter and may append parents, and Git history plus `log.md` record the revision trail. **Supersession** is reserved for genuine replacement or rescoping of a document, not routine maintenance.

## Considered Options

- Supersession for every change (v0.3 PRD stance, AUT-7): explicit lineage, but IDs churn and citations rot.
- Hybrid by change size: rejected for needing an arbitrary, contestable boundary between "small" and "semantic" changes.

## Consequences

- A `kb revise` command must be specified and implemented; `kb create --supersedes` remains for replacement only.
- Revisions are performed in human-initiated sessions with the agent proposing and the human confirming judgment calls; both `timestamp` and (on human confirmation) `last_human_touch` advance.
