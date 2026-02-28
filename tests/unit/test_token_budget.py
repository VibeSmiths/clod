"""
Unit tests for TokenBudget class and check_token_thresholds().
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod
from clod import TokenBudget, check_token_thresholds

# ── Basic TokenBudget behaviour ────────────────────────────────────────────────


def test_empty_budget_zero_fraction():
    """A fresh TokenBudget has fraction=0 and pct=0."""
    budget = TokenBudget(10000)
    assert budget.fraction == 0.0
    assert budget.pct == 0


def test_add_increments_used():
    """Adding messages and output text increases the used counter."""
    budget = TokenBudget(10000)
    msgs = [{"role": "user", "content": "Hello, how are you?"}]
    budget.add(msgs, "I am fine, thank you.")
    assert budget.used > 0


def test_pct_clamped_at_100():
    """pct never exceeds 100 even when used > budget."""
    budget = TokenBudget(100)
    budget.used = 500  # well over budget
    assert budget.pct == 100


def test_bar_empty():
    """bar() returns all empty chars when used=0."""
    budget = TokenBudget(10000)
    b = budget.bar(10)
    assert b == "░" * 10


def test_bar_full():
    """bar() returns all filled chars at 100%."""
    budget = TokenBudget(10000)
    budget.used = 10000
    b = budget.bar(10)
    assert b == "█" * 10


def test_bar_half():
    """bar() returns half filled at 50%."""
    budget = TokenBudget(10000)
    budget.used = 5000
    b = budget.bar(10)
    assert b.count("█") == 5
    assert b.count("░") == 5


def test_status_str_format():
    """status_str() contains a bar, percentage, and token counts."""
    budget = TokenBudget(10000)
    budget.used = 2500
    s = budget.status_str()
    assert "%" in s
    assert "/" in s
    # Should contain bar characters
    assert "█" in s or "░" in s


def test_token_budget_configurable():
    """TokenBudget(50_000) has budget=50000."""
    budget = TokenBudget(50_000)
    assert budget.budget == 50_000


# ── Threshold tests ────────────────────────────────────────────────────────────


def test_warn_threshold_prints_warning(monkeypatch, mock_cfg):
    """At 82% usage, check_token_thresholds prints a yellow warning."""
    printed = []

    class _FakeConsole:
        def print(self, msg, *args, **kwargs):
            printed.append(msg)

        def input(self, *args, **kwargs):
            return ""

    monkeypatch.setattr(clod, "console", _FakeConsole())

    budget = TokenBudget(10000)
    budget.used = 8200  # 82% — past TOKEN_WARN=0.80, below TOKEN_OFFER=0.95

    session_state = {
        "model": "qwen2.5-coder:14b",
        "pipeline": None,
        "tools_on": False,
        "system": None,
        "cfg": mock_cfg,
        "budget": budget,
        "offline": False,
    }

    check_token_thresholds(budget, session_state)

    assert len(printed) >= 1
    # The warning message should contain yellow markup
    assert any("yellow" in str(msg) for msg in printed)
    # offline should NOT have been set
    assert session_state["offline"] is False


def test_offer_threshold_prompts_offline(monkeypatch, mock_cfg):
    """At 96% usage, user is prompted; answering 'y' sets offline=True."""

    class _FakeConsole:
        def print(self, *args, **kwargs):
            pass

        def input(self, *args, **kwargs):
            return "y"

    monkeypatch.setattr(clod, "console", _FakeConsole())

    budget = TokenBudget(10000)
    budget.used = 9600  # 96%

    session_state = {
        "model": "qwen2.5-coder:14b",
        "pipeline": None,
        "tools_on": False,
        "system": None,
        "cfg": mock_cfg,
        "budget": budget,
        "offline": False,
    }

    check_token_thresholds(budget, session_state)

    assert session_state["offline"] is True


def test_limit_threshold_forces_offline(mock_cfg):
    """At 100% usage, offline becomes True without any prompt."""
    printed = []

    import clod as _clod

    original_console = _clod.console

    class _FakeConsole:
        def print(self, *args, **kwargs):
            printed.append(args)

        def input(self, *args, **kwargs):
            # Should never be called at TOKEN_LIMIT
            raise AssertionError("input() should not be called at TOKEN_LIMIT")

    _clod.console = _FakeConsole()
    try:
        budget = TokenBudget(10000)
        budget.used = 10000  # exactly 100%

        session_state = {
            "model": "qwen2.5-coder:14b",
            "pipeline": None,
            "tools_on": False,
            "system": None,
            "cfg": mock_cfg,
            "budget": budget,
            "offline": False,
        }

        check_token_thresholds(budget, session_state)

        assert session_state["offline"] is True
    finally:
        _clod.console = original_console
