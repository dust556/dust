#!/usr/bin/env python3
"""Generate tests/unit_test_plan.md from the CHECK() ids in test_main.cpp."""
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SRC = os.path.join(ROOT, "tests", "host", "test_main.cpp")
OUT = os.path.join(ROOT, "tests", "unit_test_plan.md")

SECTIONS = {
 "test_time_sync": "4.1 MTF time synchronisation, decision_tick, signal_id",
 "test_state_store": "10 StateStore, dual store reconciliation, exactly-once consume",
 "test_signal_ledger": "4.1 per-symbol signal ledger, exactly-once consume (DEV-003)",
 "test_dev_regressions": "regression cover for the conformance fixes DEV-001, 002, 004, 009-016",
 "test_patch2_regressions": "v0.4.1a Addendum A/B/E: STATE_UNCERTAIN protective management, audited manual recovery and state epochs, fakeout_3 / fakeout_6",
 "test_dd_state_machine": "10/11 drawdown state machine, hysteresis, latch, DailyEntryLock",
 "test_risk_and_lots": "9 stop placement, risk money, lot sizing, post-fill risk",
 "test_deviation": "13 PipSize, deviation computation and hard cap",
 "test_exits": "14/15 exit modes A/B/C, partial, trail, timeout, MFE/MAE",
 "test_portfolio": "12 portfolio limits, currency exposure, correlation guard",
 "test_signal_logic": "5/6/7/8 H4, M15, M5 and market quality scoring",
 "test_log_schema": "16 research log schema integrity",
}


def main():
    text = open(SRC, encoding="utf-8").read()
    groups, current = [], None
    for line in text.splitlines():
        m = re.match(r"static void (test_[a-z0-9_]+)\(\)", line)
        if m:
            current = (m.group(1), [])
            groups.append(current)
        c = re.search(r'CHECK\("([^"]+)"', line)
        if c and current:
            current[1].append(c.group(1))

    total = sum(len(g[1]) for g in groups)
    out = ["# Unit Test Plan (host, executable)", "",
           "Scope: the pure specification logic of the G3 Research EA, compiled",
           "from the same `src/*.mqh` files that MetaEditor compiles, through the",
           "MQL5 shim in `tests/host/mql5_shim.h`.", "",
           "Run: `tests/run_unit_tests.sh` (C++17 compiler only, no MetaTrader).",
           "The build uses `-Wall -Wextra -Werror`.", "",
           "Terminal-bound behaviour is **not** in scope here; see",
           "`tests/integration_test_plan.md`.", "",
           "Total assertions: **%d**." % total, ""]
    for name, ids in groups:
        out.append("## %s" % name)
        out.append("")
        out.append("Specification: %s" % SECTIONS.get(name, "-"))
        out.append("")
        out.append("| test id | assertion |")
        out.append("|---------|-----------|")
        for i in ids:
            parts = i.split(" ", 1)
            out.append("| `%s` | %s |" % (parts[0], parts[1] if len(parts) > 1 else ""))
        out.append("")
    open(OUT, "w", encoding="utf-8").write("\n".join(out))
    print("wrote %s (%d assertions in %d groups)" % (OUT, total, len(groups)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
