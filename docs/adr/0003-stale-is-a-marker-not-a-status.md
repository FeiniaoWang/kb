# Deferred propagation marks documents with a pending-upstream field, not a status

When a parent document is revised and the human defers propagating the change into a child, that child is knowingly outdated — a state the lifecycle must record, because "human consciously deferred" and "nobody has looked" are different audit conditions. We decided this is a **separate frontmatter marker** (`pending_upstream`, listing the revised parent ids not yet propagated), not a fifth status value: status stays `current`, so the document remains the best-available context for consumers (who are warned, not blocked), and the marker is cleared by the revision that performs the propagation.

## Considered Options

- New `stale` status: rejected — `--status current` filters would silently drop the only existing spec, and lifecycle semantics would overload.
- Lint-computed staleness with no marker: rejected — cannot distinguish deliberate deferral from neglect.
