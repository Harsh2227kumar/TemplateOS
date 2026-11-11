"""
V1.7 Phase 2.2 (Member 3): length budgets from where a placeholder sits in
the Word file (app.services.field_placement).

Coverage: inline vs own line, table cell, header, list loop, validation_rule
max:N as a hard budget, types without a budget, unreadable / missing file,
the per-version cache, over-budget helpers.
"""

import io
import os
from types import SimpleNamespace

from docx import Document as DocxDocument

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

from app.services import field_placement  # noqa: E402
from app.services.field_placement import (  # noqa: E402
    FieldBudget,
    cached_field_budgets,
    clear_budget_cache,
    field_budgets,
    is_over_budget,
    placements,
    value_length,
)
from app.services.storage_service import storage_service  # noqa: E402


def field(name, field_type="text", rule=None):
    return SimpleNamespace(field_name=name, field_type=field_type, validation_rule=rule)


def build_docx() -> bytes:
    document = DocxDocument()
    document.sections[0].header.paragraphs[0].text = "{{ institute_name }}"
    document.add_paragraph("Name: {{ student_name }}")
    document.add_paragraph("{{ abstract }}")
    document.add_paragraph("{{ short_title }}")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Guide"
    table.cell(0, 1).text = "{{ guide_name }}"
    document.add_paragraph("{%p for item in objectives %}")
    document.add_paragraph("{{ item }}")
    document.add_paragraph("{%p endfor %}")
    document.add_paragraph("Submitted on {{ submission_date }} with {{ page_count }} pages")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


FIELDS = [
    field("institute_name"),
    field("student_name"),
    field("abstract", "textarea"),
    field("short_title", "text", "max:50"),
    field("guide_name"),
    field("objectives", "list"),
    field("submission_date", "date"),
    field("page_count", "number", "max:500"),
    field("signature", "signature"),
    field("not_in_file", "textarea"),
]


def test_placements_of_first_occurrence():
    found = placements(build_docx())
    assert found["student_name"] == "inline"
    assert found["abstract"] == "line"
    assert found["guide_name"] == "table_cell"
    assert found["institute_name"] == "header_footer"
    assert found["objectives"] == "line"
    assert "item" in found  # the loop variable is harmless: no field has that name


def test_budgets_per_placement_and_type():
    budgets = field_budgets(build_docx(), FIELDS)
    assert budgets["student_name"] == FieldBudget("student_name", "inline", 80, "chars")
    assert budgets["abstract"] == FieldBudget("abstract", "line", 1200, "chars")
    assert budgets["guide_name"] == FieldBudget("guide_name", "table_cell", 120, "chars")
    assert budgets["institute_name"] == FieldBudget("institute_name", "header_footer", 60, "chars")
    assert budgets["objectives"] == FieldBudget("objectives", "line", 10, "items", item_budget=200)
    # validation_rule max:N wins and is marked hard
    assert budgets["short_title"] == FieldBudget("short_title", "line", 50, "chars", hard=True)
    # a field the file does not contain still gets the default
    assert budgets["not_in_file"] == FieldBudget("not_in_file", "line", 1200, "chars")
    # dates, numbers and signatures have no budget
    assert not {"submission_date", "page_count", "signature"} & set(budgets)


def test_list_in_a_table_and_list_max_rule():
    document = DocxDocument()
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "{%p for m in members %}{{ m }}{%p endfor %}"
    buffer = io.BytesIO()
    document.save(buffer)
    budgets = field_budgets(buffer.getvalue(), [field("members", "list"), field("topics", "list", "min:1|max:4")])
    assert budgets["members"] == FieldBudget("members", "table_cell", 8, "items", item_budget=120)
    assert budgets["topics"] == FieldBudget("topics", "line", 4, "items", item_budget=200, hard=True)


def test_unreadable_or_missing_file_uses_defaults():
    for data in (None, b"", b"this is not a docx"):
        budgets = field_budgets(data, FIELDS)
        assert budgets["student_name"].placement == "line"
        assert budgets["student_name"].budget == 200
        assert budgets["short_title"].budget == 50


def test_over_budget_helpers():
    chars = FieldBudget("a", "line", 10, "chars")
    assert not is_over_budget(chars, "x" * 10)
    assert is_over_budget(chars, "x" * 11)
    assert value_length(chars, "abc") == 3

    items = FieldBudget("b", "line", 2, "items", item_budget=5)
    assert not is_over_budget(items, None, ["one", "two"])
    assert is_over_budget(items, None, ["one", "two", "x"])  # too many items
    assert is_over_budget(items, None, ["toolong"])  # one item too long
    assert value_length(items, None, ["one", "two"]) == 2


def test_cache_per_template_version(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_service, "root_path", tmp_path.resolve())
    clear_budget_cache()
    path = storage_service.save_bytes("templates_processed", "report.docx", build_docx()).path
    template = SimpleNamespace(id=7, version=1, processed_file_path=path, original_file_path=None)

    calls = {"count": 0}
    real = field_placement.field_budgets

    def counting(docx_bytes, fields):
        calls["count"] += 1
        return real(docx_bytes, fields)

    monkeypatch.setattr(field_placement, "field_budgets", counting)

    first = cached_field_budgets(template, FIELDS)
    second = cached_field_budgets(template, FIELDS)
    assert first is second and calls["count"] == 1
    assert first["guide_name"].placement == "table_cell"

    template.version = 2  # a new template revision: read the file again
    cached_field_budgets(template, FIELDS)
    assert calls["count"] == 2

    # a changed field configuration is a different key too
    cached_field_budgets(template, [field("student_name", "text", "max:30")])
    assert calls["count"] == 3

    # a missing file never raises
    missing = SimpleNamespace(id=8, version=1, processed_file_path="templates_processed/none.docx",
                              original_file_path=None)
    assert cached_field_budgets(missing, FIELDS)["student_name"].placement == "line"
    clear_budget_cache()
