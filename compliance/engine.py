"""Post-trade scans and pre-trade checks."""

import pandas as pd

from .db import Dataset
from .rules import RULE_CHECKS

BREACH_COLUMNS = ["portfolio_id", "portfolio_name", "rule_id", "rule_type", "severity",
                  "description", "item", "actual", "limit", "excess"]


def scan(data: Dataset, portfolio_ids=None) -> pd.DataFrame:
    """Check every guideline for every portfolio. Returns one row per breach."""
    con = data.connect()
    names = dict(zip(data.portfolios["portfolio_id"], data.portfolios["name"]))
    breaches = []
    for rule in data.guidelines.to_dict("records"):
        pid = rule["portfolio_id"]
        if portfolio_ids is not None and pid not in portfolio_ids:
            continue
        check = RULE_CHECKS.get(rule["rule_type"])
        if check is None:
            raise ValueError(f"Unknown rule type {rule['rule_type']} in {rule['rule_id']}")
        for b in check(con, pid, rule):
            breaches.append(dict(portfolio_id=pid, portfolio_name=names.get(pid, pid),
                                 rule_id=rule["rule_id"], rule_type=rule["rule_type"],
                                 severity=rule["severity"], description=rule["description"],
                                 **b))
    con.close()
    return pd.DataFrame(breaches, columns=BREACH_COLUMNS)


def portfolio_summary(data: Dataset, breaches: pd.DataFrame) -> pd.DataFrame:
    con = data.connect()
    nav = pd.read_sql("SELECT portfolio_id, nav FROM nav", con)
    cash = pd.read_sql(
        "SELECT portfolio_id, SUM(weight) AS cash_weight FROM weights "
        "WHERE asset_class = 'Cash' GROUP BY portfolio_id", con)
    con.close()
    df = data.portfolios.merge(nav, on="portfolio_id").merge(cash, on="portfolio_id", how="left")
    rules = data.guidelines.groupby("portfolio_id").size().rename("rules_checked")
    df = df.merge(rules, on="portfolio_id", how="left")
    for sev in ["Hard", "Soft"]:
        counts = breaches[breaches["severity"] == sev].groupby("portfolio_id").size()
        df[f"{sev.lower()}_breaches"] = df["portfolio_id"].map(counts).fillna(0).astype(int)
    df["status"] = df.apply(
        lambda r: "BREACH" if r["hard_breaches"] else ("WARNING" if r["soft_breaches"] else "COMPLIANT"),
        axis=1)
    return df


def holdings_detail(data: Dataset) -> pd.DataFrame:
    con = data.connect()
    df = pd.read_sql(
        "SELECT portfolio_id, security_id, name, issuer, sector, asset_class, rating, "
        "quantity, price, market_value, weight FROM weights "
        "ORDER BY portfolio_id, weight DESC", con)
    con.close()
    return df


# ---------------------------------------------------------------------------
# Pre-trade
# ---------------------------------------------------------------------------
def _apply_trade(holdings: pd.DataFrame, trade: dict, price: float) -> pd.DataFrame:
    h = holdings.copy()
    pid, sid, qty = trade["portfolio_id"], trade["security_id"], float(trade["quantity"])
    signed = qty if trade["side"].upper() == "BUY" else -qty

    mask = (h["portfolio_id"] == pid) & (h["security_id"] == sid)
    if mask.any():
        h.loc[mask, "quantity"] = h.loc[mask, "quantity"].astype(float) + signed
    else:
        h = pd.concat([h, pd.DataFrame([{"portfolio_id": pid, "security_id": sid,
                                         "quantity": signed}])], ignore_index=True)
    cash = (h["portfolio_id"] == pid) & (h["security_id"] == "CASH")
    h.loc[cash, "quantity"] = h.loc[cash, "quantity"].astype(float) - signed * price
    return h


def _key(b):
    return (b["rule_id"], b["item"])


def pretrade_check(data: Dataset, trade: dict) -> dict:
    """Simulate a trade and decide APPROVED / BLOCKED.

    A trade is BLOCKED if it would create a new breach, make an existing
    breach worse, oversell a position, or overdraw cash. A trade that only
    reduces an existing breach is APPROVED -- you should never block the
    trade that fixes the problem.
    """
    pid, sid, side = trade["portfolio_id"], trade["security_id"], trade["side"].upper()
    qty = float(trade["quantity"])
    sec = data.securities.set_index("security_id")
    result = dict(trade_id=trade["trade_id"], portfolio_id=pid, security_id=sid, side=side,
                  quantity=qty)

    if sid not in sec.index:
        return {**result, "notional": None, "decision": "BLOCKED",
                "reasons": f"Unknown security {sid}"}
    price = float(sec.loc[sid, "price"])
    result["notional"] = qty * price

    h = data.holdings
    held = h[(h["portfolio_id"] == pid) & (h["security_id"] == sid)]["quantity"].sum()
    cash = h[(h["portfolio_id"] == pid) & (h["security_id"] == "CASH")]["quantity"].sum()

    reasons = []
    if side == "SELL" and qty > held:
        reasons.append(f"Insufficient holdings: selling {qty:,.0f} but fund holds {held:,.0f}")
    if side == "BUY" and qty * price > cash:
        reasons.append(f"Insufficient cash: trade costs ${qty * price:,.0f}, "
                       f"fund has ${cash:,.0f}")
    if reasons:
        return {**result, "decision": "BLOCKED", "reasons": "; ".join(reasons)}

    before = {_key(b): b for b in scan(data, [pid]).to_dict("records")}
    after_data = data.with_holdings(_apply_trade(h, trade, price))
    after = scan(after_data, [pid]).to_dict("records")

    for b in after:
        prev = before.get(_key(b))
        if prev is None:
            reasons.append(f"New breach: {b['description']} ({b['item']}: {_fmt(b)})")
        elif b["excess"] > prev["excess"] + 1e-9:
            reasons.append(f"Worsens breach: {b['description']} ({b['item']}: "
                           f"{_fmt(prev)} -> {_fmt(b)})")

    decision = "BLOCKED" if reasons else "APPROVED"
    if not reasons:
        after_keys = {_key(b): b for b in after}
        resolved = [k for k in before if k not in after_keys]
        reduced = [k for k, b in after_keys.items() if b["excess"] < before[k]["excess"] - 1e-9]
        if not before:
            reasons = ["Within all guidelines"]
        elif resolved or reduced:
            parts = []
            if resolved:
                parts.append(f"resolves {len(resolved)} breach(es): "
                             + ", ".join(before[k]["item"] for k in resolved))
            if reduced:
                parts.append(f"reduces {len(reduced)}: " + ", ".join(
                    f"{after_keys[k]['item']} {_fmt(before[k])} -> {_fmt(after_keys[k])}"
                    for k in reduced))
            reasons = ["Improves compliance; " + "; ".join(parts)]
        else:
            reasons = ["No new breaches; existing breaches in this fund are unchanged"]
    return {**result, "decision": decision, "reasons": "; ".join(reasons)}


def _fmt(b):
    return b["actual"] if isinstance(b["actual"], str) else f"{b['actual']:.2%}"


def run_pretrade(data: Dataset, trades: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([pretrade_check(data, t) for t in trades.to_dict("records")])
