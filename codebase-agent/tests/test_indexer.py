"""Tests for indexer.py."""

import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codebase_agent.core import indexer
from codebase_agent.core.indexer import build_index, save_index_to_disk, load_index
from codebase_agent.config import INDEX_DIR, INDEX_FILE

SAMPLE_REPO = str(Path(__file__).parent.parent / "examples" / "sample_repo")


def test_build_index_collects_files():
    idx = build_index(SAMPLE_REPO)
    assert len(idx.files) >= 3


def test_build_index_collects_symbols():
    idx = build_index(SAMPLE_REPO)
    names = [s.name for s in idx.symbols]
    assert "User" in names
    assert "create_user" in names


def test_build_index_collects_imports():
    idx = build_index(SAMPLE_REPO)
    assert len(idx.imports) > 0


def test_build_index_builds_name_reference_map():
    idx = build_index(SAMPLE_REPO)
    assert isinstance(idx.name_reference_map, dict)


def test_save_and_load_roundtrip():
    idx = build_index(SAMPLE_REPO)
    cache_dir = Path(SAMPLE_REPO) / INDEX_DIR
    cache_dir.mkdir(exist_ok=True)
    index_path = str(cache_dir / INDEX_FILE)

    save_index_to_disk(idx, SAMPLE_REPO)
    loaded = load_index(index_path)

    assert loaded.root_path == idx.root_path
    assert len(loaded.files) == len(idx.files)
    assert len(loaded.symbols) == len(idx.symbols)

    # Cleanup
    shutil.rmtree(str(cache_dir), ignore_errors=True)


def test_incremental_reindex():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(SAMPLE_REPO)
        dst = Path(tmp)
        for f in src.iterdir():
            if f.is_file():
                shutil.copy(f, dst / f.name)

        idx1 = build_index(tmp)
        count1 = len(idx1.symbols)

        # Modify one file
        test_file = dst / "utils.py"
        content = test_file.read_text()
        test_file.write_text(content + "\n\ndef new_function(): pass\n")

        idx2 = build_index(tmp)
        assert len(idx2.symbols) == count1 + 1

        # Cleanup
        shutil.rmtree(str(dst / INDEX_DIR), ignore_errors=True)


def test_cached_index_invalidates_when_file_changes():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "module.py"
        source.write_text("def old_name():\n    return 1\n")

        idx = build_index(tmp)
        save_index_to_disk(idx, tmp)
        assert indexer.is_index_cache_fresh(tmp, idx)

        source.write_text("def new_name():\n    return 2\n")
        assert not indexer.is_index_cache_fresh(tmp, idx)

        indexer._session_index = None
        rebuilt = indexer.get_or_build_index(tmp)
        names = {s.name for s in rebuilt.symbols}
        assert "new_name" in names
        assert "old_name" not in names


def test_watcher_update_refreshes_files_and_reference_maps():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.py").write_text("def used():\n    return 1\n")

        idx = build_index(tmp)
        save_index_to_disk(idx, tmp)

        new_file = root / "b.py"
        new_file.write_text("from a import used\n\ndef caller():\n    return used()\n")
        indexer._update_index_for_file(idx, str(new_file), root)

        assert any(f.path == "b.py" for f in idx.files)
        assert any(s.name == "caller" for s in idx.symbols)
        assert "b.py" in idx.name_reference_map.get("used", [])
        assert indexer.is_index_cache_fresh(tmp, idx)
