# Portfolio Guideline Compliance Checker

A rules-based engine that checks investment portfolios against their client and
prospectus guidelines, both **before a trade** (pre-trade) and **every day after
markets move** (post-trade), and produces an Excel breach report.

Built with Python, pandas, SQL (SQLite), and openpyxl.

## Why

Funds and client accounts have to stay inside their investment guidelines: issuer
concentration limits, sector caps, exclusion lists, credit quality minimums, and
cash levels for redemptions. A fund can fall out of compliance in two ways:

1. **A trade** pushes it over a limit, so trades are checked *before* they execute.
2. **Market movement** changes position weights with no trade at all, so every
   portfolio is re-scanned daily.

This project automates both checks.

## Features

| Rule type | What it checks | Example |
|---|---|---|
| `MAX_ISSUER_WEIGHT` | No issuer above X% of NAV. **Aggregates stock and bonds of the same issuer.** US Treasuries exempt. | Apple stock 3.0% + Apple bond 2.5% = 5.5% > 5% |
| `MAX_SECTOR_WEIGHT` | One sector (or `*` = every sector) capped at X% | Technology 28% > 25% |
| `RESTRICTED_LIST` | No holdings from issuers on an exclusion list. Matches by issuer, so bonds are caught too. | Exxon bond in an ESG fund |
| `MIN_CREDIT_RATING` | Bonds must be rated at or above a minimum (unrated bonds fail) | Ford bond rated BB, minimum BBB |
| `MIN_CASH_WEIGHT` | Keep at least X% in cash for redemptions | Cash 1.0% < 2% |

- **Guidelines are data, not code.** Each fund's rules live in `data/guidelines.csv`.
  Adding a client rule means adding a row. A new rule *type* is one SQL function
  registered in `compliance/rules.py`.
- **Pre-trade logic.** A trade is **BLOCKED** if it creates a new breach, worsens an
  existing one, oversells a position, or overdraws cash. A trade that *reduces* an
  existing breach is **APPROVED**, so you never block the trade that fixes the problem.
- **Severity levels.** *Hard* breaches (prospectus/regulatory) vs. *Soft* (internal targets).
- **Excel report** with a color-coded summary, breach detail, pre-trade decisions,
  and full holdings with weights.

## Quick start

```bash
pip install -r requirements.txt
python data/generate_data.py      # build the sample data set
python main.py                    # daily scan + pre-trade checks -> reports/compliance_report.xlsx
python -m pytest -q               # run the test suite
```

Other commands:

```bash
python main.py scan                                  # post-trade scan only
python main.py scan --prices data/prices_shock.csv   # re-scan after a price move
python main.py pretrade --trades data/proposed_trades.csv
```

## Sample output

```
POST-TRADE SCAN: 7 breach(es)
  [Hard] P1 R01  No issuer above 5% of NAV  ->  NVIDIA Corp.: 6.50% (limit 5.00%)
  [Hard] P2 R04  No issuer above 5% of NAV (Treasuries exempt)  ->  Apple Inc.: 5.50% (limit 5.00%)
  [Hard] P2 R06  Bonds must be investment grade (BBB or better)  ->  F_B: BB (limit BBB)
  [Hard] P3 R09  No tobacco issuers  ->  Altria Group Inc.: 1.50% (limit 0.00%)
  [Hard] P3 R10  No fossil fuel issuers  ->  Exxon Mobil Corp.: 2.00% (limit 0.00%)
  [Hard] P4 R14  No sector above 25% of NAV  ->  Technology: 28.00% (limit 25.00%)
  [Soft] P4 R16  Hold at least 2% cash for redemptions  ->  Cash: 1.00% (limit 2.00%)

PRE-TRADE CHECKS: 8 proposed trade(s)
  T1 P1 BUY  AAPL   -> BLOCKED   New breach: No issuer above 5% of NAV (Apple Inc.: 5.40%); ...
  T2 P3 BUY  PM     -> BLOCKED   New breach: No tobacco issuers (Philip Morris International: 0.25%)
  T3 P3 BUY  GOOGL  -> APPROVED  No new breaches; existing breaches in this fund are unchanged
  T4 P2 BUY  CCL_B  -> BLOCKED   New breach: Bonds must be investment grade (BBB or better) (CCL_B: B)
  T5 P4 SELL NVDA   -> APPROVED  Improves compliance; resolves 1 breach(es): Cash; reduces 1: Technology 28.00% -> 26.50%
  T6 P4 BUY  ORCL   -> BLOCKED   Worsens breach: No sector above 25% of NAV (Technology: 28.00% -> 28.50%); ...
  T7 P1 SELL MSFT   -> BLOCKED   Insufficient holdings: selling 24,390 but fund holds 10,975
  T8 P2 BUY  UST10  -> BLOCKED   Insufficient cash: trade costs $9,999,917, fund has $4,001,259
```

## Testing approach

The sample data plants **7 known breaches** across 4 portfolios, plus deliberate
**near-misses** (a 4.9% position against a 5% limit, a position exactly at its limit,
a BBB bond against a BBB minimum, and 2.1% cash against a 2% minimum).

The answer keys (`data/expected_*.csv`) are written by hand in the generator, not
produced by the engine, so the tests independently verify:

- every planted breach is caught, with **no false positives**
- values exactly at a limit are not flagged
- issuer limits aggregate across stock and bonds
- Treasuries are exempt from issuer limits
- an 8% price move creates a new breach with no trades (drift detection)
- all 8 pre-trade decisions match the expected outcome
- pre-trade simulation never modifies the real holdings

## Project structure

```
compliance/
  db.py        loads CSVs into SQLite; positions / NAV / weights views
  rules.py     one SQL query per rule type
  engine.py    post-trade scan, pre-trade simulation, summaries
  report.py    Excel report (openpyxl)
data/
  generate_data.py           builds the sample data and answer keys
  securities.csv             security master: issuer, sector, asset class, rating, price
  portfolios.csv, holdings.csv
  guidelines.csv             each fund's rules (data-driven)
  restricted_list.csv        exclusion lists (TOBACCO, FOSSIL_FUELS)
  proposed_trades.csv        trades for the pre-trade check
  prices_shock.csv           price move for the drift scenario
  expected_*.csv             answer keys used by the tests
tests/test_engine.py
main.py
```

## Notes

All data is synthetic. Tickers are real companies, but prices, holdings, and
portfolios are illustrative. Ratings use a simplified scale (AAA to D, no +/-
notches). Because every check is plain SQL against the `weights` view, the engine
would move to MySQL or another production database with minimal changes.
