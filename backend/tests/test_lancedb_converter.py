"""Tests for app/lancedb/converter.py — IConverter's ABC contract, and CodesRowConverter's
mapping from the raw LanceDB row shape (CodeRow) to this backend's own internal Code shape."""

import pytest

from app.lancedb.converter import CodesRowConverter, IConverter
from app.lancedb.models import CodeRow, CodeRowFee
from app.ramq_codes.models import Code


def test_cannot_instantiate_interface_directly():
    with pytest.raises(TypeError):
        IConverter()


def test_convert_maps_every_field_onto_code():
    row = CodeRow(
        number="15801",
        description="Visite de prise en charge",
        when_to_use=["Nouveau patient"],
        rules=["Clientele < 500 patients inscrits"],
        fees=[CodeRowFee(amount=33.15, when_to_use="Par visite", majoration=None)],
        confidence=0.9,
    )

    code = CodesRowConverter().convert(row)

    assert isinstance(code, Code)
    assert code.number == "15801"
    assert code.description == "Visite de prise en charge"
    assert code.confidence == 0.9
    assert code.when_to_use == ("Nouveau patient",)
    assert code.rules == ("Clientele < 500 patients inscrits",)
    assert len(code.fees) == 1
    assert code.fees[0].amount == 33.15
    assert code.fees[0].when_to_use == "Par visite"
    assert code.fees[0].majoration is None


def test_convert_defaults_missing_optional_fields_to_empty():
    row = CodeRow(number="15801", description="", confidence=1.0)

    code = CodesRowConverter().convert(row)

    assert code.when_to_use == ()
    assert code.rules == ()
    assert code.fees == ()


def test_convert_maps_every_fee_in_a_multi_fee_row():
    row = CodeRow(
        number="15801",
        description="",
        confidence=1.0,
        fees=[
            CodeRowFee(amount=33.15, when_to_use="Jour", majoration=None),
            CodeRowFee(amount=50.00, when_to_use="Soir", majoration="20%"),
        ],
    )

    code = CodesRowConverter().convert(row)

    assert [(f.amount, f.when_to_use, f.majoration) for f in code.fees] == [
        (33.15, "Jour", None),
        (50.00, "Soir", "20%"),
    ]
