# Associative links notify on upstream change but never obligate propagation

When a document connected only by an associative link (references, contradicts, constrains, …) has its target revised or superseded, the linking document appears in the impact report as "aware of change" — surfaced to the human — but carries no propagation obligation and no `pending_upstream` marking. Only `derived_from` provenance creates maintenance obligations; otherwise every link would become a subscription and propagation fatigue (PRD §11) would multiply with network density.

The link-type vocabulary is governance-declared in `kb-config.json` (like types and tags), with a shipped default set.
