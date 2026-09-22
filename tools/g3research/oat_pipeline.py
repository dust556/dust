"""
Addendum C (DEV-005 / CR-006R) - OAT, freeze, Walk-Forward, Static OOS.

The order is the control, not a convention:

  C1 baseline on Research IS
  C2 OAT one-at-a-time, Research IS ONLY, pre-registered neighbours only
  C3 family-level report, no automatic adoption of a better neighbour
  C4 freeze the baseline logic and parameters
  C5 Walk-Forward over the whole Development window, DIAGNOSTIC ONLY,
     one confirmatory run per (spec_hash, config_hash, data_hash)
  C6 Static OOS one-shot, only if nothing was changed after seeing WF

This module refuses the sequence violations rather than documenting them:
an OAT on anything but Research IS, a second confirmatory WF on the same
triple, a TECHNICAL_RERUN that quietly changed something, or a Static OOS
opened before WF has run.
"""
import json
import os

STAGES = ["C1_BASELINE_IS", "C2_OAT_IS", "C3_OAT_REPORT", "C4_FREEZE",
          "C5_WALK_FORWARD", "C6_STATIC_OOS"]

DATASET_RESEARCH_IS = "RESEARCH_IS"
DATASET_DEVELOPMENT = "DEVELOPMENT"
DATASET_STATIC_OOS = "STATIC_OOS"
DATASET_FINAL_HOLDOUT = "FINAL_HOLDOUT"

# Addendum C / N-2: where a parameter family may be exercised.
FAMILY_PAIR_LOCAL = "PAIR_LOCAL"
FAMILY_PORTFOLIO_SHARED = "PORTFOLIO_SHARED"

VENUE_SINGLE_PAIR_IS = "SINGLE_PAIR_RESEARCH_IS"
VENUE_OFFLINE_PORTFOLIO_REPLAY = "OFFLINE_PORTFOLIO_REPLAY_ON_RESEARCH_IS"


class PipelineOrderError(RuntimeError):
    """The requested step would break the Addendum C ordering."""


class HoldoutAccessError(RuntimeError):
    """Any attempt to reach Final Holdout before G5."""


def oat_venue(family_kind):
    """N-2: pair-local families run on a single pair's Research IS;
    families that depend on shared portfolio state run on the offline
    portfolio replay over Research IS."""
    if family_kind == FAMILY_PAIR_LOCAL:
        return VENUE_SINGLE_PAIR_IS
    if family_kind == FAMILY_PORTFOLIO_SHARED:
        return VENUE_OFFLINE_PORTFOLIO_REPLAY
    raise ValueError("unknown parameter family kind %r" % family_kind)


def assert_oat_dataset(dataset):
    """OAT is a local robustness diagnosis on Research IS and nowhere else."""
    if dataset == DATASET_FINAL_HOLDOUT:
        raise HoldoutAccessError("Final Holdout is never opened before G5")
    if dataset != DATASET_RESEARCH_IS:
        raise PipelineOrderError(
            "OAT runs on Research IS only; %s was requested" % dataset)
    return True


class WfIterationManifest:
    """N-1: the Walk-Forward iteration record.

    One confirmatory run per (spec_hash, config_hash, data_hash). A repeat is
    admissible only as a TECHNICAL_RERUN, which must carry a reason and
    evidence and must not change the parameters, the logic or the data
    window. LOW-4 flags every such entry for later G2/G3 sampling.
    """

    def __init__(self):
        self.entries = []

    def _confirmatory_for(self, spec_hash, config_hash, data_hash):
        return [e for e in self.entries
                if e["spec_hash"] == spec_hash
                and e["config_hash"] == config_hash
                and e["data_hash"] == data_hash
                and e["run_kind"] == "CONFIRMATORY"]

    def can_run_confirmatory(self, spec_hash, config_hash, data_hash):
        return not self._confirmatory_for(spec_hash, config_hash, data_hash)

    def record_confirmatory(self, version_id, spec_hash, config_hash, data_hash,
                            canonical_window, timestamp, result_summary,
                            cr_reference=None):
        if not self.can_run_confirmatory(spec_hash, config_hash, data_hash):
            raise PipelineOrderError(
                "a confirmatory Walk-Forward already exists for this "
                "spec/config/data triple; a repeat must be recorded as a "
                "TECHNICAL_RERUN")
        entry = {
            "run_kind": "CONFIRMATORY",
            "version_id": version_id,
            "spec_hash": spec_hash,
            "config_hash": config_hash,
            "data_hash": data_hash,
            "canonical_window": canonical_window,
            "timestamp": timestamp,
            "result_summary": result_summary,
            "cr_reference": cr_reference,
            "review_required": False,
        }
        self.entries.append(entry)
        return entry

    def record_technical_rerun(self, version_id, spec_hash, config_hash,
                               data_hash, canonical_window, timestamp,
                               reason, evidence, result_summary):
        """A rerun forced by infrastructure failure.

        Nothing about the run may differ from the confirmatory entry it
        repeats; if it does, this is a new experiment and is refused.
        """
        prior = self._confirmatory_for(spec_hash, config_hash, data_hash)
        if not prior:
            raise PipelineOrderError(
                "TECHNICAL_RERUN has no confirmatory run to repeat")
        if not reason or not evidence:
            raise PipelineOrderError(
                "TECHNICAL_RERUN requires both a reason and evidence (LOW-4)")
        if prior[0]["canonical_window"] != canonical_window:
            raise PipelineOrderError(
                "TECHNICAL_RERUN must not change the data window")
        entry = {
            "run_kind": "TECHNICAL_RERUN",
            "version_id": version_id,
            "spec_hash": spec_hash,
            "config_hash": config_hash,
            "data_hash": data_hash,
            "canonical_window": canonical_window,
            "timestamp": timestamp,
            "reason": reason,
            "evidence": evidence,
            "result_summary": result_summary,
            # LOW-4: sampled by a later G2/G3 review.
            "review_required": True,
        }
        self.entries.append(entry)
        return entry

    def review_queue(self):
        """LOW-4: every TECHNICAL_RERUN awaiting third-party confirmation."""
        return [e for e in self.entries if e.get("review_required")]

    def to_manifest(self):
        return {
            "manifest": "wf_iteration_manifest",
            "spec": "Master Specification v0.4.1a Addendum C (N-1, LOW-4)",
            "entries": list(self.entries),
            "technical_rerun_review_queue": self.review_queue(),
        }

    def write(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_manifest(), fh, indent=2)
            fh.write("\n")
        return os.path.abspath(path)


class OatPipeline:
    """Enforces the C1..C6 ordering."""

    def __init__(self):
        self.completed = []
        self.frozen = False
        self.wf_manifest = WfIterationManifest()
        self.static_oos_opened = False
        self.oos_contaminated = False

    def _require(self, stage):
        if stage in self.completed:
            raise PipelineOrderError("%s has already been completed" % stage)
        index = STAGES.index(stage)
        for earlier in STAGES[:index]:
            if earlier not in self.completed:
                raise PipelineOrderError(
                    "%s cannot run before %s" % (stage, earlier))

    def run_baseline_is(self):
        self._require("C1_BASELINE_IS")
        self.completed.append("C1_BASELINE_IS")

    def run_oat(self, family_kind, dataset):
        if "C1_BASELINE_IS" not in self.completed:
            raise PipelineOrderError("C2_OAT_IS cannot run before C1_BASELINE_IS")
        if self.frozen:
            raise PipelineOrderError("OAT is finished once the baseline is frozen")
        assert_oat_dataset(dataset)
        venue = oat_venue(family_kind)
        if "C2_OAT_IS" not in self.completed:
            self.completed.append("C2_OAT_IS")
        return venue

    def report_oat_families(self, families):
        """C3: the report is complete or it is not a report.

        Reporting only the families that looked good is a G3 FAIL under
        section 14.1, so a partial report is refused here.
        """
        if "C2_OAT_IS" not in self.completed:
            raise PipelineOrderError("no OAT has been run")
        missing = [f["family"] for f in families if not f.get("reported")]
        if missing:
            raise PipelineOrderError(
                "OAT family report is incomplete: %s" % ", ".join(missing))
        self.completed.append("C3_OAT_REPORT")
        return True

    def freeze_baseline(self):
        self._require("C4_FREEZE")
        self.frozen = True
        self.completed.append("C4_FREEZE")

    def run_walk_forward(self, version_id, spec_hash, config_hash, data_hash,
                         canonical_window, timestamp, result_summary):
        if not self.frozen:
            raise PipelineOrderError(
                "Walk-Forward is a post-freeze diagnostic; freeze first")
        entry = self.wf_manifest.record_confirmatory(
            version_id, spec_hash, config_hash, data_hash, canonical_window,
            timestamp, result_summary)
        if "C5_WALK_FORWARD" not in self.completed:
            self.completed.append("C5_WALK_FORWARD")
        return entry

    def adopt_walk_forward_parameter(self, *_args, **_kwargs):
        """Explicitly unavailable: WF never selects a parameter."""
        raise PipelineOrderError(
            "Walk-Forward is diagnostic only and must not select parameters "
            "or thresholds; raise a Change Request instead")

    def open_static_oos(self, spec_changed_after_wf):
        if "C5_WALK_FORWARD" not in self.completed:
            raise PipelineOrderError("Static OOS cannot be opened before WF")
        if spec_changed_after_wf:
            raise PipelineOrderError(
                "the specification changed after Walk-Forward: return to a "
                "Change Request, Static OOS stays sealed")
        if self.static_oos_opened:
            raise PipelineOrderError(
                "Static OOS is a one-shot confirmatory window; a second read "
                "is REPEAT_NONCONFIRMATORY and cannot support a PASS")
        self.static_oos_opened = True
        self.completed.append("C6_STATIC_OOS")
        return True

    def mark_change_after_oos(self, changed_domains):
        """Anything changed after the OOS was read contaminates that window."""
        blocking = {"entry", "exit", "score", "threshold", "risk_policy"}
        if self.static_oos_opened and blocking.intersection(set(changed_domains)):
            self.oos_contaminated = True
        return self.oos_contaminated
