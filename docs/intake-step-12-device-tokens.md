# Step 12 — Device tokens (scoped API tokens)

**Phase:** 3 (weeks 9–14) · **Depends on:** 09 · **Unblocks:** 13, 14
**Plan section:** §3 Extension risk (device auth), §4 Browser extension

## Goal
Let the browser extension call `/intake/notes` as the physician, without the session cookie,
using a token the physician can revoke.

## Tasks
- [ ] `DeviceToken` model, table `device_tokens`:
  - `user_id`, `name` ("Chrome — bureau")
  - `token_hash` (sha256 of a 32-byte random token: high entropy, so no Argon2 needed)
  - `scopes` (JSON list), `last_used_at`, `revoked_at` (never hard-deleted), `created_at`
- [ ] `DeviceTokenService` (`app/auth/device_tokens.py`): `issue` (returns the plaintext once),
  `revoke`, `authenticate(bearer) -> (User, scopes)`.
- [ ] Routes in `app/auth/router.py`: `POST /auth/device-tokens`, `GET /auth/device-tokens`,
  `DELETE /auth/device-tokens/{id}` (session auth only; a device token can't mint tokens).
- [ ] Dependency `require_scope("intake:write")`: accepts the session cookie **or**
  `Authorization: Bearer <device token>` with that scope. Apply it to `POST /intake/notes`
  and `GET /encounters/{id}` (`encounters:read`, for the side panel).
- [ ] CORS: allow the extension origin (`chrome-extension://<id>`) on those routes only.
  Configure it through env, not a wildcard.
- [ ] Frontend: an "Appareils connectés" section on `ProfilePage.tsx` with create (token shown
  once, copy button), list and revoke.

## Done when
Tests cover:
- a token works on the allowed route and gets 403 on others (for example `/claims`)
- a revoked token gets 401
- `last_used_at` updates
- a token can't create a token
- constant-time comparison (compare hashes)
