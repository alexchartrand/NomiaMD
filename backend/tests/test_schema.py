"""Exercises app/tasks/schema.py's generic Pydantic-model -> (JSON schema / prompt block /
rendered text) conversions against a small synthetic model (fast, isolates the mechanism
from the real ConsultationSummaryResult's size) and against the real model (confirms every
field actually reaches the rendered text, which is the whole point of deriving it generically
instead of hand-mirroring the schema)."""

from typing import Literal

from pydantic import BaseModel, Field

from app.summary import ConsultationSummaryResult
from app.tasks.schema import render_instance, render_schema_block, to_strict_schema
from tests.test_consultation_summary import MOCK_RESULT


class _Item(BaseModel):
    label: str = Field(json_schema_extra={"fr_label": "Étiquette"})


class _Sample(BaseModel):
    required_text: str = Field(description="a short phrase")
    optional_text: str | None = Field(default=None, description="free text or null")
    flag: bool = Field(json_schema_extra={"fr_label": "Drapeau"})
    optional_flag: bool | None = Field(default=None, json_schema_extra={"fr_label": "Drapeau optionnel"})
    choice: Literal["a", "b"] = Field(json_schema_extra={"fr_label": "Choix"})
    optional_choice: Literal["x", "y"] | None = None
    tags: list[str] = Field(default_factory=list, json_schema_extra={"fr_label": "Étiquettes"})
    items: list[_Item] = Field(default_factory=list, json_schema_extra={"fr_label": "Article"})


def test_to_strict_schema_marks_every_field_required_and_forbids_extras():
    schema = to_strict_schema(_Sample)

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    # Optional fields are still required-but-nullable (OpenAI strict-mode convention), not
    # simply absent from `required`.
    assert schema["properties"]["optional_text"]["type"] == ["string", "null"]
    assert schema["properties"]["flag"] == {"type": "boolean"}
    assert schema["properties"]["optional_flag"]["type"] == ["boolean", "null"]
    assert schema["properties"]["choice"] == {"type": "string", "enum": ["a", "b"]}
    assert schema["properties"]["optional_choice"]["enum"] == ["x", "y", None]
    assert schema["properties"]["tags"] == {"type": "array", "items": {"type": "string"}}
    nested = schema["properties"]["items"]["items"]
    assert nested["required"] == ["label"]
    assert nested["additionalProperties"] is False


def test_render_schema_block_surfaces_descriptions_and_enum_values():
    block = render_schema_block(_Sample)

    assert '"<a short phrase>"' in block
    assert '"a | b"' in block
    assert '"x | y | null"' in block
    assert "free text or null" in block


def test_render_instance_omits_none_and_empty_but_keeps_false():
    instance = _Sample(required_text="hi", flag=False, choice="a")
    rendered = render_instance(instance)

    assert "Drapeau: non" in rendered
    # None/empty fields produce no line at all, not a literal "None"/"null".
    assert "optional" not in rendered.lower()
    assert "None" not in rendered
    assert "Étiquette" not in rendered  # empty items list


def test_render_instance_numbers_nested_list_items():
    instance = _Sample(
        required_text="hi",
        flag=True,
        choice="b",
        items=[_Item(label="premier"), _Item(label="second")],
    )
    rendered = render_instance(instance)

    assert "Article 1 - Étiquette: premier" in rendered
    assert "Article 2 - Étiquette: second" in rendered


def test_consultation_summary_render_reaches_every_leaf_field():
    # The generic renderer's whole purpose is that a field on ConsultationSummaryResult
    # can't silently go missing from render_for_billing_codes the way history_taken and
    # recommendations_given_to_patient used to under the old hand-written renderer.
    summary = ConsultationSummaryResult.model_validate(MOCK_RESULT)
    rendered = render_instance(summary)

    assert "Anamnèse effectuée: oui" in rendered
    assert "Recommandations données au patient: oui" in rendered


def test_consultation_summary_strict_schema_is_still_openai_compatible():
    schema = to_strict_schema(ConsultationSummaryResult)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
