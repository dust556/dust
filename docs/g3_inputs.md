# G3 Input Surface

Master Specification v0.4 section 17: only values that G3 has pre-registered
are exposed. There is deliberately **no** optimiser-friendly surface: no step
ranges, no numeric strategy constants, no search helper. Every threshold of
sections 5-15 is a compile-time constant in the module that owns it.

## Registered research inputs

| input | type | admissible values | default | spec |
|-------|------|-------------------|---------|------|
| `InpScoreThreshold` | `ENUM_G3_SCORE_THRESHOLD` | 4, 5, 6 only | 5 (baseline) | 8 |
| `InpExitMode` | `ENUM_G3_EXIT_MODE` | A(0), B(1), C(2) | A | 14 |
| `InpTimeout` | `ENUM_G3_TIMEOUT` | OFF(0), 6, 12, 18, 24 M5 bars | OFF | 15 |

The enumerations make an out-of-range value unselectable in the tester, which
is what keeps the sweep to the registered grid.

## Execution stress inputs

Neutral by default. A non-zero value is a stress scenario, never a strategy
change.

| input | type | default | effect |
|-------|------|---------|--------|
| `InpStressExtraSpreadPoints` | `int` | 0 | added to the observed spread before the SpreadRatio filter and the deviation computation |
| `InpStressCommissionPerLot` | `double` | 0.0 | account-currency commission per 1.00 lot, converted to price for the cost-adjusted break-even |

Slippage stress is **not** implemented: an EA cannot inject slippage into the
MT5 strategy tester. See ISSUE-006 / L-06.

## Safety stress inputs

**None.** The safety constants of sections 9-12 (risk percentages, drawdown
thresholds, hysteresis levels, MaxPositions, risk ceilings, correlation
threshold) are fixed by the specification and are not parameterised. The
pre-registered safety-stress list was not supplied; see CR-006.

## OAT parameters

The one-at-a-time target list was not supplied. Until CR-006 is answered, the
OAT surface is exactly the three registered research inputs above.

## Research infrastructure inputs

Not strategy parameters; they do not affect a single decision.

| input | type | default | purpose |
|-------|------|---------|---------|
| `InpMagic` | `long` | 940400 | position ownership and cross-instance portfolio scope |
| `InpRunId` | `string` | "R000" | research log file tag |
| `InpManualHardStopReset` | `bool` | false | performs one audited manual HARD_STOP reset at start-up, admissible only below 9% drawdown (section 10) |

## Configuration files

| file | purpose |
|------|---------|
| `config/baseline.set` | Master Specification v0.4 baseline (threshold 5, exit A, timeout OFF) |
| `config/score_4.set` | ScoreThreshold sweep point 4 |
| `config/score_5.set` | ScoreThreshold sweep point 5 |
| `config/score_6.set` | ScoreThreshold sweep point 6 |
