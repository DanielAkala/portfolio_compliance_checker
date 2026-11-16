"""Writes the Excel compliance report."""

from datetime import datetime

import pandas as pd
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(bold=True, color="FFFFFF")
# Conditional formatting in Excel reads bgColor, regular cells read fgColor,
# so set both or the highlight silently disappears.
def _solid(color):
    return PatternFill(fill_type="solid", start_color=color, end_color=color)


RED = _solid("F8CBAD")
AMBER = _solid("FFE699")
GREEN = _solid("C6EFCE")


def _display(v):
    return v if isinstance(v, str) else round(float(v), 6)


def _format_sheet(ws, df, pct_cols=(), money_cols=(), qty_cols=(), widths=None):
    for c in ws[1]:
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    cols = list(df.columns)
    for i, name in enumerate(cols, start=1):
        letter = get_column_letter(i)
        fmt = ("0.00%" if name in pct_cols else "$#,##0" if name in money_cols
               else "#,##0" if name in qty_cols else None)
        if fmt:
            for cell in ws[letter][1:]:
                if isinstance(cell.value, (int, float)):
                    cell.number_format = fmt
        width = (widths or {}).get(name) or min(max(len(str(name)), *(len(str(v)) for v in df[name]), 8) + 2, 60)
        ws.column_dimensions[letter].width = width


def _highlight(ws, df, column, colors):
    col = get_column_letter(list(df.columns).index(column) + 1)
    rng = f"A2:{get_column_letter(len(df.columns))}{len(df) + 1}"
    for value, fill in colors.items():
        ws.conditional_formatting.add(rng, FormulaRule(formula=[f'${col}2="{value}"'], fill=fill))


def write_report(path, summary, breaches, holdings, pretrade=None, as_of=None):
    as_of = as_of or datetime.now().strftime("%Y-%m-%d %H:%M")

    summary_out = summary[["portfolio_id", "name", "strategy", "nav", "cash_weight",
                           "rules_checked", "hard_breaches", "soft_breaches", "status"]].rename(
        columns={"portfolio_id": "Portfolio", "name": "Fund", "strategy": "Strategy",
                 "nav": "NAV", "cash_weight": "Cash %", "rules_checked": "Rules Checked",
                 "hard_breaches": "Hard Breaches", "soft_breaches": "Soft Breaches",
                 "status": "Status"})

    breaches_out = breaches.assign(
        actual=breaches["actual"].map(_display), limit=breaches["limit"].map(_display),
        excess=breaches["excess"].map(_display),
    )[["portfolio_id", "portfolio_name", "rule_id", "severity", "rule_type", "description",
       "item", "actual", "limit", "excess"]].rename(
        columns={"portfolio_id": "Portfolio", "portfolio_name": "Fund", "rule_id": "Rule",
                 "severity": "Severity", "rule_type": "Rule Type", "description": "Guideline",
                 "item": "Breached Item", "actual": "Actual", "limit": "Limit",
                 "excess": "Excess"})

    holdings_out = holdings.rename(columns={
        "portfolio_id": "Portfolio", "security_id": "Security", "name": "Name",
        "issuer": "Issuer", "sector": "Sector", "asset_class": "Asset Class",
        "rating": "Rating", "quantity": "Quantity", "price": "Price",
        "market_value": "Market Value", "weight": "Weight"})

    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        summary_out.to_excel(xw, sheet_name="Summary", index=False, startrow=3)
        ws = xw.sheets["Summary"]
        ws["A1"] = "Portfolio Guideline Compliance Report"
        ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = (f"As of {as_of}  |  {len(breaches)} breach(es) across "
                    f"{breaches['portfolio_id'].nunique()} of {len(summary)} portfolios")
        # header row is row 4 here
        for c in ws[4]:
            c.fill, c.font = HEADER_FILL, HEADER_FONT
        for row in ws.iter_rows(min_row=5, max_row=4 + len(summary_out)):
            row[3].number_format = "$#,##0"
            row[4].number_format = "0.00%"
            status = row[8].value
            row[8].fill = RED if status == "BREACH" else AMBER if status == "WARNING" else GREEN
            row[8].font = Font(bold=True)
        for i, w in enumerate([10, 26, 44, 16, 10, 14, 14, 14, 13], start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A5"

        breaches_out.to_excel(xw, sheet_name="Breaches", index=False)
        ws = xw.sheets["Breaches"]
        _format_sheet(ws, breaches_out, widths={"Guideline": 46, "Fund": 26})
        pct_types = {"MAX_ISSUER_WEIGHT", "MAX_SECTOR_WEIGHT", "MIN_CASH_WEIGHT", "RESTRICTED_LIST"}
        for r, rule_type in enumerate(breaches["rule_type"], start=2):
            for col in ("H", "I", "J"):
                cell = ws[f"{col}{r}"]
                if isinstance(cell.value, (int, float)) and (rule_type in pct_types or col == "J"):
                    cell.number_format = "0.00%"
        if len(breaches_out):
            _highlight(ws, breaches_out, "Severity", {"Hard": RED, "Soft": AMBER})

        if pretrade is not None:
            pre = pretrade.rename(columns={
                "trade_id": "Trade", "portfolio_id": "Portfolio", "security_id": "Security",
                "side": "Side", "quantity": "Quantity", "notional": "Notional",
                "decision": "Decision", "reasons": "Reason"})
            pre.to_excel(xw, sheet_name="Pre-Trade Checks", index=False)
            ws = xw.sheets["Pre-Trade Checks"]
            _format_sheet(ws, pre, money_cols={"Notional"}, qty_cols={"Quantity"},
                          widths={"Reason": 90})
            for row in ws.iter_rows(min_row=2):
                row[-1].alignment = Alignment(wrap_text=True, vertical="top")
            _highlight(ws, pre, "Decision", {"BLOCKED": RED, "APPROVED": GREEN})

        holdings_out.to_excel(xw, sheet_name="Holdings", index=False)
        _format_sheet(xw.sheets["Holdings"], holdings_out, pct_cols={"Weight"},
                      money_cols={"Market Value"}, qty_cols={"Quantity"},
                      widths={"Name": 28, "Issuer": 28})
    return path
