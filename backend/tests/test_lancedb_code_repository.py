"""Tests for app/lancedb/repository.py's CodeRepository and app/lancedb/code_versions.py's
CurrentCodeTableProvider — built against a real, local lancedb directory
(embedded/no-server/no-network) rather than a fake, matching
tests/test_lancedb_document_repository.py's own carve-out reasoning: the point of these
tests is to pin the actual query behavior LanceDB's own async query builder gives back
(MultiMatchQuery fusing several FTS columns into one hybrid search, the eligibility WHERE
applied to it, a registry flip seen through an already-open connection) — a fake table
can't prove any of that.

The fixture schemas duplicate ramq-ingestion's codes/storage/code_table_schema.py and
code_version_registry.py column-for-column by hand rather than importing them — the two
repos share no code, so this duplication *is* the deploy contract this suite pins down (see
CLAUDE.md's RAMQ data note): if ramq-ingestion's writer and this backend's reader ever
disagree on the tables' shape, this fixture (not a shared import) is what would need
updating to notice.

No FTS index is built in these fixtures (confirmed empirically that MultiMatchQuery via
nearest_to_text silently falls back to an unindexed scan when no index exists, same as the
plain-string case DocumentRepository.hybrid_search already relies on) — building/proving the
indices themselves is ramq-ingestion's own test suite's job (test_code_index_builder.py)."""

import tempfile
from datetime import timedelta

import lancedb
import pyarrow as pa
import pytest

from app.lancedb.code_versions import (
    CurrentCodeTableProvider,
    NoCurrentCodesTableError,
    PinnedCodeTableProvider,
    UnknownCodesTableError,
)
from app.lancedb.eligibility import CodeEligibilityFilter
from app.lancedb.models import CodeRow
from app.lancedb.repository import CodeRepository, ICodeRepository

TABLE_NAME = "codes_2026-06-05"
REGISTRY_TABLE_NAME = "code_versions"
EMBED_DIM = 4

_FEE_TYPE = pa.struct(
    [
        pa.field("amount", pa.float64()),
        pa.field("amount_text", pa.string()),
        pa.field("role", pa.int32()),
        pa.field("unit", pa.string()),
        pa.field("context", pa.string()),
        pa.field("lieux", pa.list_(pa.string())),
        pa.field("majoration", pa.string()),
    ]
)


def _schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("number", pa.string(), nullable=False),
            pa.field("description", pa.string(), nullable=False),
            pa.field("header_path", pa.string(), nullable=False),
            pa.field("when_to_use", pa.list_(pa.string()), nullable=False),
            pa.field("rules", pa.list_(pa.string()), nullable=False),
            pa.field("fees", pa.list_(_FEE_TYPE), nullable=False),
            pa.field("min_age", pa.int32(), nullable=True),
            pa.field("max_age", pa.int32(), nullable=True),
            pa.field("min_panel_size", pa.int32(), nullable=True),
            pa.field("max_panel_size", pa.int32(), nullable=True),
            pa.field("requires_registered", pa.bool_(), nullable=True),
            pa.field("requires_vulnerable", pa.bool_(), nullable=True),
            pa.field("lexical_terms", pa.list_(pa.string()), nullable=False),
            pa.field("expansion_terms", pa.list_(pa.string()), nullable=False),
            pa.field("needs_review", pa.bool_(), nullable=False),
            pa.field("review_reason", pa.string(), nullable=True),
            pa.field("vector", pa.list_(pa.float32(), EMBED_DIM), nullable=False),
        ]
    )


def _registry_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("manual_rev", pa.string(), nullable=False),
            pa.field("table_name", pa.string(), nullable=False),
            pa.field("is_current", pa.bool_(), nullable=False),
            pa.field("promoted_at", pa.string(), nullable=False),
            pa.field("code_count", pa.int64(), nullable=False),
        ]
    )


def _record(
    number: str,
    description: str = "description",
    vector: list[float] | None = None,
    lexical_terms: list[str] | None = None,
    expansion_terms: list[str] | None = None,
    fees: list[dict] | None = None,
    **eligibility,
) -> dict:
    return {
        "number": number,
        "description": description,
        "header_path": "/1/1.1",
        "when_to_use": [],
        "rules": [],
        "fees": fees or [],
        "min_age": None,
        "max_age": None,
        "min_panel_size": None,
        "max_panel_size": None,
        "requires_registered": None,
        "requires_vulnerable": None,
        "lexical_terms": lexical_terms or [],
        "expansion_terms": expansion_terms or [],
        "needs_review": False,
        "review_reason": None,
        "vector": vector or [0.1, 0.2, 0.3, 0.4],
        **eligibility,
    }


def _version(table_name: str, is_current: bool) -> dict:
    return {
        "manual_rev": table_name.removeprefix("codes_"),
        "table_name": table_name,
        "is_current": is_current,
        "promoted_at": "2026-09-30T00:00:00+00:00",
        "code_count": 1,
    }


def _seed(persist_dir: str, tables: dict[str, list[dict]], current: str | None) -> None:
    db = lancedb.connect(persist_dir)
    for name, records in tables.items():
        db.create_table(name, schema=_schema()).add(records)
    registry = db.create_table(REGISTRY_TABLE_NAME, schema=_registry_schema())
    registry.add([_version(name, name == current) for name in tables])


async def _provider(persist_dir: str) -> CurrentCodeTableProvider:
    # read_consistency_interval=0: every read re-checks for a newer table version, so a test
    # can write through a second (sync) connection and see it immediately.
    connection = await lancedb.connect_async(persist_dir, read_consistency_interval=timedelta(0))
    registry = await connection.open_table(REGISTRY_TABLE_NAME)
    return CurrentCodeTableProvider(connection, registry)


async def _async_repository(persist_dir: str, records: list[dict]) -> CodeRepository:
    _seed(persist_dir, {TABLE_NAME: records}, current=TABLE_NAME)
    return CodeRepository(await _provider(persist_dir))


def test_cannot_instantiate_interface_directly():
    with pytest.raises(TypeError):
        ICodeRepository()


async def test_get_by_number_returns_the_matching_row():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("A"), _record("B")]
        repository = await _async_repository(persist_dir, records)

        row = await repository.get_by_number("A")

        assert isinstance(row, CodeRow)
        assert row.number == "A"


async def test_get_by_number_reads_the_new_fee_and_eligibility_columns():
    with tempfile.TemporaryDirectory() as persist_dir:
        fees = [
            {"amount": 1344.75, "amount_text": "1 344,75", "role": 1, "unit": "dollars",
             "context": "En cabinet", "lieux": ["cabinet"], "majoration": None},
            {"amount": 17.0, "amount_text": "17", "role": 2, "unit": "unités",
             "context": None, "lieux": [], "majoration": None},
        ]
        repository = await _async_repository(
            persist_dir, [_record("07520", fees=fees, max_age=79, requires_registered=True)]
        )

        row = await repository.get_by_number("07520")

        assert [(f.role, f.unit, f.lieux) for f in row.fees] == [(1, "dollars", ["cabinet"]), (2, "unités", [])]
        assert (row.max_age, row.min_age, row.requires_registered) == (79, None, True)


async def test_list_by_numbers_returns_every_matching_row():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("A"), _record("B"), _record("C")]
        repository = await _async_repository(persist_dir, records)

        rows = await repository.list_by_numbers(["A", "C"])

        assert {r.number for r in rows} == {"A", "C"}


async def test_hybrid_search_returns_rows_with_a_relevance_score():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("A", description="urgence de nuit", vector=[1.0, 0.0, 0.0, 0.0]),
            _record("B", description="consultation de routine", vector=[0.0, 1.0, 0.0, 0.0]),
        ]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(text="urgence", vector=[1.0, 0.0, 0.0, 0.0], k=5)

        assert len(hits) >= 1
        row, score = hits[0]
        assert isinstance(row, CodeRow)
        assert row.number == "A"
        assert isinstance(score, float)


async def test_hybrid_search_limits_to_k():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record(str(i), vector=[1.0, float(i), 0.0, 0.0]) for i in range(5)]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(text="description", vector=[1.0, 0.0, 0.0, 0.0], k=2)

        assert len(hits) == 2


async def test_hybrid_search_never_returns_the_vector_column():
    # CodeRow has no `vector` field — .select() must omit it so it never crosses the wire
    # for a hit about to be converted to a Code and discarded (see models.py).
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("A")]
        repository = await _async_repository(persist_dir, records)

        [(row, _score)] = await repository.hybrid_search(text="description", vector=[0.1, 0.2, 0.3, 0.4], k=5)

        assert not hasattr(row, "vector")


async def test_hybrid_search_logs_no_scoring_autoprojection_warning(capfd):
    # lance's deprecation warning about `_score`/`_distance` missing from an explicit select
    # goes to the process's stderr from Rust, hence capfd rather than caplog (see hybrid.py).
    with tempfile.TemporaryDirectory() as persist_dir:
        repository = await _async_repository(persist_dir, [_record("A")])

        await repository.hybrid_search(text="description", vector=[0.1, 0.2, 0.3, 0.4], k=5)

        assert "disable_scoring_autoprojection" not in capfd.readouterr().err


async def test_hybrid_search_matches_on_lexical_terms_alone():
    # The whole point of MultiMatchQuery over several columns: a synonym that only lives in
    # lexical_terms (never in description) still surfaces its row.
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("A", description="quelque chose d'autre", lexical_terms=["hypertension arterielle"]),
            _record("B", description="autre chose encore"),
        ]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(text="hypertension", vector=[0.1, 0.2, 0.3, 0.4], k=5)

        assert "A" in [row.number for row, _score in hits]


async def test_hybrid_search_matches_on_bare_code_number():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("15188"), _record("99999")]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(text="15188", vector=[0.1, 0.2, 0.3, 0.4], k=5)

        assert "15188" in [row.number for row, _score in hits]


# -- eligibility prefilter ------------------------------------------------------------------


async def test_hybrid_search_drops_variants_contradicting_a_known_fact_but_keeps_null_bounds():
    # Mirrors the real 15801/15802 pair: same visit, split on panel size.
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("15801", max_panel_size=499, max_age=79, requires_registered=True, requires_vulnerable=False),
            _record("15802", min_panel_size=500, max_age=79, requires_registered=True, requires_vulnerable=False),
            _record("00059"),  # no bound on any axis — always eligible
        ]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(
            text="description",
            vector=[0.1, 0.2, 0.3, 0.4],
            k=10,
            eligibility=CodeEligibilityFilter(age=45, panel_size=800, is_registered=True, is_vulnerable=False),
        )

        assert sorted(row.number for row, _score in hits) == ["00059", "15802"]


async def test_hybrid_search_bounds_are_inclusive():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("under80", max_age=79), _record("80plus", min_age=80)]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(
            text="description", vector=[0.1, 0.2, 0.3, 0.4], k=10, eligibility=CodeEligibilityFilter(age=79)
        )

        assert [row.number for row, _score in hits] == ["under80"]


async def test_hybrid_search_with_an_empty_filter_keeps_every_variant():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("15801", max_panel_size=499), _record("15802", min_panel_size=500)]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(
            text="description", vector=[0.1, 0.2, 0.3, 0.4], k=10, eligibility=CodeEligibilityFilter()
        )

        assert sorted(row.number for row, _score in hits) == ["15801", "15802"]


# -- section scope ----------------------------------------------------------------------------


async def test_hybrid_search_keeps_only_rows_under_the_given_sections():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("15803", header_path="B — Consultation, examen et visite > Visites sur rendez-vous"),
            _record("01323", header_path="F — Peau phanères > Réparation de plaies"),
            _record("00431", header_path="C — Actes diagnostiques et thérapeutiques > Injection"),
        ]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(
            text="description", vector=[0.1, 0.2, 0.3, 0.4], k=10, sections=("B — Consultation", "C — Actes")
        )

        assert sorted(row.number for row, _score in hits) == ["00431", "15803"]


async def test_hybrid_search_applies_the_section_scope_and_eligibility_together():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("under80", header_path="B — visite", max_age=79),
            _record("80plus", header_path="B — visite", min_age=80),
            _record("other", header_path="C — acte"),
        ]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(
            text="description",
            vector=[0.1, 0.2, 0.3, 0.4],
            k=10,
            eligibility=CodeEligibilityFilter(age=45),
            sections=("B —",),
        )

        assert [row.number for row, _score in hits] == ["under80"]


async def test_hybrid_search_section_prefix_is_literal_not_a_like_pattern():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("literal", header_path="B_1 > x"), _record("wildcard", header_path="BX1 > x")]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.hybrid_search(text="description", vector=[0.1, 0.2, 0.3, 0.4], k=10, sections=("B_1",))

        assert [row.number for row, _score in hits] == ["literal"]


# -- families -------------------------------------------------------------------------------


async def test_list_by_header_paths_returns_whole_families_minus_ineligible_variants():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("15638", header_path="B > CHSGS > Niveau A"),
            _record("15639", header_path="B > CHSGS > Niveau A"),
            _record("15640", header_path="B > CHSGS > Niveau A", min_age=80),
            _record("15641", header_path="B > CHSGS > Niveau B"),
            _record("15642", header_path="B > CHSGS"),  # a parent path is another family
        ]
        repository = await _async_repository(persist_dir, records)

        rows = await repository.list_by_header_paths(["B > CHSGS > Niveau A"], CodeEligibilityFilter(age=66))

        assert sorted(r.number for r in rows) == ["15638", "15639"]


async def test_list_by_header_paths_with_no_path_reads_nothing():
    with tempfile.TemporaryDirectory() as persist_dir:
        repository = await _async_repository(persist_dir, [_record("A")])

        assert await repository.list_by_header_paths([]) == []


# -- manual search (ICodeCatalogRepository) -------------------------------------------------


async def test_keyword_search_matches_description_without_a_vector():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("A", description="suture d'une plaie"),
            _record("B", description="consultation de routine"),
        ]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.keyword_search("suture", k=5)

        assert [row.number for row, _score in hits] == ["A"]
        assert isinstance(hits[0][1], float)


async def test_keyword_search_applies_the_eligibility_filter():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [
            _record("under80", description="visite de suivi", max_age=79),
            _record("80plus", description="visite de suivi", min_age=80),
        ]
        repository = await _async_repository(persist_dir, records)

        hits = await repository.keyword_search("visite", k=5, eligibility=CodeEligibilityFilter(age=85))

        assert [row.number for row, _score in hits] == ["80plus"]


async def test_list_by_number_prefix_returns_matching_numbers_in_order_up_to_k():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("15803"), _record("15801"), _record("15802"), _record("00059")]
        repository = await _async_repository(persist_dir, records)

        rows = await repository.list_by_number_prefix("158", k=2)

        assert [r.number for r in rows] == ["15801", "15802"]


async def test_list_by_number_prefix_applies_the_eligibility_filter():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("15801", max_panel_size=499), _record("15802", min_panel_size=500)]
        repository = await _async_repository(persist_dir, records)

        rows = await repository.list_by_number_prefix("158", k=10, eligibility=CodeEligibilityFilter(panel_size=800))

        assert [r.number for r in rows] == ["15802"]


async def test_list_by_numbers_drops_ineligible_rows_when_filtered():
    with tempfile.TemporaryDirectory() as persist_dir:
        records = [_record("15801", requires_registered=True), _record("00059")]
        repository = await _async_repository(persist_dir, records)

        rows = await repository.list_by_numbers(
            ["15801", "00059"], eligibility=CodeEligibilityFilter(is_registered=False)
        )

        assert [r.number for r in rows] == ["00059"]


async def test_list_by_numbers_with_no_numbers_returns_nothing():
    with tempfile.TemporaryDirectory() as persist_dir:
        repository = await _async_repository(persist_dir, [_record("A")])

        assert await repository.list_by_numbers([]) == []


async def test_current_revision_is_the_registry_rows_manual_rev():
    with tempfile.TemporaryDirectory() as persist_dir:
        repository = await _async_repository(persist_dir, [_record("A")])

        assert await repository.current_revision() == "2026-06-05"


# -- code_versions registry -----------------------------------------------------------------


async def test_reads_from_the_table_the_registry_marks_current():
    with tempfile.TemporaryDirectory() as persist_dir:
        _seed(
            persist_dir,
            {"codes_2026-01-01": [_record("OLD")], "codes_2026-06-05": [_record("NEW")]},
            current="codes_2026-06-05",
        )
        repository = CodeRepository(await _provider(persist_dir))

        rows = await repository.list_by_numbers(["OLD", "NEW"])

        assert [r.number for r in rows] == ["NEW"]


async def test_follows_a_promote_without_reopening():
    with tempfile.TemporaryDirectory() as persist_dir:
        _seed(
            persist_dir,
            {"codes_2026-01-01": [_record("OLD")], "codes_2026-06-05": [_record("NEW")]},
            current="codes_2026-01-01",
        )
        provider = await _provider(persist_dir)
        repository = CodeRepository(provider)
        assert [r.number for r in await repository.list_by_numbers(["OLD", "NEW"])] == ["OLD"]

        # Same single-commit flip ramq-ingestion's LanceCodeVersionRegistry.mark_current does.
        registry = lancedb.connect(persist_dir).open_table(REGISTRY_TABLE_NAME)
        registry.update(values_sql={"is_current": "manual_rev = '2026-06-05'"})

        assert [r.number for r in await repository.list_by_numbers(["OLD", "NEW"])] == ["NEW"]
        assert (await provider.current_version()).table_name == "codes_2026-06-05"


async def test_raises_when_no_table_is_current():
    with tempfile.TemporaryDirectory() as persist_dir:
        _seed(persist_dir, {TABLE_NAME: [_record("A")]}, current=None)
        provider = await _provider(persist_dir)

        with pytest.raises(NoCurrentCodesTableError):
            await provider.current()


async def test_raises_when_more_than_one_table_is_current():
    with tempfile.TemporaryDirectory() as persist_dir:
        _seed(persist_dir, {"codes_2026-01-01": [_record("A")], TABLE_NAME: [_record("B")]}, current=None)
        lancedb.connect(persist_dir).open_table(REGISTRY_TABLE_NAME).update(values_sql={"is_current": "true"})
        provider = await _provider(persist_dir)

        with pytest.raises(NoCurrentCodesTableError):
            await provider.current()


# -- pinned table (the benchmark's --codes-table) ------------------------------------------


async def _pinned(persist_dir: str, table_name: str) -> PinnedCodeTableProvider:
    connection = await lancedb.connect_async(persist_dir)
    registry = await connection.open_table(REGISTRY_TABLE_NAME)
    return PinnedCodeTableProvider(connection, registry, table_name)


async def test_a_pinned_provider_reads_a_table_that_is_not_current():
    with tempfile.TemporaryDirectory() as persist_dir:
        _seed(
            persist_dir,
            {"codes_2026-01-01": [_record("OLD")], "codes_2026-06-05": [_record("NEW")]},
            current="codes_2026-06-05",
        )
        provider = await _pinned(persist_dir, "codes_2026-01-01")
        repository = CodeRepository(provider)

        assert [r.number for r in await repository.list_by_numbers(["OLD", "NEW"])] == ["OLD"]
        assert (await provider.current_version()).manual_rev == "2026-01-01"


async def test_a_pinned_provider_refuses_an_unregistered_table():
    with tempfile.TemporaryDirectory() as persist_dir:
        _seed(persist_dir, {TABLE_NAME: [_record("A")]}, current=TABLE_NAME)
        provider = await _pinned(persist_dir, "codes_nope")

        with pytest.raises(UnknownCodesTableError, match="codes_nope"):
            await provider.current()
