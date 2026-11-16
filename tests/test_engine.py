"""The answer keys in data/expected_*.csv were written by hand when the data
was generated, so these tests independently verify the engine catches every
planted breach with no false positives."""

from pathlib import Path

import pandas as pd
import pytest

from compliance.db import Dataset
from compliance.engine import pretrade_check, run_pretrade, scan

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def data():
    return Dataset.load(DATA)


def keyset(df):
    return set(map(tuple, df[["portfolio_id", "rule_id", "item"]].astype(str).values))


def test_catches_all_planted_breaches_with_no_false_positives(data):
    expected = keyset(pd.read_csv(DATA / "expected_breaches.csv"))
    found = keyset(scan(data))
    assert found - expected == set(), f"False positives: {found - expected}"
    assert expected - found == set(), f"Missed breaches: {expected - found}"


def test_price_drift_creates_breach_without_any_trade(data):
    base = keyset(pd.read_csv(DATA / "expected_breaches.csv"))
    drift = keyset(pd.read_csv(DATA / "expected_drift_breaches.csv"))
    shocked = data.with_prices(pd.read_csv(DATA / "prices_shock.csv"))
    assert keyset(scan(shocked)) == base | drift


def test_pretrade_decisions_match_expected(data):
    expected = pd.read_csv(DATA / "expected_trade_decisions.csv").set_index("trade_id")["decision"]
    results = run_pretrade(data, pd.read_csv(DATA / "proposed_trades.csv")).set_index("trade_id")
    for tid, decision in expected.items():
        assert results.loc[tid, "decision"] == decision, f"{tid}: {results.loc[tid, 'reasons']}"


def test_exactly_at_limit_is_not_a_breach(data):
    # P3 holds Microsoft at the 5% limit (floored just under); P4 holds a BBB bond
    # against a BBB minimum. Neither should be flagged.
    items = set(scan(data)["item"])
    assert "Microsoft Corp." not in items
    assert "VZ_B" not in items


def test_issuer_limit_aggregates_stock_and_bonds(data):
    b = scan(data)
    apple = b[(b["portfolio_id"] == "P2") & (b["rule_id"] == "R04")]
    assert apple["item"].tolist() == ["Apple Inc."]
    assert apple["actual"].iloc[0] == pytest.approx(0.055, abs=0.001)


def test_treasuries_exempt_from_issuer_limit(data):
    # P2 holds 43% in US Treasuries -- must not be flagged as issuer concentration
    assert "US Treasury" not in set(scan(data)["item"])


def test_original_holdings_unchanged_after_pretrade(data):
    before = data.holdings.copy()
    pretrade_check(data, dict(trade_id="X", portfolio_id="P1", security_id="AAPL",
                              side="BUY", quantity=100))
    pd.testing.assert_frame_equal(before, data.holdings)
