"""Portfolio Guideline Compliance Checker -- command line entry point.

Examples
  python main.py                                   # daily scan + pre-trade checks
  python main.py scan                              # daily post-trade scan only
  python main.py scan --prices data/prices_shock.csv   # re-scan after a price move
  python main.py pretrade --trades data/proposed_trades.csv
"""

import argparse
from pathlib import Path

import pandas as pd

from compliance.db import Dataset
from compliance.engine import holdings_detail, portfolio_summary, run_pretrade, scan
from compliance.report import write_report

ROOT = Path(__file__).resolve().parent


def print_breaches(breaches):
    if breaches.empty:
        print("  No breaches. All portfolios compliant.")
        return
    for b in breaches.to_dict("records"):
        actual = b["actual"] if isinstance(b["actual"], str) else f"{b['actual']:.2%}"
        limit = b["limit"] if isinstance(b["limit"], str) else f"{b['limit']:.2%}"
        print(f"  [{b['severity']:4}] {b['portfolio_id']} {b['rule_id']}  {b['description']}"
              f"  ->  {b['item']}: {actual} (limit {limit})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="all", choices=["all", "scan", "pretrade"])
    ap.add_argument("--data", default=ROOT / "data", help="folder with the CSV data set")
    ap.add_argument("--prices", help="CSV of price overrides (security_id, price)")
    ap.add_argument("--trades", default=ROOT / "data" / "proposed_trades.csv")
    ap.add_argument("--out", default=ROOT / "reports" / "compliance_report.xlsx")
    args = ap.parse_args()

    data = Dataset.load(args.data)
    if args.prices:
        data = data.with_prices(pd.read_csv(args.prices))
        print(f"Applied price overrides from {args.prices}")

    breaches = scan(data)
    pretrade = None

    if args.command in ("all", "scan"):
        print(f"\nPOST-TRADE SCAN: {len(breaches)} breach(es)")
        print_breaches(breaches)

    if args.command in ("all", "pretrade"):
        pretrade = run_pretrade(data, pd.read_csv(args.trades))
        print(f"\nPRE-TRADE CHECKS: {len(pretrade)} proposed trade(s)")
        for t in pretrade.to_dict("records"):
            print(f"  {t['trade_id']} {t['portfolio_id']} {t['side']:4} {t['security_id']:6} "
                  f"-> {t['decision']:8}  {t['reasons']}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_report(out, portfolio_summary(data, breaches), breaches, holdings_detail(data), pretrade)
    print(f"\nExcel report written to {out}")


if __name__ == "__main__":
    main()
