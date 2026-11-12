from __future__ import annotations

import pytest

from fire_mcp import docs, repo


def test_get_enum_definitions_h2_split_loan():
    defs = docs.get_enum_definitions("repayment_type", "loan")
    assert set(defs) == {
        "combined",
        "interest_only",
        "repayment",
        "fixed",
        "french",
        "option_arm",
        "other",
    }


def test_get_enum_definitions_h2_split_security_is_disjoint_from_loan():
    defs = docs.get_enum_definitions("repayment_type", "security")
    assert set(defs) == {
        "other",
        "pr2s",
        "pr2s_abcp",
        "pr2s_non_abcp",
        "pro_rata",
        "sequential",
    }


def test_get_enum_definitions_flat_pattern_shared_across_schemas():
    for entity in ("account", "derivative", "loan", "security"):
        defs = docs.get_enum_definitions("accounting_treatment", entity)
        assert "held_for_trading" in defs


def test_get_enum_definitions_h1_split_type_field():
    defs_customer = docs.get_enum_definitions("type", "customer")
    assert "individual" in defs_customer

    defs_loan = docs.get_enum_definitions("type", "loan")
    assert "mortgage" in defs_loan


def test_get_enum_definitions_raises_when_not_found():
    with pytest.raises(docs.EnumDocsNotFoundError):
        docs.get_enum_definitions("repayment_type", "customer")


def test_docs_with_windows_line_endings_parse_like_unix_ones(tmp_path, monkeypatch):
    # read_text uses universal newlines, so a CRLF doc never reaches the
    # parsers with a stray \r -- this pins that behaviour.
    (tmp_path / "crlf_field.md").write_bytes(
        b"---\r\nschemas: [loan]\r\n---\r\n# crlf_field\r\n\r\n"
        b"First paragraph.\r\n\r\n### alpha\r\nAlpha def.\r\n### beta\r\nBeta def.\r\n"
    )
    monkeypatch.setattr(repo, "docs_dir", lambda: tmp_path)

    doc = docs.load_field_doc("crlf_field")
    assert doc.excerpt == "First paragraph."
    assert "\r" not in doc.full
    assert docs.get_enum_definitions("crlf_field", "loan") == {
        "alpha": "Alpha def.",
        "beta": "Beta def.",
    }
