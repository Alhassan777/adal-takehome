"""Per-call and cumulative token accounting."""

from collections import defaultdict

from ..models import TokenHotspot, TokenSummary


class TokenTracker:
    def __init__(self) -> None:
        self._records: list[dict] = []
        self._by_tool: dict[str, int] = defaultdict(int)
        self._by_subtask: dict[str, list[dict]] = defaultdict(list)
        self._total_input = 0
        self._total_output = 0

    def record(
        self,
        tool_name: str,
        input_text: str,
        output_text: str,
        subtask_id: str | None = None,
    ) -> None:
        input_tokens = len(input_text) // 4
        output_tokens = len(output_text) // 4

        entry = {
            "tool_name": tool_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "subtask_id": subtask_id,
        }
        self._records.append(entry)
        self._by_tool[tool_name] += input_tokens + output_tokens
        self._total_input += input_tokens
        self._total_output += output_tokens

        if subtask_id:
            self._by_subtask[subtask_id].append(entry)

    def subtask_summary(self, subtask_id: str) -> TokenSummary:
        records = self._by_subtask.get(subtask_id, [])
        inp = sum(r["input_tokens"] for r in records)
        out = sum(r["output_tokens"] for r in records)
        by_tool: dict[str, int] = defaultdict(int)
        for r in records:
            by_tool[r["tool_name"]] += r["input_tokens"] + r["output_tokens"]
        return TokenSummary(
            input_tokens=inp,
            output_tokens=out,
            total_tokens=inp + out,
            call_count=len(records),
            by_tool=dict(by_tool),
        )

    def workflow_summary(self) -> TokenSummary:
        return TokenSummary(
            input_tokens=self._total_input,
            output_tokens=self._total_output,
            total_tokens=self._total_input + self._total_output,
            call_count=len(self._records),
            by_tool=dict(self._by_tool),
        )

    def session_summary(self) -> TokenSummary:
        return self.workflow_summary()

    def hotspots(self, top_n: int = 10) -> list[TokenHotspot]:
        total = self._total_input + self._total_output
        if total == 0:
            return []

        tool_counts: dict[str, int] = defaultdict(int)
        for r in self._records:
            tool_counts[r["tool_name"]] += 1

        items = sorted(self._by_tool.items(), key=lambda x: -x[1])
        result = []
        for tool_name, tokens in items[:top_n]:
            count = tool_counts[tool_name]
            result.append(TokenHotspot(
                tool_name=tool_name,
                total_tokens=tokens,
                call_count=count,
                avg_tokens_per_call=tokens / count if count > 0 else 0,
                pct_of_total=(tokens / total * 100) if total > 0 else 0,
            ))
        return result
