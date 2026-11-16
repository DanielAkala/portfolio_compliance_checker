"""
Generates the sample data set for the Portfolio Guideline Compliance Checker.

All data is synthetic: tickers are real companies, but prices, holdings and
portfolios are illustrative only.

The portfolios are built from target weights so that a known set of guideline
breaches is planted on purpose. The answer keys (expected_breaches.csv and
expected_trade_decisions.csv) are written by hand here -- NOT produced by the
engine -- so the tests are an independent check that the engine catches every
planted breach with no false positives.

Run:  python data/generate_data.py
"""

import csv
import math
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
NAV = 100_000_000  # every portfolio starts at $100M

# ---------------------------------------------------------------------------
# Security master
# security_id, name, issuer, sector, asset_class, rating, price
# Bonds are priced per $100 face; quantity is in $100-face units.
# ---------------------------------------------------------------------------
SECURITIES = [
    # Technology
    ("AAPL", "Apple Inc. Common", "Apple Inc.", "Technology", "Equity", "", 190.00),
    ("MSFT", "Microsoft Corp. Common", "Microsoft Corp.", "Technology", "Equity", "", 410.00),
    ("NVDA", "NVIDIA Corp. Common", "NVIDIA Corp.", "Technology", "Equity", "", 120.00),
    ("AVGO", "Broadcom Inc. Common", "Broadcom Inc.", "Technology", "Equity", "", 165.00),
    ("ORCL", "Oracle Corp. Common", "Oracle Corp.", "Technology", "Equity", "", 140.00),
    ("CRM", "Salesforce Inc. Common", "Salesforce Inc.", "Technology", "Equity", "", 290.00),
    ("ADBE", "Adobe Inc. Common", "Adobe Inc.", "Technology", "Equity", "", 520.00),
    ("CSCO", "Cisco Systems Common", "Cisco Systems Inc.", "Technology", "Equity", "", 58.00),
    # Communication Services
    ("GOOGL", "Alphabet Inc. Class A", "Alphabet Inc.", "Communication Services", "Equity", "", 170.00),
    ("META", "Meta Platforms Common", "Meta Platforms Inc.", "Communication Services", "Equity", "", 500.00),
    ("VZ", "Verizon Common", "Verizon Communications", "Communication Services", "Equity", "", 41.00),
    # Consumer Discretionary
    ("AMZN", "Amazon.com Common", "Amazon.com Inc.", "Consumer Discretionary", "Equity", "", 185.00),
    ("HD", "Home Depot Common", "The Home Depot Inc.", "Consumer Discretionary", "Equity", "", 360.00),
    ("NKE", "Nike Inc. Class B", "Nike Inc.", "Consumer Discretionary", "Equity", "", 80.00),
    # Health Care
    ("UNH", "UnitedHealth Common", "UnitedHealth Group", "Health Care", "Equity", "", 520.00),
    ("ABT", "Abbott Labs Common", "Abbott Laboratories", "Health Care", "Equity", "", 110.00),
    ("JNJ", "Johnson & Johnson Common", "Johnson & Johnson", "Health Care", "Equity", "", 155.00),
    ("PFE", "Pfizer Common", "Pfizer Inc.", "Health Care", "Equity", "", 28.00),
    # Financials
    ("V", "Visa Inc. Class A", "Visa Inc.", "Financials", "Equity", "", 280.00),
    ("JPM", "JPMorgan Chase Common", "JPMorgan Chase & Co.", "Financials", "Equity", "", 200.00),
    ("GS", "Goldman Sachs Common", "Goldman Sachs Group", "Financials", "Equity", "", 450.00),
    ("BAC", "Bank of America Common", "Bank of America Corp.", "Financials", "Equity", "", 38.00),
    # Industrials
    ("CAT", "Caterpillar Common", "Caterpillar Inc.", "Industrials", "Equity", "", 340.00),
    ("HON", "Honeywell Common", "Honeywell International", "Industrials", "Equity", "", 205.00),
    ("UNP", "Union Pacific Common", "Union Pacific Corp.", "Industrials", "Equity", "", 240.00),
    # Consumer Staples
    ("PG", "Procter & Gamble Common", "Procter & Gamble Co.", "Consumer Staples", "Equity", "", 165.00),
    ("KO", "Coca-Cola Common", "The Coca-Cola Co.", "Consumer Staples", "Equity", "", 62.00),
    ("MO", "Altria Group Common", "Altria Group Inc.", "Consumer Staples", "Equity", "", 50.00),
    ("PM", "Philip Morris Common", "Philip Morris International", "Consumer Staples", "Equity", "", 120.00),
    # Energy
    ("XOM", "Exxon Mobil Common", "Exxon Mobil Corp.", "Energy", "Equity", "", 115.00),
    ("CVX", "Chevron Common", "Chevron Corp.", "Energy", "Equity", "", 155.00),
    # Utilities
    ("NEE", "NextEra Energy Common", "NextEra Energy Inc.", "Utilities", "Equity", "", 72.00),
    ("DUK", "Duke Energy Common", "Duke Energy Corp.", "Utilities", "Equity", "", 105.00),
    # Bonds (issuer's sector; rating on simplified scale)
    ("UST10", "US Treasury 4.25% 2035", "US Treasury", "Government", "Bond", "AAA", 98.50),
    ("UST30", "US Treasury 4.50% 2055", "US Treasury", "Government", "Bond", "AAA", 96.75),
    ("MSFT_B", "Microsoft 3.70% 2046", "Microsoft Corp.", "Technology", "Bond", "AAA", 92.40),
    ("AAPL_B", "Apple 3.85% 2043", "Apple Inc.", "Technology", "Bond", "AA", 94.10),
    ("JPM_B", "JPMorgan 4.25% 2033", "JPMorgan Chase & Co.", "Financials", "Bond", "A", 97.20),
    ("VZ_B", "Verizon 4.40% 2034", "Verizon Communications", "Communication Services", "Bond", "BBB", 96.30),
    ("DUK_B", "Duke Energy 4.50% 2032", "Duke Energy Corp.", "Utilities", "Bond", "A", 98.10),
    ("PFE_B", "Pfizer 4.10% 2036", "Pfizer Inc.", "Health Care", "Bond", "A", 95.60),
    ("XOM_B", "Exxon Mobil 3.45% 2040", "Exxon Mobil Corp.", "Energy", "Bond", "AA", 88.90),
    ("F_B", "Ford Motor 6.10% 2032", "Ford Motor Co.", "Consumer Discretionary", "Bond", "BB", 99.80),
    ("CCL_B", "Carnival 6.00% 2029", "Carnival Corp.", "Consumer Discretionary", "Bond", "B", 98.40),
    # Cash
    ("CASH", "US Dollar Cash", "Cash", "Cash", "Cash", "", 1.00),
]
PRICE = {s[0]: s[6] for s in SECURITIES}

PORTFOLIOS = [
    ("P1", "Growth Equity Fund", "Large-cap growth equities"),
    ("P2", "Core Income Fund", "Investment-grade bonds plus dividend equities"),
    ("P3", "Sustainable Leaders Fund", "ESG equity fund with exclusion lists"),
    ("P4", "Balanced Fund", "Diversified mix of equities and bonds"),
]

# ---------------------------------------------------------------------------
# Target weights (% of NAV). Cash = whatever is left over.
# Comments mark planted breaches and deliberate near-misses.
# ---------------------------------------------------------------------------
TARGET_WEIGHTS = {
    "P1": {
        "NVDA": 6.5,   # PLANTED: issuer 6.5% > 5% limit
        "AAPL": 4.9,   # near-miss: just under 5%
        "MSFT": 4.5, "AVGO": 4.0, "ORCL": 3.0, "CRM": 3.0,        # Tech 25.9% (< 30%)
        "GOOGL": 4.5, "META": 4.5, "VZ": 2.0,
        "AMZN": 4.5, "HD": 4.0, "NKE": 3.0,
        "UNH": 4.5, "ABT": 3.5, "JNJ": 3.5, "PFE": 2.0,
        "V": 4.0, "JPM": 4.5, "GS": 3.0, "BAC": 2.5,
        "CAT": 4.5, "HON": 4.0, "UNP": 4.0,
        "PG": 4.0, "KO": 3.5,
        "NEE": 2.0,
        # cash ~2.1%  -> near-miss on 2% minimum
    },
    "P2": {
        "UST10": 30.0, "UST30": 13.0,     # Government: exempt from issuer limit
        "MSFT_B": 4.0, "JPM_B": 4.5, "VZ_B": 4.0, "DUK_B": 4.0, "PFE_B": 3.5,
        "AAPL_B": 2.5,
        "AAPL": 3.0,   # PLANTED: Apple equity 3.0% + bond 2.5% = 5.5% > 5%
        "F_B": 3.0,    # PLANTED: Ford bond rated BB, below BBB minimum
        "JNJ": 4.0, "PG": 4.0, "KO": 3.5,
        "BAC": 4.5, "GS": 4.0, "V": 4.5,  # Financials 17.5% (< 20%)
        # cash ~4%
    },
    "P3": {
        "MSFT": 5.0,   # boundary: exactly at 5% limit -> NOT a breach
        "AAPL": 4.5, "NVDA": 4.5, "CRM": 3.5, "ADBE": 3.5, "CSCO": 3.5,  # Tech 24.5% (< 25%)
        "UNH": 4.0, "ABT": 4.0, "JNJ": 4.0,
        "V": 4.0, "JPM": 4.0,
        "HON": 4.0, "UNP": 4.0,
        "NEE": 4.5, "DUK": 4.0,
        "AMZN": 4.0, "NKE": 3.0,
        "GOOGL": 4.0, "VZ": 3.0,
        "PG": 4.0, "KO": 3.0,
        "MO": 1.5,     # PLANTED: Altria is on the TOBACCO restricted list
        "XOM_B": 2.0,  # PLANTED: Exxon bond -- issuer on FOSSIL_FUELS list
        "UST10": 10.0,
        # cash ~4.5%
    },
    "P4": {
        # PLANTED: Technology 28% > 25% sector cap (no single name over 4%)
        "AAPL": 3.5, "MSFT": 3.5, "NVDA": 3.5, "AVGO": 3.5,
        "ORCL": 3.5, "CRM": 3.5, "ADBE": 3.5, "CSCO": 3.5,
        "UST10": 20.0,
        "JPM_B": 3.0, "DUK_B": 3.0,
        "VZ_B": 3.0,   # boundary: rated BBB, exactly the minimum -> NOT a breach
        "JNJ": 3.0, "UNH": 3.0, "PG": 3.0, "KO": 3.0,
        "V": 3.5, "GS": 3.0, "CAT": 3.0, "HON": 3.0,
        "AMZN": 3.5, "GOOGL": 3.5, "META": 3.5,
        "NEE": 3.5, "XOM": 3.5,
        # PLANTED: cash ~1% < 2% minimum
    },
}

# ---------------------------------------------------------------------------
# Investment guidelines -- stored as data, not code.
# rule_id, portfolio_id, rule_type, parameter, limit_value, severity, description
# ---------------------------------------------------------------------------
GUIDELINES = [
    ("R01", "P1", "MAX_ISSUER_WEIGHT", "", 0.05, "Hard", "No issuer above 5% of NAV"),
    ("R02", "P1", "MAX_SECTOR_WEIGHT", "*", 0.30, "Hard", "No sector above 30% of NAV"),
    ("R03", "P1", "MIN_CASH_WEIGHT", "", 0.02, "Soft", "Hold at least 2% cash for redemptions"),
    ("R04", "P2", "MAX_ISSUER_WEIGHT", "", 0.05, "Hard", "No issuer above 5% of NAV (Treasuries exempt)"),
    ("R05", "P2", "MAX_SECTOR_WEIGHT", "Financials", 0.20, "Hard", "Financials capped at 20% of NAV"),
    ("R06", "P2", "MIN_CREDIT_RATING", "BBB", None, "Hard", "Bonds must be investment grade (BBB or better)"),
    ("R07", "P2", "MIN_CASH_WEIGHT", "", 0.03, "Soft", "Hold at least 3% cash for redemptions"),
    ("R08", "P3", "MAX_ISSUER_WEIGHT", "", 0.05, "Hard", "No issuer above 5% of NAV"),
    ("R09", "P3", "RESTRICTED_LIST", "TOBACCO", None, "Hard", "No tobacco issuers"),
    ("R10", "P3", "RESTRICTED_LIST", "FOSSIL_FUELS", None, "Hard", "No fossil fuel issuers"),
    ("R11", "P3", "MAX_SECTOR_WEIGHT", "*", 0.25, "Hard", "No sector above 25% of NAV"),
    ("R12", "P3", "MIN_CASH_WEIGHT", "", 0.02, "Soft", "Hold at least 2% cash for redemptions"),
    ("R13", "P4", "MAX_ISSUER_WEIGHT", "", 0.04, "Hard", "No issuer above 4% of NAV (Treasuries exempt)"),
    ("R14", "P4", "MAX_SECTOR_WEIGHT", "*", 0.25, "Hard", "No sector above 25% of NAV"),
    ("R15", "P4", "MIN_CREDIT_RATING", "BBB", None, "Hard", "Bonds must be investment grade (BBB or better)"),
    ("R16", "P4", "MIN_CASH_WEIGHT", "", 0.02, "Soft", "Hold at least 2% cash for redemptions"),
]

RESTRICTED = [
    ("TOBACCO", "Altria Group Inc."),
    ("TOBACCO", "Philip Morris International"),
    ("FOSSIL_FUELS", "Exxon Mobil Corp."),
    ("FOSSIL_FUELS", "Chevron Corp."),
]

# ---------------------------------------------------------------------------
# Proposed trades for the pre-trade check: (trade_id, portfolio, security,
# side, approx dollar amount, expected decision, why)
# ---------------------------------------------------------------------------
TRADES = [
    ("T1", "P1", "AAPL", "BUY", 500_000, "BLOCKED", "Pushes Apple to ~5.4% (limit 5%) and cash below 2%"),
    ("T2", "P3", "PM", "BUY", 250_000, "BLOCKED", "Philip Morris is on the TOBACCO restricted list"),
    ("T3", "P3", "GOOGL", "BUY", 500_000, "APPROVED", "Stays inside every guideline"),
    ("T4", "P2", "CCL_B", "BUY", 1_000_000, "BLOCKED", "Carnival bond is rated B, below BBB minimum"),
    ("T5", "P4", "NVDA", "SELL", 1_500_000, "APPROVED", "Reduces the existing tech breach and fixes the cash shortfall"),
    ("T6", "P4", "ORCL", "BUY", 500_000, "BLOCKED", "Worsens the existing tech sector breach"),
    ("T7", "P1", "MSFT", "SELL", 10_000_000, "BLOCKED", "Sells more shares than the fund holds"),
    ("T8", "P2", "UST10", "BUY", 10_000_000, "BLOCKED", "Costs more than the fund's available cash"),
]

# Answer key for the baseline scan: (portfolio_id, rule_id, item)
EXPECTED_BREACHES = [
    ("P1", "R01", "NVIDIA Corp."),
    ("P2", "R04", "Apple Inc."),
    ("P2", "R06", "F_B"),
    ("P3", "R09", "Altria Group Inc."),
    ("P3", "R10", "Exxon Mobil Corp."),
    ("P4", "R14", "Technology"),
    ("P4", "R16", "Cash"),
]

# Price shock scenario: Microsoft rallies 8% overnight. With no trades at all,
# P3's Microsoft position drifts from exactly 5.0% to above the 5% limit.
PRICE_SHOCK = [("MSFT", round(PRICE["MSFT"] * 1.08, 2))]
EXPECTED_DRIFT_BREACHES = [("P3", "R08", "Microsoft Corp.")]


def write_csv(name, header, rows):
    with open(DATA_DIR / name, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def build_holdings():
    rows = []
    for pid, weights in TARGET_WEIGHTS.items():
        invested = 0.0
        for sid, pct in weights.items():
            # floor so a position never lands a hair above its target weight
            qty = math.floor(NAV * pct / 100 / PRICE[sid])
            invested += qty * PRICE[sid]
            rows.append((pid, sid, qty))
        cash = round(NAV - invested, 2)
        assert cash > 0, f"{pid} is over-invested"
        rows.append((pid, "CASH", cash))
    return rows


def main():
    write_csv("securities.csv",
              ["security_id", "name", "issuer", "sector", "asset_class", "rating", "price"],
              SECURITIES)
    write_csv("portfolios.csv", ["portfolio_id", "name", "strategy"], PORTFOLIOS)
    write_csv("holdings.csv", ["portfolio_id", "security_id", "quantity"], build_holdings())
    write_csv("guidelines.csv",
              ["rule_id", "portfolio_id", "rule_type", "parameter", "limit_value",
               "severity", "description"],
              [(r[0], r[1], r[2], r[3], "" if r[4] is None else r[4], r[5], r[6])
               for r in GUIDELINES])
    write_csv("restricted_list.csv", ["list_name", "issuer"], RESTRICTED)
    write_csv("proposed_trades.csv",
              ["trade_id", "portfolio_id", "security_id", "side", "quantity"],
              [(t[0], t[1], t[2], t[3], math.floor(t[4] / PRICE[t[2]])) for t in TRADES])
    write_csv("prices_shock.csv", ["security_id", "price"], PRICE_SHOCK)

    write_csv("expected_breaches.csv", ["portfolio_id", "rule_id", "item"], EXPECTED_BREACHES)
    write_csv("expected_drift_breaches.csv", ["portfolio_id", "rule_id", "item"],
              EXPECTED_DRIFT_BREACHES)
    write_csv("expected_trade_decisions.csv", ["trade_id", "decision", "why"],
              [(t[0], t[5], t[6]) for t in TRADES])
    print(f"Sample data written to {DATA_DIR}")


if __name__ == "__main__":
    main()
