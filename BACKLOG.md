# Backlog

## How to use this
- Add new items under the right section, newest on top.
- Check off `[x]` when done, but leave the line — don't delete (keeps history).
- Priority: 🔴 High · 🟡 Medium · 🟢 Low
- Ask Claude Code things like: "add a bug for X", "mark dark mode as done", "what's still open in features?"

---

## 🐛 Bugs

- [ ] 🔴 Vector search blocks the event loop — *added 8/19, from codebase audit*
  - `LanceDBVectorStore` has no `aquery` override, so both retrievers' `_aretrieve` (`ramq_codes/retriever.py`, `ramq_chatbot/retriever.py`) fall back to the sync `.retrieve()` call under the hood. Every concurrent physician's request stalls the single event loop for the duration of the native call.
  - Fix: wrap the sync query in `run_in_threadpool`, or move to an async-native vector store call path.

- [ ] 🟡 No server-side check that returned billing codes are from the candidate set — *added 8/19, from codebase audit*
  - `ramq_codes/task.py`'s `parse()` only validates JSON shape, never cross-checks returned `number`s against the candidates built in `build_prompt`. The "only choose from candidates" constraint lives in the prompt only. Mandatory physician review is the only backstop today — no defense in depth.

- [ ] 🟡 Login timing side-channel enables user enumeration — *added 8/19, from codebase audit*
  - `auth/service.py` `login()` returns immediately on `user is None`, but runs the deliberately slow Argon2 `verify()` when the email exists — response time distinguishes valid from invalid emails.
  - Fix: always run a dummy hash verify on the unknown-user path. Low real-world impact given the small, manually-provisioned user base.

- [ ] 🟡 Argon2 verify blocks the event loop on every login — *added 8/19, from codebase audit*
  - `AuthService.login` (async) calls the sync, CPU-slow `PasswordHasher.verify` directly (`auth/security.py`), no `run_in_threadpool`. Stalls the whole process for tens–hundreds of ms, including other physicians' in-flight `/extract`/`/query` requests.

- [ ] 🟡 Chat history grows unbounded, no truncation — *added 8/19, from codebase audit*
  - `ChatbotPage.tsx` resends the full message array every turn (stateless server by design), but nothing truncates or summarizes it. Cost and latency grow linearly with conversation length, no ceiling before hitting context limits.

- [ ] 🟡 Chatbot's BM25 index builds synchronously on first request — *added 8/19, from codebase audit*
  - `get_ramq_query_engine()` (`ramq_chatbot/factory.py`) is `lru_cache`d but invoked lazily inside the request handler (`router.py`), so building the BM25 retriever blocks the first user's coroutine and any concurrent requests. billing_codes' retriever builds eagerly at import time instead — chatbot doesn't.
  - Note: commit 51d729a only added a CI fixture table to unblock test collection — it did not fix this.

- [ ] 🟢 Backend has no network-level allowlist of its own — *added 8/19, from codebase audit*
  - `docker-compose.yml`: header-spoofing protection depends entirely on nginx being the only path to `backend:8000`. Partially mitigated since S1's fix moved backend to an `internal` network, but backend still has no self-defense if another container joins that network later.

- [ ] 🟢 Non-backend containers run with image-default privileges — *added 8/19, from codebase audit*
  - Postgres/redis/caddy/frontend don't set an explicit non-root `user:` in `docker-compose.yml`. Backend (the real attack surface) already drops to `appuser`.

- [ ] 🟢 DEPLOY.md and nginx's allowlist behavior disagree — *added 8/19, from codebase audit*
  - `DEPLOY.md:65-67` says leaving `ALLOWED_CIDRS` unset makes the demo fully public; `frontend/docker-entrypoint.sh` actually `deny all`s everything but `127.0.0.1` in that case. Fails safe, but will send an operator chasing a bogus CIDR issue.

- [ ] 🟢 Prompt injection surface is unhardened — *added 8/19, from codebase audit*
  - Transcript and chat text are interpolated directly into prompts (`summary/task.py`, `ramq_codes/task.py`, `ramq_chatbot/engine.py`) with only section headers, no delimiter/escaping scheme. Low impact today given JSON-schema output + mandatory physician review downstream.

- [ ] 🟢 Two sequential Postgres writes tail every extraction — *added 8/19, from codebase audit*
  - `extraction/router.py` fires two separate sessions/commits back-to-back after the LLM calls finish. Trivial next to LLM latency; worth batching into one transaction as a cleanliness win.

- [ ] 🟢 Chat bubbles re-parse markdown on every new message — *added 8/19, from codebase audit*
  - `ChatBubble.tsx` isn't wrapped in `React.memo`, so the full thread re-renders and re-parses every prior bubble on each append — O(n²) over a long conversation. No token streaming either.

## ✨ Features


## 🧹 Cleanup / Dead code

- [ ] 🟢 Unused dependency: pandas — *added 8/19, from codebase audit*
  - Declared in `backend/pyproject.toml`; zero imports anywhere in `app/`, `scripts/`, or `tests/`.

- [ ] 🟢 Unused "ghost" button variant — *added 8/19, from codebase audit*
  - `components/Button.tsx` + `styles.css:135-140` — defined with matching CSS, no call site anywhere passes `variant="ghost"`.

- [ ] 🟢 Unused `tagline` prop — *added 8/19, from codebase audit*
  - `components/PageHeader.tsx` renders it, but its only call site `SiteHeader.tsx` never supplies it.

- [ ] 🟢 `encounter_id` accepted, validated, then discarded — *added 8/19, from codebase audit, needs confirmation*
  - `extraction/models.py` / `extraction/router.py` — router only reads `source.system`; `encounter_id` is parsed and never persisted. Frontend doesn't send a `source` object today. CLAUDE.md frames multi-source ingestion (Epic/Plume) as part of the design, so may be intentional scaffolding rather than a mistake.

## ✅ Done

- [x] Rate-limit bypass via X-Forwarded-For spoofing — *added 8/19, done 8/18, from codebase audit*
  - Fixed by commit 5c231b5 ("Pin backend's trusted proxy IP to nginx's static compose address") — `--forwarded-allow-ips` now pinned to nginx's static IP on an internal compose network, instead of trusting `*`.

---
