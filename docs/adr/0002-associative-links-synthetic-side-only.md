# Associative links live on synthetic documents only; raw stays fully immutable

The knowledge network needs associative relationships (references, contradicts, constrains, …) beyond `derived_from` provenance — but raw documents are immutable, so a relationship discovered *after* ingest (e.g., new note-B contradicts old note-A) cannot be written onto either raw file. We decided associative links are frontmatter on **synthetic documents only**; raw immutability is fully preserved, and a raw↔raw relationship is expressed where it matters — in the downstream synthetic documents, where the later evidence overrides the earlier on conflict (CS1 latest-wins).

## Considered Options

- Body-immutable raw with appendable link frontmatter: rejected — weakens the immutability guarantee auditors rely on.
- Standalone edge-record documents: rejected — a new document class and file sprawl for marginal benefit.
