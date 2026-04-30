"""Ablation matrix configuration for benchmark evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from codebase_agent.config import ExecutionMode


class ConfigID(str, Enum):
    FULL_ADAPTIVE = "full_adaptive"
    FULL_RLM = "full_rlm"
    NO_LSP = "no_lsp"
    NO_SUMMARIES = "no_summaries"
    MINIMAL = "minimal"


@dataclass(frozen=True)
class AblationConfig:
    """A single evaluation configuration in the ablation matrix."""

    config_id: ConfigID
    mode: ExecutionMode
    use_lsp: bool
    use_summaries: bool
    description: str

    @property
    def name(self) -> str:
        return self.config_id.value


ABLATION_MATRIX: dict[ConfigID, AblationConfig] = {
    ConfigID.FULL_ADAPTIVE: AblationConfig(
        config_id=ConfigID.FULL_ADAPTIVE,
        mode=ExecutionMode.ADAPTIVE,
        use_lsp=True,
        use_summaries=True,
        description="Best-case adaptive (all features on)",
    ),
    ConfigID.FULL_RLM: AblationConfig(
        config_id=ConfigID.FULL_RLM,
        mode=ExecutionMode.RLM,
        use_lsp=True,
        use_summaries=True,
        description="Best-case RLM (all features on)",
    ),
    ConfigID.NO_LSP: AblationConfig(
        config_id=ConfigID.NO_LSP,
        mode=ExecutionMode.ADAPTIVE,
        use_lsp=False,
        use_summaries=True,
        description="Adaptive without Pyright LSP",
    ),
    ConfigID.NO_SUMMARIES: AblationConfig(
        config_id=ConfigID.NO_SUMMARIES,
        mode=ExecutionMode.ADAPTIVE,
        use_lsp=True,
        use_summaries=False,
        description="Adaptive without NL summaries",
    ),
    ConfigID.MINIMAL: AblationConfig(
        config_id=ConfigID.MINIMAL,
        mode=ExecutionMode.ADAPTIVE,
        use_lsp=False,
        use_summaries=False,
        description="Minimal baseline (tree-sitter + ripgrep only)",
    ),
}


ALL_CONFIGS: list[AblationConfig] = list(ABLATION_MATRIX.values())


def get_config(config_id: str | ConfigID) -> AblationConfig:
    """Retrieve an ablation config by ID string or enum."""
    if isinstance(config_id, str):
        config_id = ConfigID(config_id)
    return ABLATION_MATRIX[config_id]
