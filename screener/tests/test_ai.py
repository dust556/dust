"""The optional Claude layer: it must never change a screening verdict."""

import sys
import types
import unittest
from typing import Any, Dict

from smallcap.ai.analyst import REVIEW_SCHEMA, ClaudeAnalyst, _build_evidence, _extract_json
from smallcap.config import AIConfig
from smallcap.models import CriterionResult, ScreenResult, Verdict


class FakeBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeResponse:
    def __init__(self, text=None, parsed=None, stop_reason="end_turn"):
        self.content = [FakeBlock(text)] if text is not None else []
        self.parsed_output = parsed
        self.stop_reason = stop_reason
        self.model = "claude-opus-5"


class FakeClient:
    """Captures the request instead of calling the API."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []
        self.beta = types.SimpleNamespace(
            messages=types.SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


REVIEW = {
    "summary": "Margins are rising but the driver is not determinable here.",
    "margin_driver": "Possible mix shift; a reclassification would look identical.",
    "reinvestment_runway": "Capex is well above D&A.",
    "alignment_quality": "18% on a lower-bound basis is supportive.",
    "red_flags": ["Share count is a cover-page figure."],
    "verification_needed": ["Confirm insider ownership against the DEF 14A."],
    "confidence": "medium",
}


def sample_result() -> ScreenResult:
    return ScreenResult(
        ticker="IDEAL",
        name="Ideal Compounder Inc.",
        all_passed=True,
        passed_count=5,
        criteria=[
            CriterionResult(
                key="gross_margin",
                label="Gross margin",
                verdict=Verdict.PASS,
                value=0.53,
                threshold="gross margin >= 40%",
                detail={"slope_per_year": 0.012},
                reasons=["gross margin 53.0% vs 40% threshold"],
            )
        ],
        warnings=["share count is stale"],
    )


class TestEvidence(unittest.TestCase):
    def test_evidence_includes_verdicts_thresholds_and_detail(self):
        text = _build_evidence(sample_result())
        self.assertIn("[gross_margin]", text)
        self.assertIn("verdict: PASS", text)
        self.assertIn("slope_per_year", text)
        self.assertIn("share count is stale", text)


class TestExtraction(unittest.TestCase):
    def test_prefers_the_parsed_output(self):
        self.assertEqual(_extract_json(FakeResponse(parsed=REVIEW)), REVIEW)

    def test_falls_back_to_parsing_the_text_block(self):
        import json

        self.assertEqual(_extract_json(FakeResponse(text=json.dumps(REVIEW))), REVIEW)

    def test_unparseable_content_yields_none(self):
        self.assertIsNone(_extract_json(FakeResponse(text="not json at all")))


class TestAnalyst(unittest.TestCase):
    def setUp(self):
        # The analyst imports `anthropic` for its exception types; provide a
        # stand-in so the layer can be tested without the package installed.
        self.installed = "anthropic" not in sys.modules
        if self.installed:
            module = types.ModuleType("anthropic")
            for name in (
                "BadRequestError",
                "AuthenticationError",
                "RateLimitError",
                "APIStatusError",
                "APIConnectionError",
            ):
                setattr(module, name, type(name, (Exception,), {}))
            sys.modules["anthropic"] = module
        self.anthropic = sys.modules["anthropic"]

    def tearDown(self):
        if self.installed:
            del sys.modules["anthropic"]

    def test_review_returns_the_structured_object(self):
        client = FakeClient(FakeResponse(parsed=REVIEW))
        analyst = ClaudeAnalyst(AIConfig(), client=client)
        review = analyst.review(sample_result())
        self.assertEqual(review["confidence"], "medium")
        self.assertEqual(review["_generated"], "claude")

    def test_request_pins_the_model_schema_and_effort(self):
        client = FakeClient(FakeResponse(parsed=REVIEW))
        config = AIConfig(model="claude-opus-5", effort="high")
        ClaudeAnalyst(config, client=client).review(sample_result())
        call = client.calls[0]
        self.assertEqual(call["model"], "claude-opus-5")
        self.assertEqual(call["output_config"]["effort"], "high")
        self.assertEqual(
            call["output_config"]["format"]["schema"], REVIEW_SCHEMA
        )
        self.assertEqual(call["thinking"], {"type": "adaptive"})

    def test_refusal_returns_none_rather_than_garbage(self):
        client = FakeClient(FakeResponse(text=None, stop_reason="refusal"))
        self.assertIsNone(ClaudeAnalyst(AIConfig(), client=client).review(sample_result()))

    def test_api_errors_degrade_to_no_review(self):
        for name in ("BadRequestError", "RateLimitError", "APIConnectionError"):
            client = FakeClient(error=getattr(self.anthropic, name)("failed"))
            with self.assertLogs("smallcap.ai", level="WARNING"):
                review = ClaudeAnalyst(AIConfig(), client=client).review(sample_result())
            self.assertIsNone(review, name)

    def test_review_all_respects_the_candidate_cap(self):
        client = FakeClient(FakeResponse(parsed=REVIEW))
        config = AIConfig(max_candidates=2)
        results = []
        for index in range(5):
            result = sample_result()
            result.ticker = f"TKR{index}"
            results.append(result)
        reviewed = ClaudeAnalyst(config, client=client).review_all(results)
        self.assertEqual(sorted(reviewed), ["TKR0", "TKR1"])
        self.assertEqual(len(client.calls), 2)
        # Candidates past the cap are left without a review, not given a stale one.
        self.assertIsNone(results[4].ai_review)

    def test_review_never_alters_the_verdict_or_score(self):
        client = FakeClient(FakeResponse(parsed=REVIEW))
        result = sample_result()
        before = (result.all_passed, result.passed_count, result.composite_score)
        ClaudeAnalyst(AIConfig(), client=client).review_all([result])
        after = (result.all_passed, result.passed_count, result.composite_score)
        self.assertEqual(before, after)
        self.assertIsNotNone(result.ai_review)


if __name__ == "__main__":
    unittest.main()
