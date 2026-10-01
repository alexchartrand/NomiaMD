# Step 18 — Billing deadline tracker

**Phase:** 4 · **Depends on:** 06, 11 · **Unblocks:** —
**Plan section:** §2 Optimizations (billing deadline tracker)

## Goal
No encounter is lost to RAMQ's submission deadline.

## Tasks
- [ ] **Verify the deadline first.** Find the current RAMQ submission delay for omnipraticiens
  (fee-for-service) in the manual or the RAMQ site. Cite the section. It can differ by situation;
  list every case found.
- [ ] `app/intake/deadlines.py`: `BillingDeadlinePolicy.deadline_for(service_date, …) -> date`.
  The delay is a constant defined once, with the citation in a comment. "Today" comes from the
  injected `Clock`, never `date.today()`.
- [ ] `GET /encounters` adds `deadline` and `days_left` for encounters without a live claim, plus
  a `?due_within=N` filter (the encounter may be from any day).
- [ ] Inbox: a "À facturer bientôt" banner listing unclaimed encounters within 14 days of the
  deadline, sorted by `days_left`.

## Done when
- Policy unit tests with a fixed `Clock` (boundaries: the deadline day, the day after).
- The filter returns only unclaimed encounters. Voided claims count as unclaimed.
