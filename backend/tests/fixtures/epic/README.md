Epic FHIR R4 responses for the sandbox connector's unit tests (tests/test_intake_epic_fhir.py).
Synthetic data only.

- The top-level files are hand-built in the shape Epic answers with. They cover cases the
  real data doesn't have, such as a timed encounter or an entered-in-error note.
- `recorded/<patient id>/` holds real responses from the fhir.epic.com sandbox, saved by
  `scripts/epic_sandbox_inventory.py --record <patient id>`. That's the patient, the selected
  notes plus two drafts, three note bodies and their encounters.
