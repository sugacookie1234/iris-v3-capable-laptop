# IRIS design baseline

The owner adopted the supplied design package and generalist addendum as the
design direction on **2026-10-28** and asked development to continue. Roadmap
features remain proposals until their implementation and acceptance evidence exist.

- [Master product and technical design](IRIS_MASTER_DESIGN.md)
- [Generalist architecture addendum](IRIS_GENERALIST_ARCHITECTURE.md)
- [Capability and delivery tracker](IRIS_CAPABILITY_TRACKER.md)
- [Architectural decisions](IRIS_DECISIONS.md)
- [Collaboration protocol](IRIS_CODEX_PROTOCOL.md)
- [Actual validation evidence](VALIDATION.md)

Preserved source snapshots and a linked index were also imported into the owner's
configured Obsidian vault under `IRIS/Design/2026-10-28/` and `IRIS/Start Here.md`.
The separately supplied personal profile is a provenance-labelled vault note,
outside this repository. It is not a source-code fixture, global system prompt,
or a bulk import into the confirmed-memory database.

## Reconciliation with the working code

- Baseline: `9db02a7` contains voice endpoint detection, follow-up listening and
  tray standby. Actual microphone and OMEN acceptance are still outstanding.
- Desktop control slice: **CAP-21**, explicit Windows app/folder and system-volume
  actions, plus a fixed workspace routine that is a precursor to **CAP-15**.
- Current generalist slice: **CAP-30/31**, bounded local action receipts and a
  read-only tool/model/workflow inventory. See [usage and coverage](ACTION-HISTORY.md).
  Broader trace/cost coverage and runtime health verification remain pending.
- **CAP-32 first execution slice:** bounded read-only proposal validation, a local
  preview and a fixed search/read/draft recipe. Source revisions and excerpt spans
  are checked independently. General planning and durable background jobs remain
  pending. [Vault and planning usage](OBSIDIAN-READING.md).
- New action handlers must pass through the existing `ToolExecutor` and authority
  checks. App launches use YELLOW approval and distinguish launch requests from
  independently observed windows. One workspace approval covers exactly Chrome,
  Obsidian and the configured folder selected by the owner in this conversation.
- Filename search and a concise daily briefing use the existing bounded local
  data sources. They do not create a new knowledge store or external connector.
- The workspace routine is explicitly requested; double clap continues to start
  conversation. It does not imply arrival at home or start apps automatically.
- No general planner, autonomous code modification, new monitor, external account
  connection, personal-data training or automatic skill installation is enabled
  by adopting these documents.

The supplied protocol's sample audit-only handoff is retained as a reference; it
does not supersede the owner's current request to continue implementation. Source
and tests determine what works. Keep this index and the tracker aligned as slices
are delivered, and keep personal content out of commits even for a private repo.
