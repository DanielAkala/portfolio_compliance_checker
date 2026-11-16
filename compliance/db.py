"""Loads the CSV data set into an in-memory SQLite database.

Every check in rules.py is a SQL query against the views defined here, so the
same logic would run on MySQL or any other SQL database with minor changes.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# Lower rank = better credit quality.
RATING_SCALE = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"]

VIEWS = """
CREATE VIEW positions AS
SELECT h.portfolio_id,
       h.security_id,
       s.name,
       s.issuer,
       s.sector,
       s.asset_class,
       NULLIF(s.rating, '') AS rating,
       h.quantity,
       s.price,
       h.quantity * s.price AS market_value
FROM holdings h
JOIN securities s ON s.security_id = h.security_id;

CREATE VIEW nav AS
SELECT portfolio_id, SUM(market_value) AS nav
FROM positions
GROUP BY portfolio_id;

CREATE VIEW weights AS
SELECT p.*, p.market_value / n.nav AS weight
FROM positions p
JOIN nav n ON n.portfolio_id = p.portfolio_id;
"""


@dataclass
class Dataset:
    securities: pd.DataFrame
    portfolios: pd.DataFrame
    holdings: pd.DataFrame
    guidelines: pd.DataFrame
    restricted: pd.DataFrame

    @classmethod
    def load(cls, data_dir):
        d = Path(data_dir)
        read = lambda name: pd.read_csv(d / name, keep_default_na=False)
        guidelines = read("guidelines.csv")
        guidelines["limit_value"] = pd.to_numeric(guidelines["limit_value"], errors="coerce")
        return cls(
            securities=read("securities.csv"),
            portfolios=read("portfolios.csv"),
            holdings=read("holdings.csv"),
            guidelines=guidelines,
            restricted=read("restricted_list.csv"),
        )

    def with_prices(self, prices: pd.DataFrame) -> "Dataset":
        """Return a copy of the data set with some prices overridden."""
        sec = self.securities.copy()
        new = dict(zip(prices["security_id"], prices["price"]))
        sec["price"] = [new.get(sid, p) for sid, p in zip(sec["security_id"], sec["price"])]
        return Dataset(sec, self.portfolios, self.holdings, self.guidelines, self.restricted)

    def with_holdings(self, holdings: pd.DataFrame) -> "Dataset":
        return Dataset(self.securities, self.portfolios, holdings, self.guidelines, self.restricted)

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(":memory:")
        self.securities.to_sql("securities", con, index=False)
        self.portfolios.to_sql("portfolios", con, index=False)
        self.holdings.to_sql("holdings", con, index=False)
        self.guidelines.to_sql("guidelines", con, index=False)
        self.restricted.to_sql("restricted_list", con, index=False)
        pd.DataFrame({"rating": RATING_SCALE, "rank": range(len(RATING_SCALE))}).to_sql(
            "rating_scale", con, index=False)
        con.executescript(VIEWS)
        return con
