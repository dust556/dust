"""
Addendum F (ISSUE-003 / CR-003) - offline chronological portfolio replay.

The MT5 strategy tester runs one expert, so the portfolio rules of section
11.4 cannot be produced by a per-symbol backtest. The official G3 portfolio
evidence is this replay: every pair's strategy-eligible candidates (the
SHADOW records the EA writes before any portfolio guard) are merged in
decision-time order and driven through ONE shared state machine.

Simply adding up per-pair results is forbidden by Addendum F and this module
offers no way to do it.

Nothing here is tuned. Every ceiling comes from spec_constants, which is
checked back against the EA sources on import of that module.
"""

from . import spec_constants as sc

SPEC = sc.SPEC

# Addendum F: performance-independent processing order for candidates that
# share a decision timestamp. Fixed in advance, never reordered on results.
UNIVERSE_ORDER_INITIAL7 = [
    "AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY",
]

# Cross-check gate, Addendum F. Pre-registered, never changed after results.
CROSSCHECK_ACCEPT_AGREEMENT_MIN = 98.0      # percent
CROSSCHECK_RESULT_R_MAE_MAX = 0.10          # R per matched trade
CROSSCHECK_DD_STATE_AGREEMENT_MIN = 90.0    # percent
CROSSCHECK_MAX_DD_ABS_DIFF_MAX = 1.0        # percentage points
CROSSCHECK_BLOCK_MONTHS = 3

# N-3 (G2 delta re-audit, MEDIUM, non-blocking): a disclosure threshold, not
# a PASS threshold. Below it the cross-check window is flagged as of limited
# representativeness; nothing fails because of it.
SIMULTANEOUS_CANDIDATE_DISCLOSURE_MIN = 5


def universe_rank(symbol):
    """Initial 7 in the fixed order, Stage-2 after them in ASCII order."""
    if symbol in UNIVERSE_ORDER_INITIAL7:
        return UNIVERSE_ORDER_INITIAL7.index(symbol)
    return len(UNIVERSE_ORDER_INITIAL7)


def candidate_sort_key(candidate):
    """Decision time first, then the fixed universe order, then ASCII."""
    return (candidate["decision_time"], universe_rank(candidate["symbol"]),
            candidate["symbol"])


def sort_candidates(candidates):
    return sorted(candidates, key=candidate_sort_key)


def base_currency(symbol):
    return symbol[0:3]


def quote_currency(symbol):
    return symbol[3:6]


def currency_direction(side, is_base):
    d = 1 if side == "BUY" else -1
    return d if is_base else -d


def side_sign(side):
    return 1 if side == "BUY" else -1


def next_dd_state(current, dd_pct, latched):
    """Identical transition rules to G3NextDDState in src/RiskManager.mqh."""
    if current == "STATE_UNCERTAIN":
        return "STATE_UNCERTAIN", latched
    if dd_pct >= SPEC["G3_DD_HARD_STOP_ENTER"]:
        return "HARD_STOP", True
    if latched:
        return "HARD_STOP", True
    if current == "NORMAL":
        if dd_pct >= SPEC["G3_DD_RESTRICTED_ENTER"]:
            return "RESTRICTED", latched
        if dd_pct >= SPEC["G3_DD_MODERATE_ENTER"]:
            return "MODERATE", latched
        return "NORMAL", latched
    if current == "MODERATE":
        if dd_pct >= SPEC["G3_DD_RESTRICTED_ENTER"]:
            return "RESTRICTED", latched
        if dd_pct < SPEC["G3_DD_NORMAL_RECOVER"]:
            return "NORMAL", latched
        return "MODERATE", latched
    if current == "RESTRICTED":
        if dd_pct < SPEC["G3_DD_MODERATE_RECOVER"]:
            return "MODERATE", latched
        return "RESTRICTED", latched
    return current, latched


def drawdown_pct(peak_equity, equity):
    if peak_equity <= 0.0:
        return 0.0
    return max(0.0, (peak_equity - equity) / peak_equity * 100.0)


def floor_to_step(raw, step):
    if step <= 0.0:
        return raw
    return max(0.0, (raw // step) * step) if raw >= 0 else 0.0


class PortfolioReplay:
    """One shared state machine for the whole universe."""

    def __init__(self, initial_equity, score_threshold_input,
                 correlation_provider=None, server_date_of=None):
        self.equity = float(initial_equity)
        self.peak_equity = float(initial_equity)
        self.dd_state = "NORMAL"
        self.hard_stop_latched = False
        self.daily_start_equity = float(initial_equity)
        self.server_date = None
        self.score_threshold_input = int(score_threshold_input)
        self.open_positions = []          # dicts with exit_time / risk data
        self.correlation_provider = correlation_provider
        self.server_date_of = server_date_of or (lambda t: t // 86400)
        self.decisions = []
        self.max_drawdown_pct = 0.0

    # -- equity / state -------------------------------------------------
    def _touch_state(self):
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
        dd = drawdown_pct(self.peak_equity, self.equity)
        self.max_drawdown_pct = max(self.max_drawdown_pct, dd)
        self.dd_state, self.hard_stop_latched = next_dd_state(
            self.dd_state, dd, self.hard_stop_latched)
        return dd

    def _roll_day(self, at_time):
        day = self.server_date_of(at_time)
        if self.server_date is None or day > self.server_date:
            self.server_date = day
            self.daily_start_equity = self.equity

    def _close_due(self, at_time):
        still_open = []
        for pos in self.open_positions:
            if pos["exit_time"] <= at_time:
                self.equity += pos["result_r"] * pos["risk_money"]
                self._roll_day(pos["exit_time"])
                self._touch_state()
            else:
                still_open.append(pos)
        self.open_positions = still_open

    def daily_locked(self):
        return self.equity <= self.daily_start_equity * SPEC["G3_DAILY_LOCK_RATIO"]

    # -- guards ---------------------------------------------------------
    def _total_risk_pct(self, extra=0.0):
        return sum(p["risk_pct"] for p in self.open_positions) + extra

    def _currency_risk_pct(self, symbol, side, extra_pct):
        worst = 0.0
        for is_base in (True, False):
            ccy = base_currency(symbol) if is_base else quote_currency(symbol)
            direction = currency_direction(side, is_base)
            total = extra_pct
            for p in self.open_positions:
                for p_is_base in (True, False):
                    p_ccy = (base_currency(p["symbol"]) if p_is_base
                             else quote_currency(p["symbol"]))
                    if p_ccy != ccy:
                        continue
                    if currency_direction(p["side"], p_is_base) != direction:
                        continue
                    total += p["risk_pct"]
            worst = max(worst, total)
        return worst

    def _cluster_risk_pct(self, candidate, extra_pct, at_time):
        """Direction adjusted signed correlation cluster (spec 11.4)."""
        if self.correlation_provider is None:
            return extra_pct, "CORR_READY", int(SPEC["G3_CORR_REQUIRED_BARS"])
        legs = [{"symbol": p["symbol"], "side": p["side"], "risk_pct": p["risk_pct"]}
                for p in self.open_positions]
        legs.append({"symbol": candidate["symbol"], "side": candidate["side"],
                     "risk_pct": extra_pct})
        ready = True
        warmup = int(SPEC["G3_CORR_REQUIRED_BARS"])
        pair_corr = {}
        for i in range(len(legs)):
            for j in range(i + 1, len(legs)):
                value, is_ready, bars = self.correlation_provider(
                    legs[i]["symbol"], legs[j]["symbol"], at_time)
                if not is_ready:
                    ready = False
                warmup = min(warmup, bars)
                pair_corr[(i, j)] = value
        if not ready:
            # correlation is never treated as zero: candidate plus every open
            # position form one unknown cluster.
            return sum(l["risk_pct"] for l in legs), "CORR_WARMUP_UNKNOWN", warmup
        parent = list(range(len(legs)))

        def find(x):
            while parent[x] != x:
                x = parent[x]
            return x

        for (i, j), value in pair_corr.items():
            signed = value * side_sign(legs[i]["side"]) * side_sign(legs[j]["side"])
            if signed >= SPEC["G3_CORR_THRESHOLD"]:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
        root = find(len(legs) - 1)
        total = sum(l["risk_pct"] for i, l in enumerate(legs) if find(i) == root)
        return total, "CORR_READY", warmup

    # -- main loop ------------------------------------------------------
    def run(self, candidates):
        """Replay all candidates in decision-time order.

        Each candidate dict needs: symbol, decision_time, side, total_score,
        risk_1lot_money, volume_step, volume_min, result_r, exit_time.
        """
        ordered = sort_candidates(candidates)
        simultaneous = simultaneous_candidate_counts(ordered)
        for cand in ordered:
            at = cand["decision_time"]
            self._close_due(at)
            self._roll_day(at)
            dd = self._touch_state()
            decision = {
                "symbol": cand["symbol"],
                "decision_time": at,
                "side": cand["side"],
                "dd_state": self.dd_state,
                "dd_pct": dd,
                "equity": self.equity,
                "accepted": False,
                "reason": "NONE",
                "risk_pct": 0.0,
                "open_positions": len(self.open_positions),
                "corr_state": "CORR_READY",
                "corr_warmup_days": int(SPEC["G3_CORR_REQUIRED_BARS"]),
                "simultaneous_candidates": simultaneous.get(at, 1),
            }

            if self.dd_state in ("HARD_STOP", "STATE_UNCERTAIN") or self.hard_stop_latched:
                decision["reason"] = "HARD_STOP_LATCHED"
                self.decisions.append(decision)
                continue
            if self.daily_locked():
                decision["reason"] = "DAILY_ENTRY_LOCK"
                self.decisions.append(decision)
                continue

            threshold = sc.effective_score_threshold(self.score_threshold_input,
                                                     self.dd_state)
            if cand["total_score"] < threshold:
                decision["reason"] = "TOTAL_SCORE_BELOW_THRESHOLD"
                self.decisions.append(decision)
                continue

            risk_pct = sc.risk_pct_for_state(self.dd_state)
            risk_money = self.equity * risk_pct / 100.0
            if cand["risk_1lot_money"] <= 0.0 or risk_money <= 0.0:
                decision["reason"] = "ORDER_CALC_PROFIT_INVALID"
                self.decisions.append(decision)
                continue
            raw_lot = risk_money / cand["risk_1lot_money"]
            lot = floor_to_step(raw_lot, cand["volume_step"])
            if lot < cand["volume_min"] - 1e-12:
                decision["reason"] = "RISK_MONEY_EXCEEDED_AT_MIN_VOLUME"
                self.decisions.append(decision)
                continue
            booked_risk_money = lot * cand["risk_1lot_money"]
            booked_risk_pct = booked_risk_money / self.equity * 100.0
            decision["risk_pct"] = booked_risk_pct

            if len(self.open_positions) >= int(SPEC["G3_MAX_POSITIONS"]):
                decision["reason"] = "MAX_POSITIONS"
                self.decisions.append(decision)
                continue
            if self._total_risk_pct(booked_risk_pct) > SPEC["G3_MAX_TOTAL_RISK_PCT"] + 1e-9:
                decision["reason"] = "MAX_TOTAL_RISK"
                self.decisions.append(decision)
                continue
            if self._currency_risk_pct(cand["symbol"], cand["side"],
                                       booked_risk_pct) > SPEC["G3_MAX_CURRENCY_RISK_PCT"] + 1e-9:
                decision["reason"] = "CURRENCY_EXPOSURE"
                self.decisions.append(decision)
                continue
            cluster, corr_state, warmup = self._cluster_risk_pct(
                cand, booked_risk_pct, at)
            decision["corr_state"] = corr_state
            decision["corr_warmup_days"] = warmup
            if corr_state == "CORR_WARMUP_UNKNOWN":
                if cluster > SPEC["G3_MAX_UNKNOWN_CLUSTER_PCT"] + 1e-9:
                    decision["reason"] = "UNKNOWN_CLUSTER_RISK"
                    self.decisions.append(decision)
                    continue
            elif cluster > SPEC["G3_MAX_CLUSTER_RISK_PCT"] + 1e-9:
                decision["reason"] = "CORR_CLUSTER_RISK"
                self.decisions.append(decision)
                continue

            decision["accepted"] = True
            self.open_positions.append({
                "symbol": cand["symbol"],
                "side": cand["side"],
                "risk_pct": booked_risk_pct,
                "risk_money": booked_risk_money,
                "result_r": cand["result_r"],
                "exit_time": cand["exit_time"],
            })
            self.decisions.append(decision)

        # flush anything still open at the end of the window
        if self.open_positions:
            last = max(p["exit_time"] for p in self.open_positions)
            self._close_due(last)
        return self.decisions

    def summary(self):
        accepted = [d for d in self.decisions if d["accepted"]]
        return {
            "candidates": len(self.decisions),
            "accepted": len(accepted),
            "rejected": len(self.decisions) - len(accepted),
            "final_equity": self.equity,
            "peak_equity": self.peak_equity,
            "max_equity_dd_pct": self.max_drawdown_pct,
            "final_dd_state": self.dd_state,
            "hard_stop_latched": self.hard_stop_latched,
        }


def simultaneous_candidate_counts(candidates):
    """How many candidates share each decision timestamp (Addendum F / N-3)."""
    counts = {}
    for c in candidates:
        counts[c["decision_time"]] = counts.get(c["decision_time"], 0) + 1
    return counts


def order_conflict_rejections(decisions):
    """Rejections that happened at a timestamp carrying several candidates.

    Addendum F requires these to be counted separately from ordinary
    rejections, because they are the ones the fixed tie-break order decided.
    """
    return [d for d in decisions
            if not d["accepted"] and d.get("simultaneous_candidates", 1) > 1]


# ----------------------------------------------------------------------
# Cross-check period selection (Addendum F, HIGH-2)
# ----------------------------------------------------------------------
def median(values):
    if not values:
        raise ValueError("median of an empty sample")
    s = sorted(values)
    n = len(s)
    if n % 2:
        return s[n // 2]
    return 0.5 * (s[n // 2 - 1] + s[n // 2])


def volatility_proxy_series(daily_rows):
    """Daily portfolio volatility proxy = median over the initial 7 pairs of
    D1 ATR14 / Close (Addendum F). `daily_rows` is a list of
    {date, values: {symbol: atr14_over_close}}.
    """
    series = []
    for row in daily_rows:
        vals = [v for sym, v in row["values"].items()
                if sym in UNIVERSE_ORDER_INITIAL7 and v is not None]
        if not vals:
            continue
        series.append({"date": row["date"], "proxy": median(vals)})
    return series


def select_crosscheck_periods(proxy_series, block_months=CROSSCHECK_BLOCK_MONTHS,
                              days_per_month=21):
    """Pick the highest and lowest volatility non-overlapping blocks.

    Selection is purely market-data driven: it never looks at strategy
    performance, so a favourable period cannot be chosen after the fact.
    Ties resolve to the earliest block so the choice is deterministic.
    """
    block_len = block_months * days_per_month
    if len(proxy_series) < block_len:
        raise ValueError("proxy series shorter than one %d month block" % block_months)
    blocks = []
    for start in range(0, len(proxy_series) - block_len + 1, block_len):
        window = proxy_series[start:start + block_len]
        blocks.append({
            "start_index": start,
            "end_index": start + block_len - 1,
            "start_date": window[0]["date"],
            "end_date": window[-1]["date"],
            "proxy_median": median([w["proxy"] for w in window]),
        })
    high = min(blocks, key=lambda b: (-b["proxy_median"], b["start_index"]))
    low = min(blocks, key=lambda b: (b["proxy_median"], b["start_index"]))
    return {"high_volatility_block": high, "low_volatility_block": low,
            "block_count": len(blocks)}


def representativeness_note(simultaneous_total):
    """N-3 disclosure. Never a PASS condition."""
    if simultaneous_total >= SIMULTANEOUS_CANDIDATE_DISCLOSURE_MIN:
        return {"limited_representativeness": False,
                "simultaneous_candidates": simultaneous_total,
                "note": "simultaneous candidate density is disclosed for this window"}
    return {"limited_representativeness": True,
            "simultaneous_candidates": simultaneous_total,
            "note": ("cross-check window carries fewer than %d simultaneous "
                     "candidates: tie-break order, Correlation Guard and "
                     "MaxPositions are exercised only weakly, so the "
                     "representativeness of this window is limited. This is a "
                     "disclosure, not a PASS condition."
                     % SIMULTANEOUS_CANDIDATE_DISCLOSURE_MIN)}


def crosscheck_gate(accept_agreement_pct, result_r_mean_abs_diff,
                    dd_state_agreement_pct, max_dd_abs_diff_pp):
    """Addendum F cross-check: four conditions, all of them, or FAIL."""
    conditions = {
        "accept_agreement": (accept_agreement_pct >= CROSSCHECK_ACCEPT_AGREEMENT_MIN,
                             accept_agreement_pct, CROSSCHECK_ACCEPT_AGREEMENT_MIN),
        "result_r_mean_abs_diff": (result_r_mean_abs_diff <= CROSSCHECK_RESULT_R_MAE_MAX,
                                   result_r_mean_abs_diff, CROSSCHECK_RESULT_R_MAE_MAX),
        "dd_state_agreement": (dd_state_agreement_pct >= CROSSCHECK_DD_STATE_AGREEMENT_MIN,
                               dd_state_agreement_pct, CROSSCHECK_DD_STATE_AGREEMENT_MIN),
        "max_dd_abs_diff_pp": (max_dd_abs_diff_pp <= CROSSCHECK_MAX_DD_ABS_DIFF_MAX,
                               max_dd_abs_diff_pp, CROSSCHECK_MAX_DD_ABS_DIFF_MAX),
    }
    passed = all(v[0] for v in conditions.values())
    return {
        "pass": passed,
        "conditions": {k: {"pass": v[0], "value": v[1], "threshold": v[2]}
                       for k, v in conditions.items()},
        "usable_as_g3_pass_evidence": passed,
        "on_fail": ("offline replay is not usable as G3 PASS evidence; return "
                    "to G1/G2 as a Change Request"),
    }
