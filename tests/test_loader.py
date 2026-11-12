from __future__ import annotations

import pytest

from fire_mcp import loader


@pytest.mark.parametrize(
    "name", ["../schemas/loan", "/etc/hostname", "..", "", "bond_future.json"]
)
def test_load_example_rejects_anything_but_a_plain_name(name):
    with pytest.raises(FileNotFoundError):
        loader.load_example(name)


def test_load_doc_rejects_paths():
    assert loader.load_doc("../README") is None


def test_missing_names_are_not_cached():
    before = loader._load_text.cache_info().currsize
    for i in range(50):
        assert loader.load_doc(f"no_such_field_{i}") is None
    assert loader._load_text.cache_info().currsize == before
