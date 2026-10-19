"""Estimated cost of metered LLM calls, for the admin console's usage report. An estimate,
not an invoice: list prices in USD per million tokens, by model name. A model with no price
costs None — the report shows it as unknown rather than guessing."""

import json
import logging
from dataclasses import dataclass
from decimal import Decimal

from app.config import settings

logger = logging.getLogger(__name__)

_PER_TOKENS = Decimal(1_000_000)


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: Decimal
    output_per_million: Decimal = Decimal(0)


# List prices of the default models (app/summary/summarizer.py, app/ramq_codes/selector.py,
# app/ramq_chatbot/factory.py, the embedding model) when this table was written. Check them
# against the provider's price page and override with LLM_PRICES when they change.
DEFAULT_PRICES: dict[str, ModelPrice] = {
    "mistral-small-latest": ModelPrice(Decimal("0.10"), Decimal("0.30")),
    "mistral-medium-latest": ModelPrice(Decimal("0.40"), Decimal("2.00")),
    "mistral-embed": ModelPrice(Decimal("0.10")),
}


class PriceTable:
    def __init__(self, prices: dict[str, ModelPrice]) -> None:
        self._prices = prices

    @classmethod
    def from_settings(cls) -> "PriceTable":
        prices = dict(DEFAULT_PRICES)
        prices.update(_parse_overrides(settings.llm_prices))
        return cls(prices)

    def cost(self, model: str, input_tokens: int | None, output_tokens: int | None) -> Decimal | None:
        price = self._prices.get(model)
        if price is None:
            return None
        return (
            Decimal(input_tokens or 0) * price.input_per_million
            + Decimal(output_tokens or 0) * price.output_per_million
        ) / _PER_TOKENS

    def is_priced(self, model: str) -> bool:
        return model in self._prices


def _parse_overrides(raw: str | None) -> dict[str, ModelPrice]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return {
            model: ModelPrice(Decimal(str(entry["input"])), Decimal(str(entry.get("output", 0))))
            for model, entry in data.items()
        }
    except (ValueError, TypeError, KeyError, AttributeError):
        # A malformed override must not take the console down: fall back to the defaults.
        logger.warning("Ignoring malformed LLM_PRICES")
        return {}
