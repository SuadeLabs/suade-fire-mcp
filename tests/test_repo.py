from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from fire_mcp import repo


def _load_vendor_script():
    path = Path(__file__).resolve().parent.parent / "scripts" / "vendor_fire.py"
    spec = importlib.util.spec_from_file_location("vendor_fire", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def real_fire_root():
    return repo.root()


@pytest.fixture
def fresh_root():
    repo.root.cache_clear()
    yield
    repo.root.cache_clear()


@pytest.fixture
def bundled(tmp_path, real_fire_root, monkeypatch):
    dest = tmp_path / "_fire"
    _load_vendor_script().vendor(real_fire_root, "v0.test", dest=dest)
    monkeypatch.setattr(repo, "BUNDLED_ROOT", dest)
    return dest


def test_vendor_copies_everything_repo_reads(bundled, real_fire_root):
    assert (bundled / "FIRE_VERSION").read_text().strip() == "v0.test"
    assert (bundled / "LICENSE").is_file()
    for directory, pattern in (
        ("schemas", "*.json"),
        ("extensions/schemas", "*.json"),
        ("documentation/properties", "*.md"),
        ("extensions/documentation/properties", "*.md"),
        ("examples", "*.json"),
    ):
        expected = {p.name for p in (real_fire_root / directory).glob(pattern)}
        assert {p.name for p in (bundled / directory).glob(pattern)} == expected


def test_bundled_data_is_used_when_fire_repo_root_is_unset(
    bundled, fresh_root, monkeypatch
):
    monkeypatch.delenv("FIRE_REPO_ROOT", raising=False)
    assert repo.root() == bundled


def test_fire_repo_root_overrides_bundled_data(
    bundled, fresh_root, monkeypatch, real_fire_root
):
    monkeypatch.setenv("FIRE_REPO_ROOT", str(real_fire_root))
    assert repo.root() == real_fire_root


def test_vendor_rejects_a_directory_that_is_not_fire(tmp_path):
    with pytest.raises(SystemExit, match="does not look like a FIRE checkout"):
        _load_vendor_script().vendor(tmp_path, "v0", dest=tmp_path / "out")
