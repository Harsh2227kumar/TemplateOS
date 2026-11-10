"""
Document validation service for V1.4 Phase 2.

Validates document_values against template_fields metadata:
- Duplicate field_name checks (one value per field per payload)
- Required field checks (an empty JSON array counts as empty for list fields)
- Type validation (finite number, list = JSON array of strings)
- validation_rule enforcement (email, min:N, max:N; list fields count items)
"""

import json
import logging
import math
import re
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

if TYPE_CHECKING:
    from app.models.template_field import TemplateField

logger = logging.getLogger(__name__)

# Regex for email validation
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _parse_validation_rule(rule: str) -> dict | None:
    """
    Parse validation_rule string into structured format.

    Supported formats:
    - "email"
    - "min:N" (N = integer)
    - "max:N" (N = integer)
    - "min:N|max:M" (combined)
    - "email|min:5" (combined with pipe)

    Malformed min/max parts (e.g. "min:abc") are ignored with a warning: a
    bad template config should not block the user from saving.
    """
    if not rule:
        return None

    parts = rule.split("|")
    parsed = {}

    for part in parts:
        part = part.strip()
        if part == "email":
            parsed["email"] = True
        elif part.startswith("min:") or part.startswith("max:"):
            key = part[:3]
            try:
                parsed[key] = int(part.split(":", 1)[1])
            except ValueError:
                logger.warning(
                    "Ignoring malformed validation rule part %r in rule %r",
                    part,
                    rule,
                )

    return parsed if parsed else None


def _parse_list_value(value: str) -> list[str] | None:
    """
    Parse a list-field value (JSON array of strings, e.g. '["a", "b"]').

    A blank string is treated as an empty list. Returns None if the value is
    not a valid JSON array of strings.
    """
    if not value.strip():
        return []
    try:
        items = json.loads(value)
    except ValueError:
        return None
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        return None
    return items


def validate_document_values(
    fields: list["TemplateField"], values: list[dict]
) -> list[dict]:
    """
    Validate document values against template field definitions.

    Args:
        fields: List of TemplateField objects from the template
        values: List of dicts with {field_name, value}

    Returns:
        The validated values list (unchanged, for chaining)

    Raises:
        HTTPException(422): If any validation fails, detail contains list of
        {field_name, error} objects.
    """
    errors = []
    field_map = {f.field_name: f for f in fields}
    seen_names: set[str] = set()

    for value_dict in values:
        field_name = value_dict.get("field_name")
        value = value_dict.get("value", "")

        if not field_name:
            errors.append({"field_name": field_name, "error": "field_name is required"})
            continue

        if field_name in seen_names:
            errors.append(
                {"field_name": field_name, "error": "Duplicate field in payload"}
            )
            continue
        seen_names.add(field_name)

        field = field_map.get(field_name)
        if not field:
            errors.append(
                {"field_name": field_name, "error": "Field not found in template"}
            )
            continue

        is_list = field.field_type == "list"

        # List fields must be a JSON array of strings; "empty" means no
        # non-blank items.
        list_items: list[str] = []
        if is_list:
            parsed_items = _parse_list_value(value)
            if parsed_items is None:
                errors.append(
                    {
                        "field_name": field_name,
                        "error": "Must be a valid list (JSON array of strings)",
                    }
                )
                continue
            list_items = parsed_items
            is_empty = not any(item.strip() for item in list_items)
        else:
            is_empty = not value.strip()

        # Required check
        if field.is_required and is_empty:
            errors.append({"field_name": field_name, "error": "This field is required"})
            continue

        # Skip further validation if value is empty and not required
        if is_empty:
            continue

        # Type validation: number (finite only; rejects nan/inf)
        number_value: float | None = None
        if field.field_type == "number":
            try:
                number_value = float(value)
            except ValueError:
                number_value = None
            if number_value is None or not math.isfinite(number_value):
                errors.append(
                    {"field_name": field_name, "error": "Must be a valid number"}
                )
                continue

        # Validation rule parsing
        rule_parsed = _parse_validation_rule(field.validation_rule)
        if rule_parsed:
            # Email validation (not meaningful for list fields)
            if rule_parsed.get("email") and not is_list:
                if not EMAIL_REGEX.match(value):
                    errors.append(
                        {
                            "field_name": field_name,
                            "error": "Must be a valid email address",
                        }
                    )

            # Min validation (numbers: value, lists: item count, else: length)
            if "min" in rule_parsed:
                min_val = rule_parsed["min"]
                if number_value is not None:
                    if number_value < min_val:
                        errors.append(
                            {
                                "field_name": field_name,
                                "error": f"Must be at least {min_val}",
                            }
                        )
                elif is_list:
                    if len(list_items) < min_val:
                        errors.append(
                            {
                                "field_name": field_name,
                                "error": f"Must have at least {min_val} items",
                            }
                        )
                else:
                    if len(value) < min_val:
                        errors.append(
                            {
                                "field_name": field_name,
                                "error": f"Must be at least {min_val} characters",
                            }
                        )

            # Max validation (numbers: value, lists: item count, else: length)
            if "max" in rule_parsed:
                max_val = rule_parsed["max"]
                if number_value is not None:
                    if number_value > max_val:
                        errors.append(
                            {
                                "field_name": field_name,
                                "error": f"Must be at most {max_val}",
                            }
                        )
                elif is_list:
                    if len(list_items) > max_val:
                        errors.append(
                            {
                                "field_name": field_name,
                                "error": f"Must have at most {max_val} items",
                            }
                        )
                else:
                    if len(value) > max_val:
                        errors.append(
                            {
                                "field_name": field_name,
                                "error": f"Must be at most {max_val} characters",
                            }
                        )

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=errors,
        )

    return values
