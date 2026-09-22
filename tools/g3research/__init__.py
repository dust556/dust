"""
G3 research instruments (offline).

Master Specification v0.4 + v0.4.1a Addendum. These modules are RESEARCH
INSTRUMENTS, not part of the live Expert Advisor: Addendum D states plainly
that the replay engine "はG3研究器具であり、実運用EAの一部ではない".

They are deterministic and side-effect free unless a manifest write is asked
for explicitly, so that any G3 result can be reproduced from the recorded
hashes alone.

Nothing here selects a parameter, tunes a threshold or optimises a result.
Every numeric gate in this package is pre-registered by v0.4 or v0.4.1a and
is refused the moment it would be changed after results were seen.
"""

__all__ = [
    "spec_constants",
    "data_intake",
    "portfolio_replay",
    "stress_replay",
    "oat_pipeline",
]
