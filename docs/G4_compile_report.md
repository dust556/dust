# G4 Compile Report

## Result

| gate | status | evidence |
|------|--------|----------|
| MetaEditor compile (MQL5) | **PASS — 0 errors / 0 warnings** | Run by the operator on a machine with MetaEditor and reported on 2026-09-23. Not reproducible in this environment, which has no MQL5 toolchain, so the result is recorded with its provenance rather than claimed as locally verified. |
| Compiled `.ex5` SHA-256 (EA_hash) | **BOUND** | `7a51ce18f7ffc474bc615e688284de0441b6112f04ce8ea5691e3d77f5740a55` — 157,950 bytes, supplied by the operator on 2026-09-23 and bound to the source hash below with `tools/record_ea_hash.py`. |
| Static pre-compile check | **PASS** | `python3 tools/mql5_static_check.py` -> 13 files, 227 G3 symbols defined, 157 referenced, **0 issues**. |
| Host unit tests (pure MQL5 logic) | **PASS** | `tests/run_unit_tests.sh` -> **207 assertions, 0 failures**, built with `g++ -std=c++17 -Wall -Wextra -Wpedantic -Werror` (0 warnings). |
| Research instrument tests (offline) | **PASS** | `tests/run_python_tests.sh` -> **59 tests, 0 failures**. |
| Integration tests (MT5 terminal) | **NOT_RUN** | 35 cases in `tests/integration_test_plan.md`. |

## The change that the compile required

MetaEditor warns about the `#property version` string format, so one line
changed:

```
- #property version   "0.4"
+ #property version   "1.000"
```

That is the whole diff. It is metadata carried in the `.ex5` header and is
read by nothing in the strategy: no entry or exit rule, no threshold, no
risk figure, no Addendum behaviour and no research instrument depends on it.
The 207 host assertions and 59 research tests were re-run after the change
and are unchanged.

## The binary and what was checked on it

The compiled EA was supplied on 2026-09-23 and bound to this source tree.
What could be verified here, without an MQL5 toolchain:

* it carries the `EX5\x02` magic header of a genuine MQL5 compiled program,
  157,950 bytes;
* the clear-text header metadata reads `copyright "G3 Research"` and
  `version "1.000"`, matching `#property` in `src/G3_ResearchEA.mq5`;
* `"0.4"` is absent from that header, so the binary was built after the
  version fix, not before it.

The rest of an `.ex5` is packed, so this is corroboration that the binary
belongs to this source, not a proof that it was built from it byte for byte.
Only a rebuild on a machine with MetaEditor can establish that.

`manifests/ea_hash.value` sits outside the hashed groups on purpose, so
binding the binary did not disturb `source_hash`, `config_hash`,
`schema_hash` or `release_hash`. If the source changes again, the EA must be
recompiled and re-bound with:

```sh
python3 tools/record_ea_hash.py /path/to/G3_ResearchEA.ex5
python3 tools/compute_hashes.py
```

The binary itself is deliberately not committed: the repository stays source
plus manifests, and `EA_hash` is what ties a G3 run to the executable that
produced it.

## Line endings: the MetaEditor copy hashes differently, and that is expected

The operator's MetaEditor working copy of `src/G3_ResearchEA.mq5` was supplied
on 2026-09-23. It is **content-identical** to the repository file: 1441 lines,
same bytes once CRLF is normalised to LF, `#property version "1.000"` present.

| form | line endings | SHA-256 |
|---|---|---|
| repository (canonical) | LF | `e69558adde2af9ed81da3b2f67573876d85c521e60377e2dfa0988432e8aae71` |
| MetaEditor working copy | CRLF | `dfc71f9c74ea6b25d9029c3e0928c292cc3d20f94196848c12e9c0efd4ff28d5` |

`source_hash` is a byte hash of the files as the repository stores them, which
is LF. MetaEditor saves CRLF, so a checkout opened and saved in MetaEditor will
hash differently while being the same source. This is recorded here and in
`metaeditor_compile.compiled_working_copy` so that an auditor comparing digests
does not read a line-ending difference as source drift.

If a single byte-exact digest across both worlds is wanted, the hashing rule
can be changed to normalise newlines before hashing. That would re-issue
`source_hash` and `release_hash`, so it is left as an explicit decision rather
than done silently; `EA_hash` would remain valid either way, because the
compiled content is unchanged.

## Hashes of the compiled tree

```
source_hash  : fa748067870f2952e9d9a8cceaf801fa4c374a211c04b6a143c4eab9e525597f
config_hash  : 37c820c795a23d9c30a11b19d8bd811f0bbd0c255819b86695a1c8dd1d2ebe5e
schema_hash  : ea3f1e17364f26c73d5e1686db76d0eaec61bdfedf7f3151aa26bac3ac20a332
release_hash : ea649bdb88e3becbd697d1d08162679f8f7cc1a6d6d940284c14845fb981f4a8
spec_hash    : 229f29920ee411cf008442f56a1061583fc564ad50c979c32bf7996ada7ff965
addendum_hash: fa107ac25d161253511a69b620ef70dd66677406abb539ad8031de2b680aa40c
EA_hash      : 7a51ce18f7ffc474bc615e688284de0441b6112f04ce8ea5691e3d77f5740a55
```

All three hashes that section 13.2 requires in the OOS access manifest are
now available except `data_hash`, which waits on the feed (CR-009).

## What the offline gates actually prove

1. **Structural integrity of all 13 MQL5 files** (`tools/mql5_static_check.py`):
   balanced braces, parentheses and brackets with comment and string
   awareness, balanced `#if`/`#endif` nesting, present and matched include
   guards, every `#include` target resolving, and every `G3*` symbol that is
   called being defined somewhere in `src/`.

2. **Prohibited-construct scan**: Final Holdout references, martingale,
   averaging down, netting support, `WebRequest` and optimiser helpers. 0
   hits outside comments.

3. **Forming-bar discipline**: any `CopyClose` / `CopyOpen` / `CopyHigh` /
   `CopyLow` / `CopyBuffer` / `CopyRates` reading from shift 0 must carry an
   explicit `G3-CHECK: shift0-safe` justification, or the check fails.

4. **Executable verification of the specification arithmetic**: the pure
   sections of every module are compiled by the host C++ compiler through
   `tests/host/mql5_shim.h` and asserted by 207 test cases covering v0.4
   sections 4.1 through 16 and v0.4.1a Addendum A, B and E.

5. **The offline research instruments** (Addendum C, D, F, G) are asserted by
   59 further tests, including a constant-parity check that fails if the
   Python mirror of the drawdown bands, risk percentages and portfolio
   ceilings ever drifts from the MQL5 `#define`s.

## Reproducing this report

```sh
python3 tools/mql5_static_check.py     # structural + prohibition scan
tests/run_all_tests.sh                 # 207 host assertions + 59 research tests
python3 tools/compute_hashes.py        # manifests + hashes
```
