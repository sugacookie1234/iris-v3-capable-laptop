# Reading the configured Obsidian vault

These desktop commands run locally in automatic reasoning mode, with no model
request or automatic-organizer pass:

- `Check Obsidian` verifies the configured vault and retrieval index are readable.
- `Search my notes for architecture` lists matching relative note paths.
- `Read note About me` resolves an unambiguous title. For ambiguous or limited
  searches, use the exact relative `.md` path shown in the search results.
- `Read next page` continues the last displayed note. A changed file requires
  restarting the read so pages cannot silently combine different revisions.

Long notes display in 8,000-character pages. Spoken output is a short status;
the full page appears on screen. These local replies are excluded from subsequent
model conversation history and automatic organization. Action receipts retain
tool metadata only. Starting a new chat clears the page cursor.

Ordinary questions and summarization can still retrieve relevant indexed note
excerpts for the configured model, as before. Markdown index URLs with encoded
spaces now work. Explicit slash-containing wikilinks are vault-relative; Markdown
links are index-relative. Large notes are excerpted rather than silently skipped.
Each excerpt preserves opening provenance and selects a relevant paragraph, with
bounded note, text and byte budgets. Titles rank above shared folder names.
Failed candidate reads are deduplicated and capped. Retrieval is index-based,
not an embedding index or a promise to read every note on each request.

All reads remain confined to the configured vault, reject hidden/credential paths
and links outside it, and screen the complete file before returning any page or
excerpt. The file limit remains 64 KiB. Note text is untrusted data: instructions
inside a note cannot grant permissions or execute tools.

## Imported design and profile

The October 28 source snapshots remain under `IRIS/Design/2026-10-28/` in the vault;
the personal profile remains at `IRIS/Personal/About me.md`, with its provenance
header. The October 29 local audit matched every supplied design document and
the profile body to the originals. No personal profile text is committed here.
The repository's `docs/` files track current development; imported originals are
historical snapshots. See [the working design index](IRIS_DESIGN_INDEX.md).

## First planning foundation (CAP-32)

`Plan a briefing from my notes on architecture` produces a local preview: search,
select/read, then draft. It does not execute those stages. Search is validated
against the registered tool; a read needs a selected path, and a typed draft
worker is not registered yet. These missing prerequisites are reported explicitly.

`iris/generalist/plan.py` validates immutable concrete proposals with up to eight
nodes, 120 aggregate tool-timeout seconds and 2,000 argument characters per node.
It rejects unknown tools, writes/external tools, missing host permissions,
untyped inputs, invalid dependencies and cycles. Validation grants no authority.
The existing executor must revalidate each future invocation. Dynamic output
references, execution, cancellation/restart and independently verified multi-step
outcomes are still pending; this is not the completed three-step design milestone.
