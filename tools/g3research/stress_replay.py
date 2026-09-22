"""
Addendum D (DEV-006 / CR-015) - deterministic execution stress replay.

Stress-1/2/3 never touch the live EA's alpha. They are evaluated offline by
replaying the EA's own candidate / order / exit log against the Development
tick history with a worse execution model.

Only the three scenarios pre-registered by v0.4 section 13.5 exist here, and
there is no way to add a fourth: the spread multipliers and slippage
fractions are a closed table.

Before any stress number may be used, the engine must reproduce the MT5
baseline under the Base scenario within four pre-registered tolerances. If
one of them misses, the stress results are not usable as G3 PASS evidence.
The tolerances are never changed after results have been seen.
"""
from . import spec_constants as sc

SPEC = sc.SPEC

# v0.4 section 13.5, verbatim and closed.
SCENARIOS = {
    "BASE":     {"spread_multiplier": 1.0, "adverse_slippage_fraction": 0.00},
    "STRESS_1": {"spread_multiplier": 1.5, "adverse_slippage_fraction": 0.25},
    "STRESS_2": {"spread_multiplier": 2.0, "adverse_slippage_fraction": 0.50},
    "STRESS_3": {"spread_multiplier": 3.0, "adverse_slippage_fraction": 1.00},
}

# Addendum D Base parity gate. Pre-registered, AND-combined, never relaxed.
PARITY_ACCEPT_AGREEMENT_MIN = 99.0     # percent
PARITY_EXIT_REASON_AGREEMENT_MIN = 98.0  # percent
PARITY_RESULT_R_MAE_MAX = 0.05         # R per matched trade
PARITY_NET_R_REL_DIFF_MAX = 2.0        # percent
PARITY_NET_R_DENOMINATOR_FLOOR = 1.0   # R, avoids a division by zero


class StressScenarioError(ValueError):
    """Raised when a scenario outside the pre-registered table is requested."""


def scenario(name):
    if name not in SCENARIOS:
        raise StressScenarioError(
            "unknown stress scenario %r; only %s are pre-registered"
            % (name, sorted(SCENARIOS)))
    return dict(SCENARIOS[name])


def stressed_spread(observed_spread, scenario_name):
    return observed_spread * scenario(scenario_name)["spread_multiplier"]


def adverse_slippage(observed_spread, scenario_name):
    return observed_spread * scenario(scenario_name)["adverse_slippage_fraction"]


def spread_blocks_entry(stressed_spread_price, atr_m5):
    """A stressed spread that breaches the Spread Hard Max rejects the entry
    in that stress run (Addendum D), using the v0.4 section 8.3 ceiling.
    """
    if atr_m5 <= 0.0:
        return True
    return (stressed_spread_price / atr_m5) > SPEC["G3_SPREAD_RATIO_ZERO"]


def stressed_prices(side, bid, ask, observed_spread, scenario_name):
    """Entry and exit both move against the position by the slippage amount."""
    slip = adverse_slippage(observed_spread, scenario_name)
    half = 0.5 * (stressed_spread(observed_spread, scenario_name) - observed_spread)
    if side == "BUY":
        return {"entry_price": ask + half + slip, "exit_price": bid - half - slip}
    return {"entry_price": bid - half - slip, "exit_price": ask + half + slip}


def restage_trade(side, stressed_entry, initial_sl, exit_mode,
                  timeout_bars, atr_at_entry):
    """Re-derive the protective geometry from the stressed entry price.

    Addendum D forbids treating stress as a flat P/L deduction: the stop
    distance, the 2.0R take profit of mode A, the break-even and partial
    trigger levels and the timeout MFE reference all move with the entry.
    """
    r_distance = abs(stressed_entry - initial_sl)
    if r_distance <= 0.0:
        return {"valid": False, "reason": "NON_POSITIVE_R_DISTANCE"}
    sign = 1.0 if side == "BUY" else -1.0

    def at_r(multiple):
        return stressed_entry + sign * multiple * r_distance

    staged = {
        "valid": True,
        "r_distance": r_distance,
        "entry_price": stressed_entry,
        "initial_sl": initial_sl,
        "take_profit": at_r(2.0) if exit_mode == "A" else None,
        "breakeven_trigger": at_r(1.0) if exit_mode == "B" else None,
        "partial_trigger": at_r(1.5) if exit_mode == "B" else None,
        "trail_atr_multiple": (2.0 if exit_mode == "B"
                               else (2.5 if exit_mode == "C" else None)),
        "trail_atr_distance": None,
        "timeout_bars": timeout_bars,
        "timeout_mfe_r": 0.75 if timeout_bars else None,
    }
    if staged["trail_atr_multiple"] is not None and atr_at_entry > 0.0:
        staged["trail_atr_distance"] = staged["trail_atr_multiple"] * atr_at_entry
    return staged


def net_r_relative_diff_pct(replay_net_r, mt5_net_r):
    """Addendum D: denominator is max(|MT5 aggregate Net R|, 1.0R)."""
    denominator = max(abs(mt5_net_r), PARITY_NET_R_DENOMINATOR_FLOOR)
    return abs(replay_net_r - mt5_net_r) / denominator * 100.0


def base_parity_gate(accept_agreement_pct, exit_reason_agreement_pct,
                     result_r_mean_abs_diff, replay_net_r, mt5_net_r):
    """The four Base parity conditions. All four, or the stress runs are out."""
    net_r_diff = net_r_relative_diff_pct(replay_net_r, mt5_net_r)
    conditions = {
        "candidate_accept_agreement": (
            accept_agreement_pct >= PARITY_ACCEPT_AGREEMENT_MIN,
            accept_agreement_pct, PARITY_ACCEPT_AGREEMENT_MIN),
        "exit_reason_agreement": (
            exit_reason_agreement_pct >= PARITY_EXIT_REASON_AGREEMENT_MIN,
            exit_reason_agreement_pct, PARITY_EXIT_REASON_AGREEMENT_MIN),
        "result_r_mean_abs_diff": (
            result_r_mean_abs_diff <= PARITY_RESULT_R_MAE_MAX,
            result_r_mean_abs_diff, PARITY_RESULT_R_MAE_MAX),
        "net_r_relative_diff_pct": (
            net_r_diff <= PARITY_NET_R_REL_DIFF_MAX,
            net_r_diff, PARITY_NET_R_REL_DIFF_MAX),
    }
    passed = all(v[0] for v in conditions.values())
    return {
        "pass": passed,
        "conditions": {k: {"pass": v[0], "value": v[1], "threshold": v[2]}
                       for k, v in conditions.items()},
        "stress_results_usable_as_g3_pass_evidence": passed,
        "on_fail": ("Base parity FAIL: Stress-1/2/3 results must not be used "
                    "as G3 PASS evidence. Tolerances are not adjustable after "
                    "results have been seen."),
    }


def run_scenarios(trades, atr_lookup=None):
    """Apply every pre-registered scenario to a list of recorded trades.

    Each trade needs: side, bid, ask, observed_spread, initial_sl, exit_mode,
    timeout_bars, atr_m5, atr_at_entry. The caller supplies the realised price
    path separately; this function stages the geometry and the rejections that
    the stressed execution model implies.
    """
    out = {}
    for name in ("BASE", "STRESS_1", "STRESS_2", "STRESS_3"):
        staged = []
        rejected = 0
        for t in trades:
            sp = stressed_spread(t["observed_spread"], name)
            if spread_blocks_entry(sp, t["atr_m5"]):
                rejected += 1
                staged.append({"symbol": t.get("symbol"), "rejected": True,
                               "reason": "SPREAD_HARD_MAX_UNDER_STRESS"})
                continue
            prices = stressed_prices(t["side"], t["bid"], t["ask"],
                                     t["observed_spread"], name)
            geom = restage_trade(t["side"], prices["entry_price"], t["initial_sl"],
                                 t["exit_mode"], t.get("timeout_bars", 0),
                                 t.get("atr_at_entry", 0.0))
            staged.append({"symbol": t.get("symbol"), "rejected": False,
                           "prices": prices, "geometry": geom})
        out[name] = {"scenario": scenario(name), "trades": staged,
                     "rejected_by_spread_hard_max": rejected}
    return out
