"""Registry: generates all 50 synthetic repo specs (10 challenges x 5 sizes).

Each entry is a lazy generator function -- repos are only materialized when
requested, so listing the registry is instant.
"""

from __future__ import annotations

from typing import Callable

from .generator import SizeTier, SyntheticRepo
from .challenges import (
    basic_nav,
    import_chains,
    deep_hierarchy,
    name_collision,
    inheritance,
    dependency,
    test_mapping,
    dead_code,
    cross_cutting,
    api_surface,
    route_detection,
)


CHALLENGES: dict[str, Callable[[SizeTier], SyntheticRepo]] = {
    "basic_nav": basic_nav.generate,
    "import_chains": import_chains.generate,
    "deep_hierarchy": deep_hierarchy.generate,
    "name_collision": name_collision.generate,
    "inheritance": inheritance.generate,
    "dependency": dependency.generate,
    "test_mapping": test_mapping.generate,
    "dead_code": dead_code.generate,
    "cross_cutting": cross_cutting.generate,
    "api_surface": api_surface.generate,
    "route_detection": route_detection.generate,
}

ALL_SIZES = list(SizeTier)


def list_repo_ids() -> list[str]:
    """Return all repo IDs in the full matrix (challenge x size)."""
    return [f"{name}_{size.value}" for name in CHALLENGES for size in ALL_SIZES]


def generate_repo(challenge: str, size: SizeTier) -> SyntheticRepo:
    """Generate a single synthetic repo by challenge name and size."""
    if challenge not in CHALLENGES:
        raise ValueError(f"Unknown challenge: {challenge}. Choose from: {list(CHALLENGES)}")
    return CHALLENGES[challenge](size)


def generate_all(
    *,
    challenges: list[str] | None = None,
    sizes: list[SizeTier] | None = None,
) -> list[SyntheticRepo]:
    """Generate repos for the requested slice of the matrix.

    Args:
        challenges: Subset of challenge names (default: all).
        sizes: Subset of size tiers (default: all).

    Returns:
        List of SyntheticRepo objects ready for write_repo().
    """
    target_challenges = challenges or list(CHALLENGES)
    target_sizes = sizes or ALL_SIZES

    repos = []
    for name in target_challenges:
        if name not in CHALLENGES:
            raise ValueError(f"Unknown challenge: {name}")
        for sz in target_sizes:
            repos.append(CHALLENGES[name](sz))
    return repos


def challenge_names() -> list[str]:
    """Return all challenge names."""
    return list(CHALLENGES.keys())
