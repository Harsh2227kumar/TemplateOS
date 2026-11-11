"""
Fit check (V1.7 Phase 2.2 - Member 2): does a generated version still fit
the template?

Two signals, both advisory (nothing is ever cut or blocked):

- pages: the generated PDF's page count against the template's BASELINE (the
  template rendered with each field's example value or label, converted
  once per template version and cached on the template row).
- long_fields: values longer than their length budget
  (app.services.field_placement).

Without a PDF (conversion off or failed) the report has checked=False and
still lists the long fields.
"""

import io
import json
import logging
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.crud.document_version_crud import parse_snapshot
from app.schemas.ai_fill import FitLongField, FitReport
from app.services import pdf_service
from app.services.docx_cleaner import get_renderable_path
from app.services.field_placement import FieldBudget, is_over_budget, value_length
from app.services.generation_service import build_context, render_docx
from app.services.storage_service import storage_service

if TYPE_CHECKING:
    from app.models.document_version import DocumentVersion
    from app.models.template import Template
    from app.models.template_field import TemplateField

logger = logging.getLogger(__name__)

NO_PDF_REASON = "No PDF for this version"


def pdf_page_count(pdf_bytes: bytes) -> int | None:
    """Pages of a PDF; None when it cannot be read."""
    try:
        from pypdf import PdfReader

        return len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except Exception as exc:
        logger.warning("Could not count PDF pages: %s", exc)
        return None


def _label(field: "TemplateField") -> str:
    return (field.field_label or "").strip() or field.field_name


def baseline_values(fields: list["TemplateField"], today: date | None = None) -> dict[str, str]:
    """Short, realistic stand-in values: the example value, else the label."""
    today = today or date.today()
    values: dict[str, str] = {}
    for field in fields:
        sample = (field.example_value or "").strip() or _label(field)
        if field.field_type == "list":
            values[field.field_name] = json.dumps([sample, sample])
        elif field.field_type == "date":
            values[field.field_name] = today.isoformat()
        elif field.field_type == "number":
            values[field.field_name] = "1"
        elif field.field_type == "signature":
            values[field.field_name] = ""
        else:
            values[field.field_name] = sample
    return values


def ensure_baseline(db: Session, template: "Template", fields: list["TemplateField"]) -> int | None:
    """
    The template's baseline page count, computed once per template version
    (one render + one PDF conversion) and stored on the template (flushed,
    not committed). None when PDF conversion is unavailable or anything
    fails; nothing is stored then, so a later call tries again.
    """
    if template.baseline_pages is not None and template.baseline_pages_version == template.version:
        return template.baseline_pages
    converter = pdf_service.get_pdf_converter()
    path = get_renderable_path(template)
    if converter is None or not path:
        return None
    try:
        docx_bytes = render_docx(
            storage_service.read_bytes(path), build_context(fields, baseline_values(fields))
        )
        pages = pdf_page_count(converter.convert(docx_bytes, "baseline.docx"))
    except Exception as exc:  # render / conversion / storage: the check is optional
        logger.warning("Baseline pages for template %s failed: %s", template.id, exc)
        return None
    if pages is None:
        return None
    template.baseline_pages = pages
    template.baseline_pages_version = template.version
    db.flush()
    return pages


def long_fields(
    fields: list["TemplateField"], values: dict[str, str], budgets: dict[str, FieldBudget]
) -> list[FitLongField]:
    """Fields whose value exceeds its budget, in form order."""
    found: list[FitLongField] = []
    for field in fields:
        budget = budgets.get(field.field_name)
        raw = values.get(field.field_name) or ""
        if budget is None or not raw.strip():
            continue
        items: list[str] | None = None
        if budget.unit == "items":
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError):
                parsed = [raw]
            items = [str(i) for i in parsed if str(i).strip()] if isinstance(parsed, list) else [str(parsed)]
        if not is_over_budget(budget, raw, items):
            continue
        length = value_length(budget, raw, items)
        limit = budget.budget
        unit = budget.unit
        if items is not None and len(items) <= budget.budget and budget.item_budget:
            # Not too many items: one of them is too long.
            length, limit, unit = max(len(i) for i in items), budget.item_budget, "chars"
        found.append(
            FitLongField(field_name=field.field_name, label=_label(field), length=length, budget=limit, unit=unit)
        )
    return found


def fit_report(
    db: Session,
    template: "Template",
    version: "DocumentVersion",
    fields: list["TemplateField"],
    budgets: dict[str, FieldBudget],
) -> FitReport:
    values = {item["field_name"]: item.get("value") or "" for item in parse_snapshot(version)}
    report = FitReport(version=version.version, long_fields=long_fields(fields, values, budgets))

    record = version.generated_file
    pdf_path = record.pdf_path if record is not None and record.files_pruned_at is None else None
    pages: int | None = None
    if pdf_path:
        try:
            pages = pdf_page_count(storage_service.read_bytes(pdf_path))
        except Exception as exc:  # file removed from storage
            logger.warning("PDF of version %s is not readable: %s", version.id, exc)
    if pages is None:
        report.reason = NO_PDF_REASON
        return report

    report.checked = True
    report.pages = pages
    # Only a template that is still at the version this document was
    # generated from gives a meaningful baseline.
    if version.template_version in (None, template.version):
        report.baseline_pages = ensure_baseline(db, template, fields)
    report.overflow = report.baseline_pages is not None and pages > report.baseline_pages
    return report
