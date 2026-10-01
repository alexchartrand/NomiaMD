# Step 13 — Browser extension and the first DMÉ adapter

**Phase:** 3 · **Depends on:** 12, and 04 (the pilot's DMÉ picks the adapter) · **Unblocks:** 14
**Plan section:** §1a (bridge), §3 Extension risk, §4 Browser extension

## Goal
Capture the signed note from the pilot clinic's DMÉ web page and push it to NomiaMD in one
click, with no copy/paste.

## Tasks
- [ ] Scaffold `extension/` at the repo root: Manifest V3, TypeScript, Vite build, `npm run build`
  producing a loadable unpacked folder.
- [ ] Options page: API base URL + device token (stored in `chrome.storage.local`), and a
  "Tester la connexion" button.
- [ ] `src/adapters/types.ts`: a `DmeAdapter` interface:
  - `matches(url)`
  - `readSignedNote(doc): SourceNoteDraft | null` (text, NAM, service date, times, external note
    id if visible)
  - `isSigned(doc)`: only push signed notes
- [ ] The first adapter (`omnimed.ts` or `medesync.ts`, depending on the pilot), with
  `host_permissions` limited to that DMÉ's domain.
- [ ] Content script: adds a small "Envoyer à NomiaMD" button when the adapter matches and the
  note is signed. The background worker posts to `/intake/notes` with
  `channel=extension`, `source_system=<dmé>`.
- [ ] Failure telemetry: when the adapter can't parse a page it reports `{adapter, version,
  selector_failed}` to a backend log endpoint. **No note text and no identifiers.**
- [ ] Synthetic HTML fixtures of the DMÉ's note page in `extension/fixtures/` (built by hand
  from the pilot's layout, with no real data). Write adapter unit tests against them (vitest + jsdom).
- [ ] Distribution: unlisted Chrome Web Store item or a managed install for the pilot. Document
  this in `extension/README.md`.

## Done when
- Adapter tests pass on the fixtures (signed note parsed; unsigned note → null; layout drift →
  telemetry event).
- Manual test against the pilot DMÉ's demo/test environment, if the vendor provides one:
  the note lands in the inbox as `prêt`.
- **Retirement rule** written in the README: remove the adapter once that vendor's official
  integration (step 20 or 21) is live.
