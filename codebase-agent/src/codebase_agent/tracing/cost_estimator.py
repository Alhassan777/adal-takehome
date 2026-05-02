"""Token-to-USD cost estimation per model."""

import logging

from ..config import MODEL_PRICING, OPENAI_MODEL
from ..models import CostEstimate, TokenSummary

logger = logging.getLogger("codebase_agent.cost")


class CostEstimator:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or OPENAI_MODEL

    def estimate(self, token_summary: TokenSummary) -> CostEstimate:
        input_rate, output_rate = MODEL_PRICING.get(self.model, (0.0, 0.0))
        if self.model and self.model not in MODEL_PRICING:
            logger.warning(
                "No pricing data for model %r; cost will report $0.00. "
                "Add it to MODEL_PRICING in config.py.",
                self.model,
            )
        input_cost = token_summary.input_tokens * input_rate
        output_cost = token_summary.output_tokens * output_rate

        return CostEstimate(
            input_cost_usd=round(input_cost, 6),
            output_cost_usd=round(output_cost, 6),
            total_cost_usd=round(input_cost + output_cost, 6),
            model=self.model,
        )

    def project_daily(self, token_summary: TokenSummary, queries_per_day: int = 1000) -> CostEstimate:
        single = self.estimate(token_summary)
        return CostEstimate(
            input_cost_usd=round(single.input_cost_usd * queries_per_day, 4),
            output_cost_usd=round(single.output_cost_usd * queries_per_day, 4),
            total_cost_usd=round(single.total_cost_usd * queries_per_day, 4),
            model=self.model,
            projected_daily_cost_usd=round(single.total_cost_usd * queries_per_day, 4),
        )
