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
        libelle="Visite de prise en charge",
        description="Visite de prise en charge d'une maladie chronique",
        when_to_use=["Nouveau patient"],
        rules=["Clientele < 500 patients inscrits"],
        fees=[CodeRowFee(amount=33.15, amount_text="33,15", context="Par visite", lieu=None, majoration=None)],
    )

    code = CodesRowConverter().convert(row)

    assert isinstance(code, Code)
    assert code.number == "15801"
    assert code.libelle == "Visite de prise en charge"
    assert code.description == "Visite de prise en charge d'une maladie chronique"
    assert code.when_to_use == ("Nouveau patient",)
    assert code.rules == ("Clientele < 500 patients inscrits",)
    assert len(code.fees) == 1
    assert code.fees[0].amount == 33.15
    assert code.fees[0].amount_text == "33,15"
    assert code.fees[0].context == "Par visite"
    assert code.fees[0].lieu is None
    assert code.fees[0].majoration is None


def test_convert_defaults_missing_optional_fields_to_empty():
    row = CodeRow(number="15801", libelle="", description="")

    code = CodesRowConverter().convert(row)

    assert code.when_to_use == ()
    assert code.rules == ()
    assert code.fees == ()


def test_convert_maps_every_fee_in_a_multi_fee_row():
    row = CodeRow(
        number="15801",
        libelle="",
        description="",
        fees=[
            CodeRowFee(amount=33.15, amount_text="33,15", context="Jour", lieu="Cabinet", majoration=None),
            CodeRowFee(amount=50.00, amount_text="50,00", context="Soir", lieu="Domicile", majoration="20%"),
        ],
    )

    code = CodesRowConverter().convert(row)

    assert [(f.amount, f.context, f.lieu, f.majoration) for f in code.fees] == [
        (33.15, "Jour", "Cabinet", None),
        (50.00, "Soir", "Domicile", "20%"),
    ]
