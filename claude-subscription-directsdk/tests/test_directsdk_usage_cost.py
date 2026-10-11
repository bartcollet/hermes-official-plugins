"""get_usage_cost: subscription-included accounting with a list-price gauge.

Claude Max bills $0 out-of-pocket; native's ``total_cost_usd`` is the LIST-PRICE
equivalent of the usage. The cost result must say ``included``/``$0`` with the
gauge on ``list_price_usd`` — never ``estimated``/``provider_cost_api`` (that
labelled a non-existent invoice and inflated spend reports).
"""
import dataclasses
import sys
from decimal import Decimal

from agent.usage_pricing import CanonicalUsage, CostResult

# Cores before hermes-agent#136076 have no `CostResult.list_price_usd`: there the plugin reports
# the same included/$0 result without the gauge.
CORE_HAS_LIST_PRICE = "list_price_usd" in {f.name for f in dataclasses.fields(CostResult)}


def _usage(total="2.41", models=None, basis="list"):
    models = models if models is not None else {"claude-opus-5-5[1m]": {"costBasis": basis}}
    return CanonicalUsage(
        input_tokens=1700, output_tokens=2300,
        raw_usage={"native_cost": {"total_cost_usd": total, "modelUsage": models}},
    )


def test_list_price_cost_is_included_with_gauge(profile):
    result = profile.get_usage_cost("claude-opus-5-5[1m]", _usage("2.41"))
    assert result.amount_usd == Decimal("0")
    assert result.status == "included"
    assert result.source == "subscription_included"
    assert result.label == "included"
    if CORE_HAS_LIST_PRICE:
        assert result.list_price_usd == Decimal("2.41")
    else:
        assert not hasattr(result, "list_price_usd")
    assert "list-price equivalent" in " ".join(result.notes)


def test_zero_list_price_is_still_included(profile):
    result = profile.get_usage_cost("claude-opus-5-5[1m]", _usage("0"))
    assert result.amount_usd == Decimal("0")
    assert result.status == "included"
    if CORE_HAS_LIST_PRICE:
        assert result.list_price_usd == Decimal("0")
    else:
        assert not hasattr(result, "list_price_usd")


def test_core_without_list_price_falls_back_to_included_without_gauge(profile, monkeypatch):
    """Forces the no-field path so it is covered on cores that do have the field."""
    monkeypatch.setattr(sys.modules[type(profile).__module__], "_CORE_HAS_LIST_PRICE", False)
    result = profile.get_usage_cost("claude-opus-5-5[1m]", _usage("2.41"))
    assert result.amount_usd == Decimal("0")
    assert result.status == "included"
    assert result.source == "subscription_included"
    assert result.label == "included"
    assert getattr(result, "list_price_usd", None) is None
    assert "list-price equivalent" in " ".join(result.notes)


def test_unknown_paths_stay_unknown(profile):
    no_models = profile.get_usage_cost("claude-opus-5-5[1m]", _usage(models={}))
    assert no_models.status == "unknown"
    assert no_models.amount_usd is None

    non_list = profile.get_usage_cost("claude-opus-5-5[1m]", _usage(basis="invoice"))
    assert non_list.status == "unknown"
    assert non_list.amount_usd is None

    non_numeric = profile.get_usage_cost("claude-opus-5-5[1m]", _usage(total="not-a-number"))
    assert non_numeric.status == "unknown"
    assert non_numeric.amount_usd is None
