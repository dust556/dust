# G4 Patch-1 Frozen Candidate

This is a freeze record, not a release. The code below is frozen pending the
G1 addendum and the G2 audit of that addendum. No further implementation is
to be added to this tree.

| item | value |
|---|---|
| Freeze label | **G4 Patch-1 Frozen Candidate** |
| Frozen from branch | `claude/g3-research-ea-cp6pc7` |
| Base commit | `f5abed8` (the freeze record itself is committed on top) |
| Spec authority | Master Specification v0.4 |
| Status | **FROZEN_WAITING_FOR_G1_G2_ADDENDUM** |

## Verification performed immediately before the freeze

| gate | result |
|---|---|
| Static pre-compile check (`tools/mql5_static_check.py`) | **0 issues** — 13 files, 209 G3 symbols defined, 140 referenced |
| Host build (`g++ -std=c++17 -Wall -Wextra -Wpedantic -Werror -O1`) | **0 warnings, 0 errors** |
| Host unit tests (`tests/run_unit_tests.sh`) | **179 assertions, 0 failures** |
| MetaEditor compile | **NOT_RUN** — no MQL5 toolchain in this environment (ISSUE-016 / CR-014) |
| MT5 integration tests | **NOT_RUN** — 29 cases planned in `tests/integration_test_plan.md` |
| Final Holdout | **untouched** — not introduced, not referenced, not computed, not visualised; the static check scans for it |

## Hashes of the frozen tree

```
source_hash  : 50e42c6af071ea65b407680aad45acf86a682784684325ed9a6ddfa2c3462cb1
config_hash  : 37c820c795a23d9c30a11b19d8bd811f0bbd0c255819b86695a1c8dd1d2ebe5e
schema_hash  : 01c3b3ff4cab5d507cdf8791c789f3803e8ad3dfb2d599e13cf068f8cdefe5e4
release_hash : 72158a82e3122ae386d62f36094465943df3303fedf88ee28566f0670b6e51cc
spec_hash    : 229f29920ee411cf008442f56a1061583fc564ad50c979c32bf7996ada7ff965
EA_hash      : PENDING_METAEDITOR_COMPILE
```

`release_hash` is the aggregate over `src/`, `config/` and `schema/`.
`docs/` and `manifests/` are deliberately outside the hashed groups, so this
freeze record can be added without perturbing the hashes it states.

Authority document hashes (verified against the table printed inside the G3
research start record):

```
master_specification_v0.4 : 229f29920ee411cf008442f56a1061583fc564ad50c979c32bf7996ada7ff965
g2_re_audit_report_v0.4   : 7d17353844c88030622638abd10c5b475c7f74eea26936b21c87e8c15d64fbeb
g3_research_start_record  : d068cdc797a6708629c21df2a085afa6a8a3d46b388f200340e856e1376ab82c
```

## What this freeze contains

Patch-1 fixed twelve conformance deviations against Master Specification v0.4
(`docs/G4_patch_report.md`): DEV-001, DEV-002, DEV-003, DEV-004, DEV-008,
DEV-009, DEV-010, DEV-011, DEV-012, DEV-013, DEV-015, DEV-016.

## What is deliberately NOT in this freeze

These remain open and must not be implemented before the G1 addendum has been
issued and audited by G2. No placeholder, no partial implementation and no
guessed definition was added for any of them.

| id | open question |
|----|---------------|
| DEV-005 / CR-006R | How the spec 16 OAT sensitivity is to be executed (EA inputs vs. one build per OAT point) |
| DEV-006 / CR-015 | Where the spec 13.5 execution stress (spread multiplier, adverse slippage) is realised |
| DEV-007 / CR-016 | The exact definition of `fakeout_3` / `fakeout_6` ("反転SL等") |
| ISSUE-003 / CR-003 | The multi-symbol portfolio verification method under the MT5 one-expert tester |
| ISSUE-013 / CR-008 | The fixed data split for a 61-71 month dataset |
| DEV-014 | Whether open positions are managed under STATE_UNCERTAIN (appendix A vs. section 11.2) |
| DEV-017 | The manual recovery procedure out of STATE_UNCERTAIN |

Still open for reasons outside the code:

| id | blocker |
|----|---------|
| ISSUE-016 / CR-014 | MetaEditor compile gate and the MT5 integration run |
| ISSUE-012 / CR-009 | Primary and second tick feed, symbol specifications, initial equity, account currency, cost information |

## Unfreezing

A later patch must state which G1 addendum clause and which G2 audit result
authorises it, re-run the three gates above, and recompute every hash.
