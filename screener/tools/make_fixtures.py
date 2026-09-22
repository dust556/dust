#!/usr/bin/env python3
"""Generate the offline fixture set.

Each fixture is a synthetic company built to exercise one decision path in
the screen, so a test can assert an exact verdict and a regression in the
maths shows up immediately. The parameters below are the readable source of
truth; ``data/fixtures/*.json`` is generated output and should not be edited
by hand.

Run: ``python3 tools/make_fixtures.py``
"""

from __future__ import annotations

import datetime as dt
import json
import os
from typing import Dict, List, Optional

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "fixtures")

BASE_YEAR = 2020
YEARS = 6  # fiscal 2020..2025


def build_company(
    ticker: str,
    name: str,
    *,
    revenue_start: float,
    revenue_growth: float,
    margin_start: float,
    margin_step: float,
    opex_ratio: float,
    da_ratio: float,
    capex_ratio: float,
    equity_start: float,
    debt: float,
    cash: float,
    price: float,
    shares: float,
    insider_fraction: float,
    interest_rate: float = 0.06,
    tax_rate: float = 0.21,
    working_capital_ratio: float = 0.12,
    acquisitions_ratio: float = 0.0,
    exchange: str = "Nasdaq",
    quarters: bool = True,
    note: str = "",
) -> Dict:
    """Build one synthetic filer.

    ``margin_step`` is the annual change in gross margin (negative for a
    company whose margin is eroding); ``opex_ratio`` is operating expense as a
    share of revenue, which together with the margin sets operating income.
    """
    periods: List[Dict] = []
    equity = equity_start
    revenue = revenue_start
    margin = margin_start

    for offset in range(YEARS):
        year = BASE_YEAR + offset
        end = dt.date(year, 12, 31)
        filed = dt.date(year + 1, 2, 20)

        gross_profit = revenue * margin
        cost_of_revenue = revenue - gross_profit
        operating_income = gross_profit - revenue * opex_ratio
        da = revenue * da_ratio
        interest_expense = debt * interest_rate
        pretax = operating_income - interest_expense
        tax = max(0.0, pretax) * tax_rate
        net_income = pretax - tax
        capex = revenue * capex_ratio
        acquisitions = revenue * acquisitions_ratio
        current_assets = cash + revenue * working_capital_ratio * 2.2
        current_liabilities = revenue * working_capital_ratio

        periods.append(
            {
                "end": end.isoformat(),
                "fy": year,
                "fp": "FY",
                "filed": filed.isoformat(),
                "form": "10-K",
                "duration_days": 365,
                "revenue": round(revenue, 2),
                "cost_of_revenue": round(cost_of_revenue, 2),
                "gross_profit": round(gross_profit, 2),
                "operating_income": round(operating_income, 2),
                "pretax_income": round(pretax, 2),
                "income_tax_expense": round(tax, 2),
                "net_income": round(net_income, 2),
                "interest_expense": round(interest_expense, 2),
                "depreciation_amortization": round(da, 2),
                "capex": round(capex, 2),
                "acquisitions": round(acquisitions, 2),
                "operating_cash_flow": round(net_income + da, 2),
                "cash_and_equivalents": round(cash, 2),
                "short_term_investments": 0.0,
                "short_term_debt": round(debt * 0.1, 2),
                "long_term_debt": round(debt * 0.9, 2),
                "total_equity": round(equity, 2),
                "total_assets": round(equity + debt + current_liabilities, 2),
                "current_assets": round(current_assets, 2),
                "current_liabilities": round(current_liabilities, 2),
            }
        )

        # Retained earnings build equity; reinvestment grows the asset base.
        equity += net_income * 0.9
        revenue *= 1.0 + revenue_growth
        margin += margin_step

    if quarters:
        periods.extend(_synthesise_quarters(periods[-1], periods[-2]))

    history = _price_history(price)

    company = {
        "ticker": ticker,
        "name": name,
        "cik": str(abs(hash(ticker)) % 10**10).zfill(10),
        "exchange": exchange,
        "source": "fixture",
        "periods": periods,
        "market": {
            "ticker": ticker,
            "price": price,
            "price_date": dt.date(2026, 3, 31).isoformat(),
            "shares_outstanding": shares,
            "shares_date": dt.date(2026, 2, 20).isoformat(),
            "beta": 1.1,
            "history": history,
        },
        "insiders": {
            "basis": "form345",
            "as_of": dt.date(2026, 2, 1).isoformat(),
            "holdings": _insider_holdings(shares, insider_fraction),
            "notes": [],
        },
    }
    if note:
        company["warnings"] = [note]
    return company


def _synthesise_quarters(latest: Dict, prior: Dict) -> List[Dict]:
    """Split the last two fiscal years into quarters.

    The screen prefers a TTM margin over the last fiscal year, so fixtures
    need quarterly periods for that path to be exercised at all.
    """
    quarters: List[Dict] = []
    for source, year_offset in ((prior, 0), (latest, 0)):
        year = source["fy"]
        for quarter in range(1, 5):
            end_month = quarter * 3
            last_day = 31 if end_month in (3, 12) else 30
            end = dt.date(year, end_month, last_day)
            entry = {
                "end": end.isoformat(),
                "fy": year,
                "fp": f"Q{quarter}",
                "filed": (end + dt.timedelta(days=40)).isoformat(),
                "form": "10-Q",
                "duration_days": 91,
            }
            for field in (
                "revenue",
                "cost_of_revenue",
                "gross_profit",
                "operating_income",
                "pretax_income",
                "income_tax_expense",
                "net_income",
                "interest_expense",
                "depreciation_amortization",
                "capex",
                "acquisitions",
                "operating_cash_flow",
            ):
                if source.get(field) is not None:
                    entry[field] = round(source[field] / 4.0, 2)
            for field in (
                "cash_and_equivalents",
                "short_term_investments",
                "short_term_debt",
                "long_term_debt",
                "total_equity",
                "total_assets",
                "current_assets",
                "current_liabilities",
            ):
                if source.get(field) is not None:
                    entry[field] = source[field]
            quarters.append(entry)
    return quarters


def _price_history(price: float) -> List[Dict]:
    """Two years of weekly closes on a gentle upward drift."""
    history = []
    start = dt.date(2024, 4, 5)
    level = price * 0.75
    for week in range(104):
        date = start + dt.timedelta(weeks=week)
        # Deterministic pseudo-noise: no RNG, so fixtures are byte-stable.
        wobble = 1.0 + 0.02 * ((week * 7919) % 11 - 5) / 5.0
        level *= 1.0 + 0.0035
        history.append({"date": date.isoformat(), "close": round(level * wobble, 4)})
    return history


def _insider_holdings(shares: float, fraction: float) -> List[Dict]:
    if fraction <= 0:
        return []
    total = shares * fraction
    split = [0.55, 0.25, 0.12, 0.08]
    names = [
        ("Founder, Chief Executive", True, True),
        ("Chief Financial Officer", True, False),
        ("Director A", False, True),
        ("Director B", False, True),
    ]
    holdings = []
    for (name, officer, director), weight in zip(names, split):
        holdings.append(
            {
                "owner_name": name,
                "owner_cik": str(abs(hash(name)) % 10**10).zfill(10),
                "is_officer": officer,
                "is_director": director,
                "shares": round(total * weight, 0),
                "as_of": dt.date(2026, 2, 1).isoformat(),
            }
        )
    return holdings


# ----------------------------------------------------------------------
# The fixture set. Each entry names the decision path it exercises.
# ----------------------------------------------------------------------
FIXTURES = [
    # Clears all five conditions: $1.4bn cap, 52% and rising margin, ROIC well
    # above WACC with heavy reinvestment, 1.4x leverage, 18% insider-held.
    dict(
        ticker="IDEAL",
        name="Ideal Compounder Inc.",
        revenue_start=300e6,
        revenue_growth=0.14,
        margin_start=0.47,
        margin_step=0.012,
        opex_ratio=0.30,
        da_ratio=0.035,
        capex_ratio=0.075,
        equity_start=260e6,
        debt=90e6,
        cash=45e6,
        price=35.0,
        shares=40e6,
        insider_fraction=0.18,
    ),
    # Same economics, but a $12bn market cap: condition 1 fails.
    dict(
        ticker="BIGCAP",
        name="Well Covered Industries",
        revenue_start=2.4e9,
        revenue_growth=0.14,
        margin_start=0.50,
        margin_step=0.010,
        opex_ratio=0.30,
        da_ratio=0.035,
        capex_ratio=0.090,
        equity_start=3.0e9,
        debt=600e6,
        cash=400e6,
        price=80.0,
        shares=150e6,
        insider_fraction=0.14,
        exchange="NYSE",
    ),
    # A 26% margin: condition 2 fails on level.
    dict(
        ticker="THINMRG",
        name="Commodity Fabricators Corp.",
        revenue_start=800e6,
        revenue_growth=0.12,
        margin_start=0.25,
        margin_step=0.004,
        opex_ratio=0.12,
        da_ratio=0.04,
        capex_ratio=0.075,
        equity_start=400e6,
        debt=120e6,
        cash=60e6,
        price=22.0,
        shares=45e6,
        insider_fraction=0.15,
    ),
    # A 48% margin eroding 1.5 points a year: condition 2 fails on direction.
    dict(
        ticker="FADING",
        name="Eroding Moat Software",
        revenue_start=420e6,
        revenue_growth=0.16,
        margin_start=0.56,
        margin_step=-0.015,
        opex_ratio=0.30,
        da_ratio=0.03,
        capex_ratio=0.095,
        equity_start=300e6,
        debt=80e6,
        cash=70e6,
        price=26.0,
        shares=42e6,
        insider_fraction=0.16,
    ),
    # A debt-funded roll-up at ~4x EBITDA: condition 4 fails. It also just
    # misses condition 3's implied-growth floor, which is the honest result
    # rather than a coincidence -- debt-funded acquisitions inflate invested
    # capital, so the same business compounds more slowly per dollar in it.
    dict(
        ticker="LEVERED",
        name="Roll-Up Holdings",
        revenue_start=500e6,
        revenue_growth=0.12,
        margin_start=0.46,
        margin_step=0.008,
        opex_ratio=0.24,
        da_ratio=0.04,
        capex_ratio=0.06,
        equity_start=150e6,
        debt=1050e6,
        cash=25e6,
        price=19.0,
        shares=55e6,
        insider_fraction=0.13,
        acquisitions_ratio=0.05,
    ),
    # Professionally managed, 1.2% insider-held: condition 5 fails.
    dict(
        ticker="NOSKIN",
        name="Agency Problem Corp.",
        revenue_start=350e6,
        revenue_growth=0.14,
        margin_start=0.49,
        margin_step=0.010,
        opex_ratio=0.31,
        da_ratio=0.035,
        capex_ratio=0.085,
        equity_start=250e6,
        debt=100e6,
        cash=50e6,
        price=30.0,
        shares=44e6,
        insider_fraction=0.012,
    ),
    # Fat margin, but returns below the cost of capital and nothing being
    # reinvested: condition 3 fails.
    dict(
        ticker="LOWROIC",
        name="Capital Destroyer Ltd.",
        revenue_start=260e6,
        revenue_growth=0.01,
        margin_start=0.44,
        margin_step=0.003,
        opex_ratio=0.41,
        da_ratio=0.05,
        capex_ratio=0.012,
        equity_start=900e6,
        debt=25e6,
        cash=40e6,
        price=17.0,
        shares=60e6,
        insider_fraction=0.15,
    ),
]


def main() -> None:
    out_dir = os.path.abspath(OUT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    for spec in FIXTURES:
        company = build_company(**spec)
        path = os.path.join(out_dir, f"{company['ticker']}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(company, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"wrote {os.path.relpath(path)}")

    # A company with almost no filing history: exercises INSUFFICIENT_DATA.
    thin = {
        "ticker": "THINDATA",
        "name": "Recently Listed Co.",
        "cik": "0000000999",
        "exchange": "Nasdaq",
        "source": "fixture",
        "periods": [
            {
                "end": "2025-12-31",
                "fy": 2025,
                "fp": "FY",
                "filed": "2026-02-20",
                "form": "10-K",
                "duration_days": 365,
                "revenue": 120e6,
                "gross_profit": 55e6,
            }
        ],
        "market": {
            "ticker": "THINDATA",
            "price": 14.0,
            "price_date": "2026-03-31",
            "shares_outstanding": 60e6,
            "shares_date": "2026-02-20",
            "history": [],
        },
        "insiders": None,
    }
    path = os.path.join(out_dir, "THINDATA.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(thin, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(f"wrote {os.path.relpath(path)}")


if __name__ == "__main__":
    main()
