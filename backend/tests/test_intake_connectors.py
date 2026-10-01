"""app/intake/connectors: the sample connector on the real consultations/ fixtures, the
paste splitter and NAM header reader (pure text, no DB), and the seed's path — every sample
through IntakeService.receive_all, twice — against the test DB."""

import itertools
from datetime import date

import pytest
from sqlalchemy import func, select

from app.intake import (
    Channel,
    DedupOutcome,
    IntakeService,
    ManualConnector,
    NoteSplitter,
    SampleConnector,
    UnsupportedUploadError,
)
from app.intake.connectors import SAMPLE_SOURCE_SYSTEM, read_header_nam
from app.postgresdb import Encounter, Gender, PatientRepository, session_scope
from tests.db_helpers import ensure_user_row, physician
from tests.test_intake_service import RecordingQueue

_physician_ids = itertools.count(5700)


def _note(nam: str | None, body: str) -> str:
    header = "**Clinique :** Clinique médicale Les Tilleuls\n**Patient :** Desjardins, Roch — 45 ans (H)"
    if nam is not None:
        header += f"\n**NAM :** {nam}"
    return f"{header}\n\n### Motif de consultation\n{body}\n"


# --- SampleConnector -------------------------------------------------------------------


def test_sample_connector_delivers_every_fixture_note():
    notes = SampleConnector().notes()

    assert len(notes) == 25
    assert {note.source_system for note in notes} == {SAMPLE_SOURCE_SYSTEM}
    assert {note.channel for note in notes} == {Channel.SAMPLE}
    assert len({note.external_note_id for note in notes}) == 25


def test_sample_connector_reads_nam_and_date_from_the_header():
    stemi = next(note for note in SampleConnector().notes() if note.external_note_id == "URG-2026-04471")

    assert stemi.nam == "GAGR59071301"
    assert stemi.service_date is not None
    assert "STEMI" in stemi.text


# --- NAM header ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    ["**NAM :** DESR81021001", "NAM : DESR 8102 1001", "NAM: desr-8102-1001", "**NAM** : DESR81021001 (exp. 2027-02)"],
)
def test_header_nam_is_read_in_its_usual_spellings(line):
    assert read_header_nam(f"Patient : Roch\n{line}\nMotif : toux") == "DESR81021001"


def test_a_nam_in_the_prose_is_not_a_header():
    assert read_header_nam("Patient vu ce matin, NAM DESR81021001 vérifié à l'accueil.") is None


def test_a_malformed_header_nam_is_none():
    assert read_header_nam("**NAM :** DESR8102") is None


def test_two_disagreeing_header_nams_are_ambiguous():
    assert read_header_nam("**NAM :** DESR81021001\n**NAM :** GAGR59071301") is None


def test_the_same_nam_twice_is_not_ambiguous():
    assert read_header_nam("**NAM :** DESR81021001\nNAM : DESR 8102 1001") == "DESR81021001"


# --- NoteSplitter ----------------------------------------------------------------------


def test_a_single_note_is_one_piece():
    note = _note("DESR81021001", "Toux depuis 3 jours.")
    assert NoteSplitter().split(note) == [note.strip()]


def test_three_notes_split_on_their_nam_headers():
    notes = [_note(nam, f"Note {i}.") for i, nam in enumerate(["DESR81021001", "GAGR59071301", "TREM55120302"])]

    pieces = NoteSplitter().split("\n".join(notes))

    assert pieces == [note.strip() for note in notes]
    # The lines above the NAM in each header stayed with their own note.
    assert all(piece.startswith("**Clinique :**") for piece in pieces)


def test_two_notes_split_on_an_explicit_separator():
    first, second = "Patient 1 : toux.", "Patient 2 : entorse cheville."
    assert NoteSplitter().split(f"{first}\n\n---\n\n{second}\n---\n") == [first, second]


def test_a_title_above_the_first_nam_header_stays_with_the_first_note():
    paste = "Urgence nuit du 1er octobre\n\n" + _note("DESR81021001", "A.") + "\n" + _note("GAGR59071301", "B.")

    pieces = NoteSplitter().split(paste)

    assert len(pieces) == 2
    assert pieces[0].startswith("Urgence nuit")


def test_blank_and_empty_pastes_give_no_pieces():
    assert NoteSplitter().split("") == []
    assert NoteSplitter().split("\n  \n---\n\n") == []


# --- ManualConnector -------------------------------------------------------------------


def test_paste_gives_one_source_note_per_piece_with_its_nam():
    paste = _note("DESR81021001", "A.") + "\n" + _note("GAGR59071301", "B.") + "\n---\n" + _note(None, "C.")

    notes = ManualConnector().from_paste(paste, source_system="epic")

    assert [note.nam for note in notes] == ["DESR81021001", "GAGR59071301", None]
    assert {note.channel for note in notes} == {Channel.PASTE}
    assert {note.source_system for note in notes} == {"epic"}


def test_a_note_without_a_nam_keeps_none():
    [note] = ManualConnector().from_paste(_note(None, "Toux."), source_system="manual")
    assert note.nam is None


def test_batch_label_propagates_to_every_piece():
    paste = "\n---\n".join(_note(None, f"Note {i}.") for i in range(3))

    notes = ManualConnector().from_paste(paste, source_system="manual", batch_label="Urgence 2026-10-01 nuit")

    assert len(notes) == 3
    assert {note.batch_label for note in notes} == {"Urgence 2026-10-01 nuit"}


def test_upload_reads_a_text_file_like_a_paste():
    content = ("﻿" + _note("DESR81021001", "Toux.")).encode("utf-8")

    [note] = ManualConnector().from_upload("notes.MD", content, source_system="manual", batch_label="Lot")

    assert note.channel == Channel.UPLOAD
    assert note.nam == "DESR81021001"
    assert note.batch_label == "Lot"
    assert not note.text.startswith("﻿")


@pytest.mark.parametrize(
    ("filename", "content"),
    [("note.pdf", b"%PDF-1.7"), ("note", b"Toux."), ("note.txt", "Toux é".encode("latin-1"))],
)
def test_upload_rejects_anything_but_utf8_txt_or_md(filename, content):
    with pytest.raises(UnsupportedUploadError):
        ManualConnector().from_upload(filename, content, source_system="manual")


# --- The seed's path -------------------------------------------------------------------


async def _encounter_count(user_id: int) -> int:
    async with session_scope() as session:
        return await session.scalar(select(func.count()).select_from(Encounter).where(Encounter.user_id == user_id))


async def test_seeding_the_samples_creates_one_encounter_each_and_reseeding_none():
    user = physician(next(_physician_ids))
    await ensure_user_row(user)
    # One sample's patient exists; the others arrive "à associer".
    async with session_scope() as session:
        await PatientRepository(session).get_or_create_by_ramq_number(
            ramq_number="GAGR59071301",
            full_name="Gagnon, Raymond",
            date_of_birth=date(1959, 7, 13),
            gender=Gender.MALE,
            is_vulnerable=False,
        )
    queue = RecordingQueue()
    intake = IntakeService(queue)

    first = await intake.receive_all(SampleConnector().notes(), user)

    assert [outcome.outcome for outcome in first] == [DedupOutcome.NEW] * 25
    assert await _encounter_count(user.id) == 25
    assert len(queue.enqueued) == 1

    second = await intake.receive_all(SampleConnector().notes(), user)

    assert [outcome.outcome for outcome in second] == [DedupOutcome.DUPLICATE] * 25
    assert [outcome.encounter_id for outcome in second] == [outcome.encounter_id for outcome in first]
    assert await _encounter_count(user.id) == 25
    assert len(queue.enqueued) == 1
