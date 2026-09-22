"""
Addendum G (ISSUE-013 / CR-008) - canonical evaluation window.

No new split ratio is created. The two ratios pre-registered by v0.4 section
13.2 are the only ones that exist, and a dataset that falls between them is
trimmed to the smaller pre-registered window rather than given a bespoke one.

  >= 72 months : latest 72m  = 12m Final Holdout + 60m Development
                 Development = 36m Research IS + 24m Static OOS
  60 - 71      : latest 60m  = 12m Final Holdout + 48m Development
                 Development = 29m Research IS + 19m Static OOS
  < 60         : the G3 numerical gate cannot start

Everything older than the canonical window is excluded from every Gate
performance aggregation. It may only be used for data quality checks.

This module never touches Final Holdout data. It computes where the holdout
boundary lies so that the rest of the pipeline can stay on the near side of
it, and records that boundary in the manifest as dates only.
"""

MIN_MONTHS = 60

WINDOW_72 = {
    "canonical_months": 72,
    "final_holdout_months": 12,
    "development_months": 60,
    "research_is_months": 36,
    "static_oos_months": 24,
}

WINDOW_60 = {
    "canonical_months": 60,
    "final_holdout_months": 12,
    "development_months": 48,
    "research_is_months": 29,
    "static_oos_months": 19,
}

WF_TRAIN_MONTHS = 24
WF_TEST_MONTHS = 6
WF_STEP_MONTHS = 6


class DataIntakeError(ValueError):
    """Raised when the dataset cannot start a G3 numerical gate at all."""


def canonical_window(months_available):
    """Resolve the canonical evaluation window for a contiguous dataset.

    Returns a dict describing the window and the excluded oldest surplus.
    Raises DataIntakeError below the 60 month floor.
    """
    if not isinstance(months_available, int):
        raise DataIntakeError("months_available must be an integer month count")
    if months_available < MIN_MONTHS:
        raise DataIntakeError(
            "G3 numerical gate cannot start: %d months available, %d required"
            % (months_available, MIN_MONTHS))

    base = dict(WINDOW_72 if months_available >= 72 else WINDOW_60)
    base["months_available"] = months_available
    base["excluded_oldest_months"] = months_available - base["canonical_months"]
    # Development = Research IS (oldest part) then Static OOS, then Holdout.
    base["offsets_from_oldest_canonical_month"] = {
        "research_is_start": 0,
        "static_oos_start": base["research_is_months"],
        "final_holdout_start": base["development_months"],
    }
    base["boundary_note"] = boundary_note(months_available)
    return base


def boundary_note(months_available):
    """LOW-3: the 71 -> 72 month step changes how much data is used at all."""
    if 60 <= months_available <= 71:
        return ("canonical window is the latest 60 months; at 72 months the "
                "window switches to 72 and data usage is discontinuous. This "
                "boundary effect must be noted in any cross-version comparison.")
    if months_available >= 72:
        return ("canonical window is the latest 72 months; datasets of 60-71 "
                "months use the 60 month window, so cross-version comparisons "
                "across that boundary are discontinuous by design.")
    return "below the 60 month floor"


def walk_forward_folds(development_months):
    """WF folds inside the canonical Development window only (Addendum G).

    Surplus months excluded from the canonical window are never used to add
    a fold.
    """
    folds = []
    start = 0
    while start + WF_TRAIN_MONTHS + WF_TEST_MONTHS <= development_months:
        folds.append({
            "train_start_month": start,
            "train_end_month": start + WF_TRAIN_MONTHS,
            "test_start_month": start + WF_TRAIN_MONTHS,
            "test_end_month": start + WF_TRAIN_MONTHS + WF_TEST_MONTHS,
        })
        start += WF_STEP_MONTHS
    return folds


def build_manifest(months_available, data_start, data_end, feed_id, data_hash):
    """The data_intake_manifest required by Addendum G.

    `data_start` / `data_end` are ISO date strings for the whole dataset; the
    canonical window is expressed as month offsets from the newest month so
    that the record stays unambiguous without a calendar library.
    """
    window = canonical_window(months_available)
    excluded = window["excluded_oldest_months"]
    return {
        "manifest": "data_intake_manifest",
        "spec": "Master Specification v0.4 section 13.2 + v0.4.1a Addendum G",
        "feed_id": feed_id,
        "data_hash": data_hash,
        "dataset_start": data_start,
        "dataset_end": data_end,
        "months_available": months_available,
        "canonical_window": {
            "months": window["canonical_months"],
            "ends_at": data_end,
            "starts_months_before_end": window["canonical_months"],
        },
        "excluded_oldest_months": excluded,
        "excluded_from_gate_performance": excluded > 0,
        "segments": {
            "research_is_months": window["research_is_months"],
            "static_oos_months": window["static_oos_months"],
            "final_holdout_months": window["final_holdout_months"],
        },
        "walk_forward": {
            "train_months": WF_TRAIN_MONTHS,
            "test_months": WF_TEST_MONTHS,
            "step_months": WF_STEP_MONTHS,
            "fold_count": len(walk_forward_folds(window["development_months"])),
        },
        "final_holdout_access": "NONE",
        "boundary_note": window["boundary_note"],
    }
