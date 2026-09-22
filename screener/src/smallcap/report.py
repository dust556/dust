"""Output formats: JSON, CSV and a human-readable Markdown report.

The reports are deliberately verbose about *why* each company landed where it
did. A screen that emits only a list of tickers is impossible to audit, and
an unauditable screen is one you end up trusting for the wrong reasons.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
from typing import Any, Dict, List, Optional, Sequence

from .criteria import CRITERION_KEYS
from .models import ScreenResult, Verdict
from .scoring import summarise

VERDICT_MARK = {
    Verdict.PASS: "PASS",
    Verdict.FAIL: "FAIL",
    Verdict.INSUFFICIENT_DATA: "n/a",
}


def _fmt(value: Optional[float], kind: str) -> str:
    if value is None:
        return ""
    if kind == "usd_bn":
        return f"{value / 1e9:.2f}"
    if kind == "pct":
        return f"{value * 100:.1f}%"
    if kind == "ratio":
        return f"{value:.2f}x"
    if kind == "score":
        return f"{value:.3f}"
    return str(value)


COLUMN_FORMAT = {
    "market_cap": "usd_bn",
    "gross_margin": "pct",
    "returns": "pct",
    "leverage": "ratio",
    "insider": "pct",
}


# ----------------------------------------------------------------------
def to_json(
    results: Sequence[ScreenResult],
    config: Optional[Dict[str, Any]] = None,
    ranked: Optional[Sequence[ScreenResult]] = None,
) -> str:
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "summary": summarise(results),
        "config": config,
        "ranking": [r.ticker for r in (ranked or [])],
        "results": [r.to_dict() for r in results],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def to_csv(results: Sequence[ScreenResult]) -> str:
    """One row per company, one column per criterion value plus its verdict."""
    buffer = io.StringIO()
    header = [
        "ticker",
        "name",
        "cik",
        "all_passed",
        "passed_count",
        "composite_score",
        "data_quality",
    ]
    for key in CRITERION_KEYS:
        header += [f"{key}_verdict", f"{key}_value"]
    header += ["error", "warnings"]
    writer = csv.writer(buffer)
    writer.writerow(header)

    for result in results:
        row = [
            result.ticker,
            result.name or "",
            result.cik or "",
            "yes" if result.all_passed else "no",
            result.passed_count,
            _fmt(result.composite_score, "score"),
            _fmt(result.data_quality, "score"),
        ]
        for key in CRITERION_KEYS:
            criterion = result.criterion(key)
            if criterion is None:
                row += ["", ""]
                continue
            row += [
                criterion.verdict.value,
                _fmt(criterion.value, COLUMN_FORMAT.get(key, "score")),
            ]
        row += [result.error or "", "; ".join(result.warnings)]
        writer.writerow(row)
    return buffer.getvalue()


def to_markdown(
    results: Sequence[ScreenResult],
    ranked: Sequence[ScreenResult],
    config: Optional[Dict[str, Any]] = None,
    as_of: Optional[str] = None,
    top: int = 25,
) -> str:
    stats = summarise(results)
    lines: List[str] = []
    lines.append("# US small-cap screen")
    lines.append("")
    lines.append(
        f"Generated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        + (f" | data as of {as_of}" if as_of else "")
    )
    lines.append("")

    lines.append("## Run summary")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| universe size | {stats['universe_size']} |")
    lines.append(f"| evaluated | {stats['evaluated']} |")
    lines.append(f"| fetch errors | {stats['fetch_errors']} |")
    lines.append(f"| passed all five conditions | {stats['passed_all']} |")
    if stats["pass_rate"] is not None:
        lines.append(f"| pass rate | {stats['pass_rate'] * 100:.2f}% |")
    lines.append("")

    if stats["failures_by_criterion"]:
        lines.append("### Where companies dropped out")
        lines.append("")
        lines.append("| condition | failed | undecidable |")
        lines.append("|---|---:|---:|")
        for key in CRITERION_KEYS:
            failed = stats["failures_by_criterion"].get(key, 0)
            undecided = stats["undecidable_by_criterion"].get(key, 0)
            lines.append(f"| {key} | {failed} | {undecided} |")
        lines.append("")
        lines.append(
            "> A high *undecidable* count is a data-coverage problem, not a "
            "finding about the companies."
        )
        lines.append("")

    lines.append("## Candidates")
    lines.append("")
    if not ranked:
        lines.append("No company cleared all five conditions in this run.")
        lines.append("")
    else:
        lines.append(
            "| # | ticker | name | score | mkt cap ($B) | gross margin | ROIC-WACC | debt/EBITDA | insider |"
        )
        lines.append("|---:|---|---|---:|---:|---:|---:|---:|---:|")
        for index, result in enumerate(ranked[:top], start=1):
            values = {key: result.criterion(key) for key in CRITERION_KEYS}
            lines.append(
                "| {i} | {t} | {n} | {s} | {mc} | {gm} | {rt} | {lv} | {ins} |".format(
                    i=index,
                    t=result.ticker,
                    n=(result.name or "")[:38],
                    s=_fmt(result.composite_score, "score"),
                    mc=_fmt(values["market_cap"].value if values["market_cap"] else None, "usd_bn"),
                    gm=_fmt(values["gross_margin"].value if values["gross_margin"] else None, "pct"),
                    rt=_fmt(values["returns"].value if values["returns"] else None, "pct"),
                    lv=_fmt(values["leverage"].value if values["leverage"] else None, "ratio"),
                    ins=_fmt(values["insider"].value if values["insider"] else None, "pct"),
                )
            )
        lines.append("")

    lines.append("## Per-company detail")
    lines.append("")
    for result in (ranked[:top] or []):
        lines.extend(_company_section(result))

    lines.append("---")
    lines.append("")
    lines.append(
        "This is a research screen, not investment advice. Every figure is "
        "derived from public filings and may be misclassified; see "
        "`docs/methodology.md` for the known limitations of each condition."
    )
    lines.append("")
    return "\n".join(lines)


def _company_section(result: ScreenResult) -> List[str]:
    lines = [f"### {result.ticker} - {result.name or ''}".rstrip()]
    lines.append("")
    if result.composite_score is not None:
        lines.append(
            f"Composite score **{result.composite_score:.3f}** | "
            f"data quality {(result.data_quality or 0) * 100:.0f}%"
        )
        lines.append("")
    for criterion in result.criteria:
        mark = VERDICT_MARK[criterion.verdict]
        lines.append(f"**{mark} - {criterion.label}**  ")
        if criterion.threshold:
            lines.append(f"threshold: `{criterion.threshold}`  ")
        for reason in criterion.reasons:
            lines.append(f"- {reason}")
        lines.append("")
    if result.warnings:
        lines.append("Data warnings:")
        for warning in result.warnings:
            lines.append(f"- {warning}")
        lines.append("")
    review = result.ai_review
    if review:
        lines.append("**Qualitative review (LLM-generated, unverified):**")
        lines.append("")
        for field in ("margin_driver", "reinvestment_runway", "alignment_quality"):
            if review.get(field):
                lines.append(f"- *{field.replace('_', ' ')}*: {review[field]}")
        if review.get("red_flags"):
            lines.append("- *red flags*:")
            for flag in review["red_flags"]:
                lines.append(f"  - {flag}")
        if review.get("verification_needed"):
            lines.append("- *verify before acting*:")
            for item in review["verification_needed"]:
                lines.append(f"  - {item}")
        if review.get("confidence"):
            lines.append(f"- *confidence*: {review['confidence']}")
        lines.append("")
    return lines


# ----------------------------------------------------------------------
def write_reports(
    out_dir: str,
    results: Sequence[ScreenResult],
    ranked: Sequence[ScreenResult],
    config: Optional[Dict[str, Any]] = None,
    as_of: Optional[str] = None,
) -> Dict[str, str]:
    """Write results.json, results.csv and report.md; return their paths."""
    os.makedirs(out_dir, exist_ok=True)
    paths = {
        "json": os.path.join(out_dir, "results.json"),
        "csv": os.path.join(out_dir, "results.csv"),
        "markdown": os.path.join(out_dir, "report.md"),
    }
    with open(paths["json"], "w", encoding="utf-8") as handle:
        handle.write(to_json(results, config=config, ranked=ranked))
    with open(paths["csv"], "w", encoding="utf-8", newline="") as handle:
        handle.write(to_csv(results))
    with open(paths["markdown"], "w", encoding="utf-8") as handle:
        handle.write(to_markdown(results, ranked, config=config, as_of=as_of))
    return paths


def format_console(result: ScreenResult) -> str:
    """One-company summary for terminal output."""
    lines = [f"{result.ticker}  {result.name or ''}".rstrip()]
    if result.error:
        lines.append(f"  ERROR: {result.error}")
        return "\n".join(lines)
    for criterion in result.criteria:
        mark = VERDICT_MARK[criterion.verdict]
        value = _fmt(criterion.value, COLUMN_FORMAT.get(criterion.key, "score"))
        lines.append(f"  [{mark:4s}] {criterion.label}: {value or '-'}")
        for reason in criterion.reasons:
            lines.append(f"         {reason}")
    if result.composite_score is not None:
        lines.append(f"  composite score: {result.composite_score:.3f}")
    return "\n".join(lines)
