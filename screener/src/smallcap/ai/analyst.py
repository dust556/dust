"""Optional qualitative layer: a Claude review of the numeric evidence.

**What this is for.** The five conditions are mechanical, and mechanical
screens have a characteristic failure mode: they cannot tell the difference
between a gross margin rising because the product mix is shifting toward
software and one rising because the company reclassified support costs out of
cost of revenue. Both look identical in XBRL. A language model reading the
computed evidence can at least *name* which alternative explanations would
need ruling out.

**What this is not for.** It does not decide anything. It never changes a
verdict, a score, or a ranking -- it is attached to the result as commentary
and is clearly labelled as unverified in every report. The screen's output is
identical whether or not this layer runs.

Requires the ``anthropic`` package and credentials; without either, the run
continues and the review is simply absent.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from ..config import AIConfig
from ..models import ScreenResult

LOGGER = logging.getLogger("smallcap.ai")

SYSTEM_PROMPT = """\
You are assisting a quantitative equity research process. A rule-based screen \
has already computed the numbers; your job is to interpret them, not to \
recompute or override them.

Ground rules:
- Work only from the evidence given. You have no access to news, filings \
prose, or market commentary. If something cannot be determined from the \
numbers provided, say so explicitly rather than inferring it.
- Never invent a fact about the company: no product names, customers, \
management history, or events unless they appear in the evidence.
- Your most valuable output is naming the *alternative explanations* that \
would have to be ruled out before the numbers can be believed -- accounting \
reclassifications, acquisition-driven margin shifts, one-off tax effects, \
capitalised costs, and so on.
- Be concise and specific. Quote the figure you are reasoning about.
"""

USER_TEMPLATE = """\
Company: {ticker} ({name})
Screen verdict: {verdict}

Computed evidence:
{evidence}

Assess:
1. What could be driving the gross margin trend, and what would disconfirm \
the favourable reading?
2. Does the reinvestment rate look like genuine growth investment, and is \
there evidence the company can keep redeploying at this return?
3. What does the insider ownership figure support or fail to support about \
management alignment, given its stated basis?
4. Red flags visible in these numbers.
5. What a human analyst must verify from primary sources before acting.
"""

REVIEW_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Two or three sentences on what the numbers do and do not establish.",
        },
        "margin_driver": {
            "type": "string",
            "description": "Likely drivers of the gross margin trend and what would disconfirm them.",
        },
        "reinvestment_runway": {
            "type": "string",
            "description": "Whether reinvestment looks like real growth investment, and its durability.",
        },
        "alignment_quality": {
            "type": "string",
            "description": "What the insider ownership figure supports, given its basis and limits.",
        },
        "red_flags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concerns visible in the supplied numbers. Empty if none.",
        },
        "verification_needed": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific items to check against primary sources.",
        },
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "Confidence that the numbers support the screen's verdict.",
        },
    },
    "required": [
        "summary",
        "margin_driver",
        "reinvestment_runway",
        "alignment_quality",
        "red_flags",
        "verification_needed",
        "confidence",
    ],
    "additionalProperties": False,
}


class AnalystUnavailable(RuntimeError):
    """The AI layer cannot run (missing package or credentials)."""


def _build_evidence(result: ScreenResult) -> str:
    """Flatten the computed criterion detail into readable evidence.

    Only computed figures are passed. Nothing is summarised or rounded away,
    because the model's job is to reason about the numbers the screen actually
    used, not a prettier version of them.
    """
    blocks: List[str] = []
    for criterion in result.criteria:
        lines = [
            f"[{criterion.key}] {criterion.label}",
            f"  verdict: {criterion.verdict.value}",
        ]
        if criterion.threshold:
            lines.append(f"  threshold: {criterion.threshold}")
        if criterion.value is not None:
            lines.append(f"  value: {criterion.value}")
        for reason in criterion.reasons:
            lines.append(f"  - {reason}")
        if criterion.detail:
            detail = json.dumps(
                criterion.detail, indent=2, default=str, ensure_ascii=False
            )
            lines.append("  detail:")
            lines.extend(f"    {line}" for line in detail.splitlines())
        if criterion.missing:
            lines.append(f"  missing inputs: {', '.join(criterion.missing)}")
        blocks.append("\n".join(lines))
    if result.warnings:
        blocks.append("[data warnings]\n" + "\n".join(f"  - {w}" for w in result.warnings))
    return "\n\n".join(blocks)


class ClaudeAnalyst:
    """Reviews screened companies with Claude and attaches the result."""

    def __init__(self, config: AIConfig, client: Any = None):
        self.config = config
        self._client = client

    # ------------------------------------------------------------------
    def client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on env
            raise AnalystUnavailable(
                "the 'anthropic' package is not installed; "
                "run `pip install anthropic` or omit --ai"
            ) from exc
        try:
            # Resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or an
            # `ant auth login` profile, in that order.
            self._client = anthropic.Anthropic()
        except Exception as exc:  # noqa: BLE001
            raise AnalystUnavailable(f"could not construct an Anthropic client: {exc}") from exc
        return self._client

    # ------------------------------------------------------------------
    def review(self, result: ScreenResult) -> Optional[Dict[str, Any]]:
        """Return a structured review, or None if the call could not be made."""
        import anthropic  # local: the module is optional

        client = self.client()
        verdict = (
            "cleared all five conditions"
            if result.all_passed
            else f"cleared {result.passed_count} of {len(result.criteria)} conditions"
        )
        prompt = USER_TEMPLATE.format(
            ticker=result.ticker,
            name=result.name or "unknown",
            verdict=verdict,
            evidence=_build_evidence(result),
        )

        try:
            response = client.beta.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=SYSTEM_PROMPT,
                thinking={"type": "adaptive"},
                output_config={
                    "effort": self.config.effort,
                    "format": {"type": "json_schema", "schema": REVIEW_SCHEMA},
                },
                # Server-side fallback: if a safety classifier declines the
                # request, the API routes it to a suitable alternative model
                # rather than returning an unusable turn.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.BadRequestError as exc:
            LOGGER.warning("AI review rejected for %s: %s", result.ticker, exc)
            return None
        except anthropic.AuthenticationError:
            raise AnalystUnavailable("Anthropic credentials are missing or invalid")
        except anthropic.RateLimitError as exc:
            LOGGER.warning("AI review rate limited for %s: %s", result.ticker, exc)
            return None
        except anthropic.APIStatusError as exc:
            LOGGER.warning("AI review failed for %s: HTTP %s", result.ticker, exc.status_code)
            return None
        except anthropic.APIConnectionError as exc:
            LOGGER.warning("AI review unreachable for %s: %s", result.ticker, exc)
            return None

        # A refusal returns HTTP 200 with no usable content; check before
        # reading the body.
        if getattr(response, "stop_reason", None) == "refusal":
            LOGGER.warning("AI review refused for %s", result.ticker)
            return None

        review = _extract_json(response)
        if review is None:
            return None
        review["_model"] = getattr(response, "model", self.config.model)
        review["_generated"] = "claude"
        return review

    # ------------------------------------------------------------------
    def review_all(
        self, results: Sequence[ScreenResult]
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Review the top candidates, attaching each review in place."""
        reviewed: Dict[str, Optional[Dict[str, Any]]] = {}
        for result in list(results)[: self.config.max_candidates]:
            try:
                review = self.review(result)
            except AnalystUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("AI review errored for %s: %s", result.ticker, exc)
                review = None
            result.ai_review = review
            reviewed[result.ticker] = review
        return reviewed


def _extract_json(response: Any) -> Optional[Dict[str, Any]]:
    """Pull the structured object out of the response."""
    parsed = getattr(response, "parsed_output", None)
    if isinstance(parsed, dict):
        return parsed
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) != "text":
            continue
        try:
            value = json.loads(block.text)
        except (json.JSONDecodeError, AttributeError):
            continue
        if isinstance(value, dict):
            return value
    return None
