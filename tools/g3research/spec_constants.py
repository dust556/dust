"""
Single source of truth mirror for the numeric constants the offline
instruments share with the MQL5 Expert Advisor.

The offline portfolio replay has to apply exactly the same drawdown bands,
risk percentages and portfolio ceilings as the EA. Re-typing them here would
let the two drift apart silently, so every value is checked back against the
`#define` in `src/*.mqh` and a mismatch is a hard error.
"""
import os
import re

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SRC = os.path.join(ROOT, "src")

# Master Specification v0.4 sections 8, 9, 11.1, 11.3, 11.4.
# Mirrored from src/*.mqh; verify_against_sources() proves they agree.
SPEC = {
    "G3_VOL_RATIO_MIN": 0.80,
    "G3_VOL_RATIO_MAX": 1.80,
    "G3_VOL_RATIO_BLOCK": 2.50,
    "G3_SPREAD_RATIO_POINT": 0.12,
    "G3_SPREAD_RATIO_ZERO": 0.20,
    "G3_SCORE_MAX": 8,
    "G3_RESTRICTED_SCORE_TH": 6,
    "G3_SL_MIN_ATR": 1.00,
    "G3_SL_MAX_ATR": 2.50,
    "G3_RISK_PCT_NORMAL": 0.50,
    "G3_RISK_PCT_MODERATE": 0.25,
    "G3_RISK_PCT_RESTRICTED": 0.10,
    "G3_DD_MODERATE_ENTER": 6.0,
    "G3_DD_RESTRICTED_ENTER": 8.0,
    "G3_DD_HARD_STOP_ENTER": 10.0,
    "G3_DD_NORMAL_RECOVER": 5.0,
    "G3_DD_MODERATE_RECOVER": 7.0,
    "G3_DD_MANUAL_RESET_MAX": 9.0,
    "G3_DAILY_LOCK_RATIO": 0.98,
    "G3_POST_FILL_RISK_MAX": 1.05,
    "G3_MAX_POSITIONS": 3,
    "G3_MAX_TOTAL_RISK_PCT": 1.50,
    "G3_MAX_CURRENCY_RISK_PCT": 1.00,
    "G3_MAX_CLUSTER_RISK_PCT": 1.00,
    "G3_MAX_UNKNOWN_CLUSTER_PCT": 0.75,
    "G3_CORR_THRESHOLD": 0.70,
    "G3_CORR_REQUIRED_BARS": 60,
    "G3_FAKEOUT_N3": 3,
    "G3_FAKEOUT_N6": 6,
}

DEFINE_RE = re.compile(r"^\s*#define\s+(G3_[A-Z0-9_]+)\s+([-+]?[0-9]*\.?[0-9]+)\s*(?://.*)?$", re.M)


def read_source_defines():
    """Every numeric #define found in src/*.mqh, as {name: float}."""
    found = {}
    for name in sorted(os.listdir(SRC)):
        if not name.endswith((".mqh", ".mq5")):
            continue
        with open(os.path.join(SRC, name), encoding="utf-8") as fh:
            for m in DEFINE_RE.finditer(fh.read()):
                found[m.group(1)] = float(m.group(2))
    return found


def verify_against_sources():
    """Raise ValueError on any drift between this mirror and the EA sources."""
    found = read_source_defines()
    problems = []
    for key, value in sorted(SPEC.items()):
        if key not in found:
            problems.append("%s is not defined in src/" % key)
        elif abs(found[key] - float(value)) > 1e-12:
            problems.append("%s: python %s vs src %s" % (key, value, found[key]))
    if problems:
        raise ValueError("spec constant drift: " + "; ".join(problems))
    return True


def risk_pct_for_state(dd_state):
    return {
        "NORMAL": SPEC["G3_RISK_PCT_NORMAL"],
        "MODERATE": SPEC["G3_RISK_PCT_MODERATE"],
        "RESTRICTED": SPEC["G3_RISK_PCT_RESTRICTED"],
        "HARD_STOP": 0.0,
        "STATE_UNCERTAIN": 0.0,
    }[dd_state]


def effective_score_threshold(input_threshold, dd_state):
    """Spec 8.1 / 11.1 / appendix A: RESTRICTED forces 6."""
    if dd_state == "RESTRICTED":
        return max(int(SPEC["G3_RESTRICTED_SCORE_TH"]), int(input_threshold))
    return int(input_threshold)
