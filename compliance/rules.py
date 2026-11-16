"""Guideline checks. Each rule type is one SQL query.

Every check returns a list of breach dicts with the same fields:
    item     -- what breached (an issuer, sector, security, or "Cash")
    actual   -- the measured value (a weight, or a rating)
    limit    -- the guideline limit
    excess   -- how far past the limit, always positive; bigger = worse.
                Used by the pre-trade check to tell if a trade makes an
                existing breach worse.

To add a new rule type: write a function here and register it in RULE_CHECKS.
Nothing else in the engine needs to change.
"""

TOLERANCE = 1e-9  # ignore floating-point noise at exactly-on-the-limit values


def max_issuer_weight(con, pid, rule):
    # Aggregates across ALL of an issuer's securities (stock + bonds).
    # US Government debt is exempt from issuer concentration limits.
    rows = con.execute(
        """
        SELECT issuer, SUM(weight) AS w
        FROM weights
        WHERE portfolio_id = ?
          AND asset_class != 'Cash'
          AND sector != 'Government'
        GROUP BY issuer
        HAVING w > ?
        ORDER BY w DESC
        """,
        (pid, rule["limit_value"] + TOLERANCE),
    ).fetchall()
    return [dict(item=i, actual=w, limit=rule["limit_value"], excess=w - rule["limit_value"])
            for i, w in rows]


def max_sector_weight(con, pid, rule):
    # parameter = a sector name, or "*" to cap every sector.
    # Cash and Government are not counted as sectors.
    rows = con.execute(
        """
        SELECT sector, SUM(weight) AS w
        FROM weights
        WHERE portfolio_id = ?
          AND sector NOT IN ('Cash', 'Government')
          AND (? = '*' OR sector = ?)
        GROUP BY sector
        HAVING w > ?
        ORDER BY w DESC
        """,
        (pid, rule["parameter"], rule["parameter"], rule["limit_value"] + TOLERANCE),
    ).fetchall()
    return [dict(item=s, actual=w, limit=rule["limit_value"], excess=w - rule["limit_value"])
            for s, w in rows]


def restricted_list(con, pid, rule):
    # Matches on issuer, so a restricted company's bonds are caught too.
    rows = con.execute(
        """
        SELECT w.issuer, SUM(w.weight) AS w
        FROM weights w
        JOIN restricted_list r ON r.issuer = w.issuer
        WHERE w.portfolio_id = ?
          AND r.list_name = ?
          AND w.quantity > 0
        GROUP BY w.issuer
        """,
        (pid, rule["parameter"]),
    ).fetchall()
    return [dict(item=i, actual=w, limit=0.0, excess=w) for i, w in rows]


def min_credit_rating(con, pid, rule):
    rows = con.execute(
        """
        SELECT w.security_id, w.rating, w.weight
        FROM weights w
        JOIN rating_scale rs ON rs.rating = w.rating
        WHERE w.portfolio_id = ?
          AND w.asset_class = 'Bond'
          AND w.quantity > 0
          AND rs.rank > (SELECT rank FROM rating_scale WHERE rating = ?)
        """,
        (pid, rule["parameter"]),
    ).fetchall()
    # Unrated bonds also fail an investment-grade guideline.
    unrated = con.execute(
        """
        SELECT security_id, 'NR', weight FROM weights
        WHERE portfolio_id = ? AND asset_class = 'Bond' AND quantity > 0
          AND (rating IS NULL OR rating NOT IN (SELECT rating FROM rating_scale))
        """,
        (pid,),
    ).fetchall()
    return [dict(item=sid, actual=rating, limit=rule["parameter"], excess=w)
            for sid, rating, w in rows + unrated]


def min_cash_weight(con, pid, rule):
    (w,) = con.execute(
        "SELECT COALESCE(SUM(weight), 0) FROM weights "
        "WHERE portfolio_id = ? AND asset_class = 'Cash'",
        (pid,),
    ).fetchone()
    if w < rule["limit_value"] - TOLERANCE:
        return [dict(item="Cash", actual=w, limit=rule["limit_value"],
                     excess=rule["limit_value"] - w)]
    return []


RULE_CHECKS = {
    "MAX_ISSUER_WEIGHT": max_issuer_weight,
    "MAX_SECTOR_WEIGHT": max_sector_weight,
    "RESTRICTED_LIST": restricted_list,
    "MIN_CREDIT_RATING": min_credit_rating,
    "MIN_CASH_WEIGHT": min_cash_weight,
}
