"""Screening thresholds and engine settings.

Every number a criterion tests against lives here, so a research run is fully
described by its config file plus the as-of date. Defaults encode the five
conditions in the brief; ``--set`` overrides on the CLI let you run
sensitivity sweeps without editing code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict, fields, is_dataclass
from typing import Any, Dict, Optional


@dataclass
class MarketCapConfig:
    """Condition 1 -- the small-cap band (Fama-French size factor)."""

    min_usd: float = 500_000_000.0      # 5億ドル
    max_usd: float = 3_000_000_000.0    # 30億ドル
    # Prefer the cover-page share count when it is no older than this many
    # days; otherwise fall back to the latest balance-sheet share count.
    shares_max_age_days: int = 200


@dataclass
class GrossMarginConfig:
    """Condition 2 -- gross profitability level and direction.

    Novy-Marx measures gross profitability as gross profit scaled by assets;
    the brief asks for the margin (gross profit / revenue) plus a requirement
    that it is improving. Both are computed; the gate follows the brief.
    """

    min_level: float = 0.40
    # Minimum OLS slope of the margin against time, in margin points per year.
    # 0.0 means "flat is not enough, it must be rising".
    min_slope_per_year: float = 0.0
    # Minimum improvement of the latest TTM margin over the year-ago TTM
    # margin. Guards against a slope driven entirely by old history.
    min_recent_delta: float = 0.0
    # Number of annual points used for the trend regression.
    trend_periods: int = 5
    min_trend_periods: int = 3
    # Also compute Novy-Marx gross-profits-to-assets for reference/reporting.
    report_gross_profits_to_assets: bool = True


@dataclass
class ReturnsConfig:
    """Condition 3 -- ROIC above the cost of capital, with reinvestment."""

    # Required spread of ROIC over WACC.
    min_roic_minus_wacc: float = 0.0
    # Floor on ROIC itself, so a company cannot pass on a low WACC alone.
    min_roic: float = 0.10
    min_reinvestment_rate: float = 0.30
    # Mauboussin's value-creation identity: intrinsic compounding converges on
    # ROIC x reinvestment rate. This floors that product.
    min_implied_growth: float = 0.05
    # Reinvestment can be measured from the change in invested capital
    # ("balance") or from cash deployed: capex - D&A + dWC + acquisitions
    # ("cashflow"). "auto" prefers cashflow and falls back to balance.
    reinvestment_method: str = "auto"
    # Averaged over this many years to damp single-year lumpiness.
    lookback_years: int = 3
    min_lookback_years: int = 2

    # --- WACC inputs ---
    risk_free_rate: float = 0.042
    equity_risk_premium: float = 0.055
    # Extra premium for illiquid, thinly covered small caps.
    size_premium: float = 0.020
    # Used when a price history for a beta regression is unavailable.
    default_beta: float = 1.20
    beta_min: float = 0.5
    beta_max: float = 2.5
    # Fallback cost of debt when interest expense or debt balances are missing.
    default_credit_spread: float = 0.030
    default_tax_rate: float = 0.21
    tax_rate_min: float = 0.0
    tax_rate_max: float = 0.35
    # Floor on WACC, so a debt-free company is not handed a trivially low bar.
    wacc_floor: float = 0.06


@dataclass
class LeverageConfig:
    """Condition 4 -- interest-bearing debt / EBITDA."""

    max_debt_to_ebitda: float = 3.0
    # The brief specifies gross interest-bearing debt. Net debt is always
    # computed and reported; set this to gate on net debt instead.
    use_net_debt: bool = False
    # A company with negative EBITDA cannot satisfy a leverage ceiling; it is
    # a FAIL rather than INSUFFICIENT_DATA when it also carries debt.
    treat_negative_ebitda_as_fail: bool = True
    # Debt-free companies pass trivially; recorded explicitly in the reasons.
    debt_free_passes: bool = True


@dataclass
class InsiderConfig:
    """Condition 5 -- management alignment (Jensen-Meckling)."""

    min_ownership: float = 0.10
    # Form 4 holdings older than this are treated as stale and dropped.
    max_holding_age_days: int = 1095
    # Count only officers/directors, or also 10% beneficial owners. The
    # agency-cost argument is about managers, so external 10% holders are
    # excluded by default.
    include_ten_percent_owners: bool = False
    # Ownership computed from Form 3/4/5 is a lower bound (see docs). This
    # flag keeps that caveat attached to every result derived that way.
    warn_on_form345_basis: bool = True
    # How many ownership filings to read per company, newest first. Each one
    # is a separate HTTP request, so this is the single biggest driver of a
    # full-universe run's duration. Raise it for long backtests, where the
    # oldest rebalance dates need filings from further back.
    max_filings: int = 120


@dataclass
class ScoringConfig:
    """Weights for the composite score used to rank the survivors."""

    weights: Dict[str, float] = field(
        default_factory=lambda: {
            "market_cap": 0.10,
            "gross_margin": 0.25,
            "returns": 0.35,
            "leverage": 0.15,
            "insider": 0.15,
        }
    )
    # Rank only companies that pass every decidable criterion.
    require_all_pass: bool = True
    # Below this share of resolvable inputs, a company is reported but not
    # ranked -- thin data is a reason to abstain, not to guess.
    min_data_quality: float = 0.60


@dataclass
class AIConfig:
    """Optional Claude-powered qualitative layer."""

    enabled: bool = False
    model: str = "claude-opus-5"
    effort: str = "high"
    max_tokens: int = 8000
    # Only the top-ranked survivors are sent for review; the layer is a
    # judgement aid on a short list, not a substitute for the screen.
    max_candidates: int = 10
    include_filing_excerpts: bool = False


@dataclass
class Config:
    as_of: Optional[str] = None          # ISO date; None means "today"
    market_cap: MarketCapConfig = field(default_factory=MarketCapConfig)
    gross_margin: GrossMarginConfig = field(default_factory=GrossMarginConfig)
    returns: ReturnsConfig = field(default_factory=ReturnsConfig)
    leverage: LeverageConfig = field(default_factory=LeverageConfig)
    insider: InsiderConfig = field(default_factory=InsiderConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    ai: AIConfig = field(default_factory=AIConfig)

    # --- data plumbing ---
    user_agent: str = "smallcap-screener/1.0 (research; contact: set SEC_USER_AGENT)"
    cache_dir: str = ".cache/smallcap"
    cache_ttl_hours: float = 24.0
    request_delay_seconds: float = 0.12   # SEC asks for <= 10 requests/second
    max_retries: int = 4
    timeout_seconds: float = 30.0
    workers: int = 4

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: Optional[str] = None) -> "Config":
        config = cls()
        if path:
            with open(path, "r", encoding="utf-8") as handle:
                raw = _parse_config_text(handle.read(), path)
            config = _apply_mapping(config, raw)
        env_agent = os.environ.get("SEC_USER_AGENT")
        if env_agent:
            config.user_agent = env_agent
        return config

    def override(self, dotted: str, value: str) -> None:
        """Apply a ``section.key=value`` override from the command line."""
        target: Any = self
        parts = dotted.split(".")
        for part in parts[:-1]:
            if isinstance(target, dict):
                target = target.setdefault(part, {})
            elif hasattr(target, part):
                target = getattr(target, part)
            else:
                raise KeyError(f"unknown config section: {dotted}")
        leaf = parts[-1]
        if isinstance(target, dict):
            target[leaf] = _coerce(value, target.get(leaf))
            return
        if not hasattr(target, leaf):
            raise KeyError(f"unknown config key: {dotted}")
        target.__setattr__(leaf, _coerce(value, getattr(target, leaf)))


def _parse_config_text(text: str, path: str) -> Dict[str, Any]:
    """Parse JSON, or YAML when PyYAML happens to be installed."""
    if path.endswith((".yml", ".yaml")):
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "YAML config requires PyYAML; use a .json config instead"
            ) from exc
        return yaml.safe_load(text) or {}
    return json.loads(text)


def _apply_mapping(node: Any, raw: Dict[str, Any]) -> Any:
    """Overlay a parsed mapping onto a dataclass tree, key by key."""
    if not is_dataclass(node):
        return raw
    known = {f.name: f for f in fields(node)}
    for key, value in raw.items():
        # JSON has no comment syntax, so underscore-prefixed keys are treated
        # as annotations and ignored. Everything else must be a real setting:
        # a typo silently doing nothing is how a screen ends up running
        # thresholds nobody intended.
        if key.startswith("_"):
            continue
        if key not in known:
            raise KeyError(f"unknown config key: {key}")
        current = getattr(node, key)
        if is_dataclass(current) and isinstance(value, dict):
            setattr(node, key, _apply_mapping(current, value))
        elif isinstance(current, dict) and isinstance(value, dict):
            merged = dict(current)
            merged.update(value)
            setattr(node, key, merged)
        else:
            setattr(node, key, value)
    return node


def _coerce(value: str, reference: Any) -> Any:
    """Coerce a CLI string to the type of the value it replaces."""
    if isinstance(reference, bool):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value
