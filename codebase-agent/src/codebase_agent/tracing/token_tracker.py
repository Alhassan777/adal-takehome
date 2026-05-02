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
        self._llm_input = 0
        self._llm_output = 0
        self._llm_calls = 0
        # Session-level accumulators (never reset)
        self._session_input = 0
        self._session_output = 0
        self._session_calls = 0
        self._session_llm_calls = 0

    def record(
        self,
        tool_name: str,
        input_text: str,
        output_text: str,
        subtask_id: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        in_tok = input_tokens if input_tokens is not None else len(input_text) // 4
        out_tok = output_tokens if output_tokens is not None else len(output_text) // 4

        entry = {
            "tool_name": tool_name,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "subtask_id": subtask_id,
        }
        self._records.append(entry)
        self._by_tool[tool_name] += in_tok + out_tok
        self._total_input += in_tok
        self._total_output += out_tok
        self._session_input += in_tok
        self._session_output += out_tok
        self._session_calls += 1

        if subtask_id:
            self._by_subtask[subtask_id].append(entry)

    def record_llm_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str = "",
    ) -> None:
        """Record actual token usage returned by the LLM API response."""
        self._llm_input += prompt_tokens
        self._llm_output += completion_tokens
        self._llm_calls += 1
        self._total_input += prompt_tokens
        self._total_output += completion_tokens
        self._session_input += prompt_tokens
        self._session_output += completion_tokens
        self._session_calls += 1
        self._session_llm_calls += 1

        entry = {
            "tool_name": f"llm:{model}" if model else "llm",
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "subtask_id": None,
        }
        self._records.append(entry)
        self._by_tool[entry["tool_name"]] += prompt_tokens + completion_tokens

    def start_workflow(self) -> None:
        """Reset per-workflow counters. Session totals are preserved."""
        self._records.clear()
        self._by_tool.clear()
        self._by_subtask.clear()
        self._total_input = 0
        self._total_output = 0
        self._llm_input = 0
        self._llm_output = 0
        self._llm_calls = 0

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
        """Cumulative totals across all workflows in this session."""
        return TokenSummary(
            input_tokens=self._session_input,
            output_tokens=self._session_output,
            total_tokens=self._session_input + self._session_output,
            call_count=self._session_calls,
        )

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
