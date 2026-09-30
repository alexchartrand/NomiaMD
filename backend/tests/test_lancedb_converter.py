"""Tests for app/lancedb/converter.py — IConverter's ABC contract, and CodesRowConverter's
mapping from the raw LanceDB row shape (CodeRow) to this backend's own internal Code shape."""

import pytest

from app.lancedb.converter import CodesRowConverter, DocumentRowConverter, IConverter
from app.lancedb.models import CodeRow, CodeRowFee, DocumentRow
from app.ramq_codes.models import Code, CodeEligibility


def test_cannot_instantiate_interface_directly():
    with pytest.raises(TypeError):
        IConverter()


def test_convert_maps_every_field_onto_code():
    row = CodeRow(
        number="15801",
        description="Visite de prise en charge d'une maladie chronique",
        header_path="B — Consultation, examen et visite > Visite de prise en charge",
        when_to_use=["Nouveau patient"],
        rules=["Clientele < 500 patients inscrits"],
        fees=[CodeRowFee(amount=33.15, amount_text="33,15", context="Par visite", lieux=["cabinet"], majoration=None)],
        max_age=79,
        max_panel_size=499,
        requires_registered=True,
        requires_vulnerable=False,
    )

    code = CodesRowConverter().convert(row)

    assert isinstance(code, Code)
    assert code.number == "15801"
    assert code.description == "Visite de prise en charge d'une maladie chronique"
    assert code.header_path == "B — Consultation, examen et visite > Visite de prise en charge"
    assert code.when_to_use == ("Nouveau patient",)
    assert code.rules == ("Clientele < 500 patients inscrits",)
    assert len(code.fees) == 1
    assert code.fees[0].amount == 33.15
    assert code.fees[0].amount_text == "33,15"
    assert code.fees[0].context == "Par visite"
    assert code.fees[0].lieux == ("cabinet",)
    assert code.fees[0].majoration is None
    assert code.fees[0].role is None
    assert code.fees[0].unit == "dollars"
    assert code.eligibility == CodeEligibility(
        max_age=79, max_panel_size=499, requires_registered=True, requires_vulnerable=False
    )


def test_convert_defaults_missing_optional_fields_to_empty():
    row = CodeRow(number="15801", description="", header_path="")

    code = CodesRowConverter().convert(row)

    assert code.when_to_use == ()
    assert code.rules == ()
    assert code.fees == ()
    assert code.eligibility == CodeEligibility()


def test_convert_maps_every_fee_in_a_multi_fee_row():
    row = CodeRow(
        number="15801",
        description="",
        header_path="",
        fees=[
            CodeRowFee(amount=1344.75, amount_text="1 344,75", role=1, context="Jour", lieux=["cabinet"]),
            CodeRowFee(amount=17, amount_text="17", role=2, unit="unités", context=None, majoration="20%"),
        ],
    )

    code = CodesRowConverter().convert(row)

    assert [(f.amount, f.role, f.unit, f.context, f.lieux, f.majoration) for f in code.fees] == [
        (1344.75, 1, "dollars", "Jour", ("cabinet",), None),
        (17, 2, "unités", None, (), "20%"),
    ]


def test_code_row_fee_reads_null_lieux_and_unit_as_their_defaults():
    fee = CodeRowFee.model_validate({"amount": 1.0, "lieux": None, "unit": None})

    assert fee.lieux == []
    assert fee.unit == "dollars"


def test_document_row_converter_carries_the_source_url_into_metadata():
    row = DocumentRow(id="A", text="texte", title="Guide", url="https://ramq.example/manuel#2.2.6")

    node = DocumentRowConverter().convert(row)

    assert node.metadata["url"] == "https://ramq.example/manuel#2.2.6"
