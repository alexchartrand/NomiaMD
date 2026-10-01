# Step 14 — Extension side panel (per-encounter flow)

**Phase:** 3 · **Depends on:** 13 · **Unblocks:** —
**Plan section:** §2 flow 2 (in-context, per encounter)

## Goal
Show the suggested codes next to the open chart, so a physician who prefers billing right after
each visit can do it without leaving the DMÉ.

## Tasks
- [ ] `chrome.sidePanel` page. After "Envoyer à NomiaMD", it shows the encounter's status, and
  polls `GET /encounters/{id}` until `prêt`.
- [ ] "Analyser maintenant" calls `POST /encounters/{id}/extract` (synchronous) when the physician
  doesn't want to wait for the queue.
- [ ] Codes list, read-only: code, description, fee, confidence, `needs_confirmation` sentences.
- [ ] "Réviser et approuver" opens `/app/inbox?encounter=<id>` in the web app. The review and
  claim stay in the app for now, which keeps one review UI.
- [ ] "à associer" state: link to the inbox to pick the patient.

## Done when
- Manual test with `make dev-fake`: send → panel shows `prêt` → codes visible → link opens the
  right inbox item.
- No PHI in `chrome.storage` (only the encounter id while the panel is open).

## Later (not this step)
Approve directly from the panel. Only consider it once the review UI is stable.
