"""Derived financial quantities.

Everything the five criteria test is computed here, once, so the definitions
live in one place and can be unit-tested against known inputs. Each function
returns ``None`` when its inputs are missing -- never a zero, never a guess.

Definitional choices worth knowing about (all of them defensible, none of
them the only option):

* **Invested capital** uses the financing-side identity: interest-bearing
  debt + book equity - cash and short-term investments. The operating-side
  build-up (net working capital + net fixed assets + intangibles) is
  equivalent in theory and noisier in XBRL practice.
* **Excess cash** is treated as *all* cash. For a cash-rich small cap this
  raises measured ROIC; the alternative (an operating-cash allowance of a few
  percent of revenue) is arbitrary in its own way. The screen reports both
  ROIC and the cash balance so the effect is visible.
* **EBITDA** is operating income + D&A, not "adjusted" EBITDA. Management's
  adjustments are exactly what a leverage test should not take on trust.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import List, Optional, Sequence

from .config import ReturnsConfig
from .models import FinancialPeriod
from .util.stats import (
    average_balance,
    clamp,
    safe_div,
    safe_sub,
    sum_present,
)

Number = Optional[float]


# ----------------------------------------------------------------------
# Single-period quantities
# ----------------------------------------------------------------------
def gross_margin(period: FinancialPeriod) -> Number:
    """Gross profit / revenue."""
    gross = period.gross_profit
    if gross is None and period.revenue is not None and period.cost_of_revenue is not None:
        gross = period.revenue - period.cost_of_revenue
    return safe_div(gross, period.revenue)


def gross_profits_to_assets(period: FinancialPeriod) -> Number:
    """Novy-Marx's gross profitability: gross profit / total assets.

    This is the ratio "The Other Side of Value" actually tests. The brief's
    condition is the gross *margin*, which is gated elsewhere; this is carried
    alongside it because the two can disagree sharply for asset-heavy firms.
    """
    gross = period.gross_profit
    if gross is None and period.revenue is not None and period.cost_of_revenue is not None:
        gross = period.revenue - period.cost_of_revenue
    return safe_div(gross, period.total_assets)


def total_debt(period: FinancialPeriod) -> Number:
    """Interest-bearing debt: short-term + long-term.

    Operating lease liabilities are deliberately excluded. They are debt-like
    under ASC 842, but including them would make the 3x ceiling bite hardest
    on companies that rent rather than own their premises, which is not the
    balance-sheet fragility the condition is aimed at.
    """
    return sum_present(period.short_term_debt, period.long_term_debt)


def cash_and_investments(period: FinancialPeriod) -> Number:
    return sum_present(period.cash_and_equivalents, period.short_term_investments)


def net_debt(period: FinancialPeriod) -> Number:
    debt = total_debt(period)
    if debt is None:
        return None
    cash = cash_and_investments(period) or 0.0
    return debt - cash


def ebitda(period: FinancialPeriod) -> Number:
    """Operating income + D&A, as reported."""
    if period.operating_income is None:
        return None
    da = period.depreciation_amortization
    if da is None:
        # D&A is a cash-flow-statement item and is occasionally untagged.
        # Falling back to EBIT understates EBITDA, which makes the leverage
        # test stricter -- an error in the conservative direction.
        return period.operating_income
    return period.operating_income + da


def effective_tax_rate(period: FinancialPeriod, config: ReturnsConfig) -> Number:
    """Cash-ish effective rate, clamped to a plausible band.

    A loss-making year produces a nonsense ratio (negative tax on negative
    pretax income), so the result is clamped and falls back to the statutory
    default.
    """
    rate = safe_div(period.income_tax_expense, period.pretax_income)
    if rate is None or period.pretax_income is None or period.pretax_income <= 0:
        return config.default_tax_rate
    return clamp(rate, config.tax_rate_min, config.tax_rate_max)


def nopat(period: FinancialPeriod, config: ReturnsConfig) -> Number:
    """Net operating profit after tax = EBIT x (1 - effective tax rate)."""
    if period.operating_income is None:
        return None
    rate = effective_tax_rate(period, config)
    if rate is None:
        rate = config.default_tax_rate
    return period.operating_income * (1.0 - rate)


def invested_capital(period: FinancialPeriod) -> Number:
    """Interest-bearing debt + book equity - cash and short-term investments."""
    if period.total_equity is None:
        return None
    debt = total_debt(period) or 0.0
    cash = cash_and_investments(period) or 0.0
    return debt + period.total_equity - cash


def operating_working_capital(period: FinancialPeriod) -> Number:
    """Working capital excluding cash and short-term debt."""
    if period.current_assets is None or period.current_liabilities is None:
        return None
    cash = cash_and_investments(period) or 0.0
    short_debt = period.short_term_debt or 0.0
    return (period.current_assets - cash) - (period.current_liabilities - short_debt)


def roic(
    period: FinancialPeriod,
    config: ReturnsConfig,
    prior: Optional[FinancialPeriod] = None,
) -> Number:
    """NOPAT / average invested capital.

    Averaging the opening and closing invested capital matches the flow in the
    numerator to the capital that produced it. A company whose invested
    capital is negative (more cash than debt and equity combined) has no
    meaningful ROIC, so the result is ``None`` rather than a large positive
    number produced by a negative denominator.
    """
    profit = nopat(period, config)
    ending = invested_capital(period)
    beginning = invested_capital(prior) if prior is not None else None
    capital = average_balance(ending, beginning)
    if capital is None or capital <= 0:
        return None
    return safe_div(profit, capital)


# ----------------------------------------------------------------------
# Reinvestment
# ----------------------------------------------------------------------
def reinvestment_cashflow(
    period: FinancialPeriod, prior: Optional[FinancialPeriod]
) -> Number:
    """Cash deployed into growth: capex - D&A + change in working capital + acquisitions.

    This is Mauboussin's formulation: maintenance capital (approximated by
    D&A) is not reinvestment, only the excess is.
    """
    if period.capex is None:
        return None
    # capex and acquisitions are tagged as positive cash outflows.
    growth_capex = period.capex - (period.depreciation_amortization or 0.0)
    acquisitions = period.acquisitions or 0.0
    delta_wc = 0.0
    if prior is not None:
        current_wc = operating_working_capital(period)
        prior_wc = operating_working_capital(prior)
        change = safe_sub(current_wc, prior_wc)
        if change is not None:
            delta_wc = change
    return growth_capex + delta_wc + acquisitions


def reinvestment_balance(
    period: FinancialPeriod, prior: Optional[FinancialPeriod]
) -> Number:
    """Year-on-year growth in invested capital."""
    if prior is None:
        return None
    return safe_sub(invested_capital(period), invested_capital(prior))


def reinvestment_rate(
    period: FinancialPeriod,
    prior: Optional[FinancialPeriod],
    config: ReturnsConfig,
) -> Number:
    """Reinvestment / NOPAT.

    Negative NOPAT makes the ratio meaningless (a company that reinvests while
    losing money would score as strongly negative, or strongly positive if it
    also divests), so it returns ``None``.
    """
    profit = nopat(period, config)
    if profit is None or profit <= 0:
        return None
    method = config.reinvestment_method
    value: Number = None
    if method in ("cashflow", "auto"):
        value = reinvestment_cashflow(period, prior)
    if value is None and method in ("balance", "auto"):
        value = reinvestment_balance(period, prior)
    if value is None:
        return None
    return value / profit


def implied_growth(roic_value: Number, reinvestment: Number) -> Number:
    """ROIC x reinvestment rate -- the rate at which value compounds.

    The identity behind the brief's third condition: a high return with
    nowhere to redeploy it grows nothing.
    """
    if roic_value is None or reinvestment is None:
        return None
    return roic_value * reinvestment


# ----------------------------------------------------------------------
# Cost of capital
# ----------------------------------------------------------------------
@dataclass
class WaccBreakdown:
    """Every input to the WACC, kept so a result can be argued with."""

    wacc: Optional[float]
    cost_of_equity: Optional[float]
    cost_of_debt: Optional[float]
    beta: Optional[float]
    beta_source: str
    equity_value: Optional[float]
    debt_value: Optional[float]
    tax_rate: Optional[float]
    floored: bool = False


def cost_of_equity(beta: Number, config: ReturnsConfig) -> Number:
    """CAPM, with a small-cap size premium added.

    The size premium is not part of textbook CAPM. It is here because the
    whole screen is aimed at companies where the size factor is the reason
    for the excess return -- charging nothing for that risk would make every
    candidate look like it clears its cost of capital.
    """
    if beta is None:
        return None
    return (
        config.risk_free_rate
        + beta * config.equity_risk_premium
        + config.size_premium
    )


def cost_of_debt(
    period: FinancialPeriod,
    prior: Optional[FinancialPeriod],
    config: ReturnsConfig,
) -> Number:
    """Interest expense / average debt, bounded to a sane range."""
    debt_now = total_debt(period)
    debt_prior = total_debt(prior) if prior is not None else None
    average = average_balance(debt_now, debt_prior)
    if average is None or average <= 0 or period.interest_expense is None:
        return config.risk_free_rate + config.default_credit_spread
    rate = safe_div(abs(period.interest_expense), average)
    if rate is None:
        return config.risk_free_rate + config.default_credit_spread
    # An implied rate outside this band means the interest line and the debt
    # line are not measuring the same thing; fall back rather than propagate.
    if rate < 0.005 or rate > 0.30:
        return config.risk_free_rate + config.default_credit_spread
    return rate


def wacc(
    period: FinancialPeriod,
    prior: Optional[FinancialPeriod],
    market_cap: Number,
    beta: Number,
    config: ReturnsConfig,
) -> WaccBreakdown:
    """Market-value-weighted cost of capital."""
    beta_source = "regression"
    if beta is None:
        beta = config.default_beta
        beta_source = "default"
    beta = clamp(beta, config.beta_min, config.beta_max)

    equity_cost = cost_of_equity(beta, config)
    debt_cost = cost_of_debt(period, prior, config)
    tax_rate = effective_tax_rate(period, config) or config.default_tax_rate

    equity_value = market_cap
    debt_value = total_debt(period)
    if equity_value is None:
        # Without a market value there is no sensible weighting; book equity
        # is a poor proxy, so the result is flagged rather than fabricated.
        return WaccBreakdown(
            wacc=None,
            cost_of_equity=equity_cost,
            cost_of_debt=debt_cost,
            beta=beta,
            beta_source=beta_source,
            equity_value=None,
            debt_value=debt_value,
            tax_rate=tax_rate,
        )
    debt_value = debt_value or 0.0
    total_value = equity_value + debt_value
    if total_value <= 0 or equity_cost is None or debt_cost is None:
        return WaccBreakdown(
            wacc=None,
            cost_of_equity=equity_cost,
            cost_of_debt=debt_cost,
            beta=beta,
            beta_source=beta_source,
            equity_value=equity_value,
            debt_value=debt_value,
            tax_rate=tax_rate,
        )

    raw = (equity_value / total_value) * equity_cost + (
        debt_value / total_value
    ) * debt_cost * (1.0 - tax_rate)
    floored = raw < config.wacc_floor
    return WaccBreakdown(
        wacc=max(raw, config.wacc_floor),
        cost_of_equity=equity_cost,
        cost_of_debt=debt_cost,
        beta=beta,
        beta_source=beta_source,
        equity_value=equity_value,
        debt_value=debt_value,
        tax_rate=tax_rate,
        floored=floored,
    )


# ----------------------------------------------------------------------
# Trailing-twelve-month aggregation
# ----------------------------------------------------------------------
def trailing_twelve_months(
    quarters: Sequence[FinancialPeriod], end_index: int = -1
) -> Optional[FinancialPeriod]:
    """Sum four consecutive quarters into a synthetic annual period.

    Returns ``None`` unless four quarters are present and together span
    roughly a year -- a gap (the very common case of an untagged Q4) must not
    silently produce a nine-month "year".
    """
    if len(quarters) < 4:
        return None
    ordered = sorted(quarters, key=lambda p: p.end)
    if end_index < 0:
        end_index = len(ordered) + end_index
    if end_index < 3 or end_index >= len(ordered):
        return None
    window = ordered[end_index - 3 : end_index + 1]

    span_days = sum(q.duration_days or 0 for q in window)
    if not 320 <= span_days <= 400:
        return None

    last = window[-1]
    combined = FinancialPeriod(
        end=last.end,
        fy=last.fy,
        fp="TTM",
        filed=last.filed,
        form=last.form,
        duration_days=span_days,
    )
    flow_fields = [
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
    ]
    for name in flow_fields:
        values = [getattr(q, name) for q in window]
        if any(v is None for v in values):
            continue
        setattr(combined, name, float(sum(values)))
    # Balance-sheet items are stocks: carry the latest, never the sum.
    stock_fields = [
        "cash_and_equivalents",
        "short_term_investments",
        "short_term_debt",
        "long_term_debt",
        "total_equity",
        "total_assets",
        "current_assets",
        "current_liabilities",
    ]
    for name in stock_fields:
        setattr(combined, name, getattr(last, name))
    return combined


def gross_margin_series(
    periods: Sequence[FinancialPeriod],
) -> List[tuple]:
    """(period end, gross margin) for every period where the margin computes."""
    series = []
    for period in sorted(periods, key=lambda p: p.end):
        margin = gross_margin(period)
        if margin is not None:
            series.append((period.end, margin))
    return series


def years_between(start: dt.date, end: dt.date) -> float:
    return (end - start).days / 365.25
