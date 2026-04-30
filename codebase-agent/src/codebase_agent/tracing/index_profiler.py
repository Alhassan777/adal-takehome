"""Index build/load timing and cache metrics."""

import time

from ..models import IndexProfile


class IndexProfiler:
    def __init__(self) -> None:
        self._profiles: list[IndexProfile] = []
        self._current_start: float = 0

    def start_build(self) -> None:
        self._current_start = time.perf_counter()

    def end_build(
        self,
        file_count: int,
        symbol_count: int,
        import_count: int,
        index_size_bytes: int,
        cache_hit: bool,
        scan_ms: float = 0,
        parse_ms: float = 0,
        graph_ms: float = 0,
        slowest_files: list[tuple[str, float]] | None = None,
    ) -> IndexProfile:
        total_ms = (time.perf_counter() - self._current_start) * 1000
        profile = IndexProfile(
            scan_duration_ms=scan_ms,
            parse_duration_ms=parse_ms,
            graph_build_duration_ms=graph_ms,
            total_duration_ms=total_ms,
            file_count=file_count,
            symbol_count=symbol_count,
            import_count=import_count,
            index_size_bytes=index_size_bytes,
            cache_hit=cache_hit,
            slowest_files=slowest_files or [],
        )
        self._profiles.append(profile)
        return profile

    def last_profile(self) -> IndexProfile | None:
        return self._profiles[-1] if self._profiles else None
