"""Token-to-USD cost estimation per model."""

from ..models import CostEstimate, TokenSummary

MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50 / 1_000_000, 10.00 / 1_000_000),
    "gpt-4o-mini": (0.15 / 1_000_000, 0.60 / 1_000_000),
    "claude-sonnet": (3.00 / 1_000_000, 15.00 / 1_000_000),
    "claude-haiku": (0.25 / 1_000_000, 1.25 / 1_000_000),
}


class CostEstimator:
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model

    def estimate(self, token_summary: TokenSummary) -> CostEstimate:
        input_rate, output_rate = MODEL_PRICING.get(self.model, (0.0, 0.0))
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
