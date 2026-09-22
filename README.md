# G3 Research EA

MetaTrader 5 / MQL5 research Expert Advisor implementing **Master
Specification v0.4** for the purpose of generating G3 numerical research data
(IS / OOS / Walk-Forward / Stress / Monte-Carlo / sensitivity).

This EA is a measurement instrument, not a trading product. It makes no
judgement about profitability, performs no optimisation, and never touches
Final Holdout data.

## Layout

| path | contents |
|------|----------|
| `src/` | the EA and its modules (one module per specification area) |
| `config/` | MT5 `.set` files for the registered G3 inputs |
| `schema/` | research log schema and reason codes (generated from source) |
| `tests/` | executable host unit tests, integration test plan, scenarios |
| `manifests/` | build manifest and source / config / EA hashes |
| `docs/` | implementation mapping, limitations, ISSUEs and CHANGE REQUESTs |
| `tools/` | static checker, hash tool, documentation generators |

## Status

* Compile (MetaEditor): **NOT_RUN** - no MQL5 toolchain in this environment.
* Static pre-compile check: **PASS** (0 issues).
* Host unit tests: **PASS** (142 assertions, 0 failures).
* Integration tests: **NOT_RUN** - require MetaTrader 5.
* G3 data run: **not started**; the required feeds and account parameters were
  not supplied, and no result has been fabricated.

See `docs/G4_compile_report.md` and `docs/change_requests.md`.

## Running the checks

```sh
python3 tools/mql5_static_check.py
tests/run_unit_tests.sh
python3 tools/compute_hashes.py
```

## Deployment note

One EA instance per symbol, all sharing the same magic number. The decision
point defined by section 4.1 (the first tick of a new M5 bar) is only
observable for the chart symbol in MQL5. Portfolio limits are evaluated across
instances through the terminal position list and a global-variable lock.
See ISSUE-003 for the consequence this has for portfolio-level backtesting.
