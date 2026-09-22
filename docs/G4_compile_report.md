# G4 Compile Report

## Result

| gate | status | evidence |
|------|--------|----------|
| MQL5 compile (MetaEditor), section 21 | **NOT_RUN** | No MQL5 toolchain exists in this environment: no MetaEditor, no MetaTrader 5, no Wine. `which metaeditor` and a filesystem search return nothing. |
| MQL5 compile errors | **UNKNOWN** | Cannot be established without MetaEditor. |
| MQL5 compile warnings | **UNKNOWN** | Cannot be established without MetaEditor. |
| Static pre-compile check | **PASS** | `python3 tools/mql5_static_check.py` -> 13 files checked, 193 G3 symbols defined, 125 referenced, **0 issues**. |
| Host unit tests (pure logic) | **PASS** | `tests/run_unit_tests.sh` -> **142 assertions, 0 failures**, built with `g++ -std=c++17 -Wall -Wextra -Werror` (0 compiler warnings). |
| Integration tests (terminal) | **NOT_RUN** | Require MetaTrader 5; see `tests/integration_test_plan.md` (29 cases, all NOT_RUN). |

No compile result is claimed as PASS. Section 21 remains open until the EA is
built in MetaEditor; this is tracked as ISSUE-016 / CR-014.

## What was actually verified here

1. **Structural integrity of all 13 MQL5 files**
   (`tools/mql5_static_check.py`): balanced braces / parentheses / brackets
   with comment and string awareness, balanced `#if`/`#endif` nesting, present
   and matched include guards, every `#include` target resolving, and every
   `G3*` symbol that is called being defined somewhere in `src/`.

2. **Prohibited-construct scan**: Final Holdout references, martingale,
   averaging down, netting support, `WebRequest` (external realtime decision
   source) and optimiser helpers. 0 hits outside comments.

3. **Forming-bar discipline**: every `CopyClose` / `CopyOpen` / `CopyHigh` /
   `CopyLow` / `CopyBuffer` / `CopyRates` call that reads from shift 0 must
   carry an explicit `G3-CHECK: shift0-safe` justification in the four lines
   above it, or the check fails. Exactly one such call exists
   (`G3D1Returns()`, which copies index 0 only so that it can be skipped) and
   it is justified in the source.

4. **Executable verification of the specification arithmetic**: the pure
   sections of every module are compiled by the host C++ compiler through
   `tests/host/mql5_shim.h` and asserted by 142 test cases covering sections
   4.1, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 and 16.

## What the host harness does NOT prove

The shim is not a MetaTrader emulator. MQL5 constructs that C++ accepts
differently, and everything inside `#ifndef G3_HOST_TEST` blocks
(indicator handles, `CopyBuffer`, `OrderSend`, `FileOpen`, terminal global
variables, `PositionSelectByTicket`, the account mode guard), are **not**
covered. Those are exactly the parts that the MetaEditor compile and the
integration plan must clear.

## Reproducing this report

```sh
python3 tools/mql5_static_check.py     # structural + prohibition scan
tests/run_unit_tests.sh                # 142 assertions
python3 tools/compute_hashes.py        # manifests + source hashes
python3 tools/gen_log_schema.py        # regenerate schema/research_log_schema.md
python3 tools/gen_reason_codes.py      # regenerate schema/reason_codes.md
python3 tools/gen_unit_test_plan.py    # regenerate tests/unit_test_plan.md
```

## Next step for the compile gate

1. Copy `src/` into `MQL5/Experts/G3Research/`.
2. Compile `G3_ResearchEA.mq5` in MetaEditor.
3. Record every error and warning verbatim. Do not silence a warning; report it
   with its cause.
4. Record `sha256sum G3_ResearchEA.ex5` into `manifests/EA_hash.txt`.
