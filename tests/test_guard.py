import pytest
from promisekeeper.compiler.guard import evaluate_guard, GuardExpressionError

def test_simple_comparison():
    assert evaluate_guard("tier == 'gold'", {"tier": "gold"}) is True
    assert evaluate_guard("tier == 'gold'", {"tier": "silver"}) is False

def test_boolean_and_lowercase_true_literal():
    assert evaluate_guard("true", {}) is True
    assert evaluate_guard("destination_region != 'EU' and order_value < 5000",
                           {"destination_region": "US", "order_value": 100}) is True

def test_rejects_arbitrary_code():
    with pytest.raises(GuardExpressionError):
        evaluate_guard("__import__('os').system('echo hi')", {})

def test_rejects_attribute_and_call_access():
    with pytest.raises(GuardExpressionError):
        evaluate_guard("tier.upper() == 'GOLD'", {"tier": "gold"})

def test_rejects_unknown_identifier():
    with pytest.raises(GuardExpressionError):
        evaluate_guard("nonexistent_field == 1", {})
