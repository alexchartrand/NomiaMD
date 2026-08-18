# design-sync notes

- **No packaged library build.** `frontend/` is a Vite app, not a published component
  package — there's no `dist/`, no `main`/`module`/`exports` in `package.json`. The build
  uses `--entry ./src/components/index.ts` (accepted as a synthetic "dist" entry) plus an
  added `package.json` `types` field pointing at `types/components/index.d.ts` — a
  declaration-only `tsc` build (`.ds-sync/tsconfig.dts.json`, scoped to `src/components` +
  `src/Logo.tsx` for the relative import) run before the converter. Regenerate with:
  `./node_modules/.bin/tsc -p .ds-sync/tsconfig.dts.json` before every `package-build.mjs`
  run — `types/` is gitignored (regenerable) and not committed.
- **`cfg.provider: MemoryRouter`** (via `extraEntries: ["react-router-dom"]`) — `Sidebar`
  internally renders `Link`/`NavLink` from react-router-dom, which throw outside a Router
  context. Every preview is wrapped in `MemoryRouter`; harmless for components that don't
  need it.
- **Known render warns**: `[FONT_MISSING] "IBM Plex Mono"` — accepted substitute, not a
  gap. `--font-mono` (`styles.css`) is an intentional OS-fallback stack (`SF Mono` / `IBM
  Plex Mono` / `Menlo` / `Consolas` / `Liberation Mono` / generic `monospace`) — none of
  these are meant to ship as web fonts; the design is "use whatever's on the user's system."
  Only `--font-display` (Bricolage Grotesque, self-hosted) is a real shipped brand font,
  wired via `cfg.extraFonts`.

## Known render warns

- `[RENDER_ERRORS] Banner.html` — `firstErr` is literally the `WarningTone` story's own
  rendered text ("Le code 15818 nécessite une confirmation du statut vulnérable du
  patient."), not a real exception. Confirmed by reading `package-validate.mjs`'s per-cell
  check: it treats any mounted cell whose `textContent` starts with "⚠" as a caught
  render error (the harness's own convention for a preview that failed and wrote `⚠
  <message>` into the cell instead of throwing). Our `Banner` component's real `tone="warning"`
  usage in the app (`ExtractionPage.tsx`) legitimately renders text starting with "⚠", and
  the `WarningTone` preview faithfully reproduces that — so it collides with the harness's
  sentinel. Verified directly: loading `Banner.html` standalone (both via `file://` and a
  local HTTP server matching the validator's own approach) throws no `pageerror` at all;
  the render is correct (not blank/thin/collapsed, `rootEmpty: false`). Confirmed
  deterministic (reproduces every validate run) — this is a false positive from the tag
  collision, not a flake. Safe to treat as clean; re-syncs should expect this exact warn on
  `Banner` and not treat it as new.

## Re-sync risks

- `types/` is regenerated, not committed — a re-sync on a fresh clone must re-run the `tsc
  -p .ds-sync/tsconfig.dts.json` step before `package-build.mjs`, or component discovery
  silently falls back to zero components (`[ZERO_MATCH]`).
- The `package.json` `"types"` field was added specifically for this sync's metadata
  resolution (`findTypesRoot`/`exportedNames`); it's inert for the app itself (nothing
  imports `facturemd-frontend` as a library) but don't remove it without checking design-sync
  still resolves component exports correctly.
- `NavItem`/`SidebarFooter` are pinned via `componentSrcMap` to `Sidebar.tsx` — if `Sidebar`
  is ever split into separate files, drop those overrides so the normal fuzzy-find can
  re-match them.
