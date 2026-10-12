"""
Field metadata inference (template pipeline).

Pure functions — NO database access. Given a placeholder key and, when known,
the label text it came from and the original sample value, infer the field
metadata the form builder needs:

    field_label (Title Case), field_type (one of FIELD_TYPES),
    validation_rule, is_required, ai_enabled, section hint.

Shared by placeholder detection, cleaning suggestions and the /clean
field upsert so every entry point produces the same, predictable metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.template_field import FIELD_TYPES

VALID_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
MAX_KEY_LENGTH = 60

# ── vocabularies ─────────────────────────────────────────────────────

_SMALL_WORDS = {
    "a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or",
    "the", "to", "via", "with", "from", "per",
}
_ACRONYMS = {
    "id", "hod", "dob", "url", "pdf", "cgpa", "sgpa", "gpa", "pan", "ifsc",
    "pin", "otp", "upi", "ug", "pg", "phd", "sit", "mom", "atr", "ref", "sr",
    "prn", "uid", "gst", "cc", "bcc", "tpo", "iqac", "qic", "hr", "it",
}
# Acronyms that read better kept as words in Title Case.
_TITLE_ACRONYMS = _ACRONYMS - {"ref", "sr", "it", "cc"}

_DATE_TOKENS = {"date", "dob", "deadline", "dated", "day", "birthdate"}
_DATE_PHRASES = ("date_of", "_date", "due_on", "valid_till", "valid_until", "held_on")
_NUMBER_TOKENS = {
    "count", "amount", "no", "number", "num", "marks", "mark", "total", "qty",
    "quantity", "fee", "fees", "score", "age", "percentage", "percent",
    "credits", "credit", "price", "cost", "salary", "budget", "strength",
    "duration", "hours", "semester", "sem", "year",
}
# "<x>_no" keys that are identifiers, not numbers.
_IDENTIFIER_TOKENS = {
    "ref", "reference", "roll", "registration", "reg", "enrollment",
    "enrolment", "phone", "mobile", "contact", "application", "file",
    "letter", "prn", "employee", "emp", "id", "certificate", "receipt",
    "invoice", "order", "vehicle", "passport", "aadhar", "aadhaar", "pan",
    "account", "seat", "room", "ticket", "serial", "outward", "inward",
}
_LIST_TOKENS = {
    "attendees", "items", "points", "members", "agenda", "participants",
    "tasks", "decisions", "actions", "names", "list", "invitees",
    "speakers", "topics", "objectives", "outcomes", "recipients", "panelists",
    "volunteers", "students", "guests", "deliverables", "resolutions",
}
_TEXTAREA_TOKENS = {
    "description", "summary", "remarks", "remark", "details", "minutes",
    "body", "discussion", "comments", "comment", "notes", "note", "content",
    "purpose", "objective", "message", "reason", "abstract", "address",
    "feedback", "observations", "observation", "conclusion", "background",
    "proceedings", "explanation", "justification", "outcome", "report",
}
_SIGNATURE_TOKENS = {"signature", "sign", "signed", "sig"}
_EMAIL_TOKENS = {"email", "mail", "e_mail"}
_PHONE_TOKENS = {"phone", "mobile", "contact_no", "telephone", "tel", "cell"}
_OPTIONAL_TOKENS = {
    "remarks", "remark", "notes", "note", "comments", "comment", "cc",
    "optional", "additional", "other", "others", "any", "suggestions",
}
_AI_TOKENS = {
    "agenda", "summary", "description", "discussion", "minutes", "points",
    "remarks", "objective", "objectives", "purpose", "outcome", "outcomes",
    "body", "content", "message", "abstract", "conclusion", "decisions",
    "proceedings", "background", "reason", "justification", "report",
}
_SIGNATORY_KEY = re.compile(
    r"(^|_)(prepared|verified|approved|signed|submitted|forwarded|recommended|"
    r"checked|issued|authorized|authorised|attested|sanctioned)_by($|_)"
)

# ── value recognizers ────────────────────────────────────────────────

_MONTHS = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
DATE_VALUE = re.compile(
    r"\b(?:\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
    r"|\d{4}-\d{1,2}-\d{1,2}"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS}\.?,?\s+\d{{4}}"
    rf"|{_MONTHS}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}})\b",
    re.IGNORECASE,
)
TIME_VALUE = re.compile(
    r"\b\d{1,2}[:.]\d{2}\s*(?:[ap]\.m\.|[ap]m\b|hrs\b|hours\b)?(?![\d/])"
    r"|\b\d{1,2}\s*(?:[ap]\.m\.|[ap]m\b)",
    re.IGNORECASE,
)
EMAIL_VALUE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE_VALUE = re.compile(r"(?<![\w/])(?:\+\d{1,3}[\s\-]?)?(?:\(?\d{2,5}\)?[\s\-]?){2,4}\d{2,5}(?![\w/])")
NUMBER_VALUE = re.compile(r"^\s*[₹$]?\s*\d[\d,]*(?:\.\d+)?\s*%?\s*$")


def is_phone(text: str) -> bool:
    digits = re.sub(r"\D", "", text)
    return 10 <= len(digits) <= 13 and not DATE_VALUE.fullmatch(text.strip())


# ── keys and labels ──────────────────────────────────────────────────


def normalize_label(label: str) -> str:
    """Strip separators/leaders/brackets and collapse whitespace."""
    text = label.replace("\n", " ").replace("\t", " ")
    text = re.sub(r"[_.…\-–—]{3,}", " ", text)
    text = text.strip().strip(":：-–—=>|*#").strip()
    text = text.strip("[]<>(){}«»\"'“”‘’").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def label_to_key(label: str, fallback: str = "field") -> str:
    """
    'Title of the Meeting' -> 'meeting_title', 'Ref. No' -> 'ref_no',
    'Date of Birth' -> 'date_of_birth', 'E-mail ID' -> 'email_id'.
    """
    text = normalize_label(label)
    text = re.sub(r"(?i)\be[\s\-]?mail\b", "email", text)
    text = re.sub(r"[’']s\b", "", text)
    text = text.replace("&", " ")
    match = re.match(
        r"^(\w+(?:\s+\w+)?)\s+of\s+the\s+(\w+(?:\s+\w+)?)$", text, re.IGNORECASE
    )
    if match:
        text = f"{match.group(2)} {match.group(1)}"
    words = re.findall(r"[a-z0-9]+", text.lower())
    words = [word for word in words if word not in {"the", "a", "an"}]
    key = "_".join(words)
    key = re.sub(r"_+", "_", key).strip("_")
    if len(key) > MAX_KEY_LENGTH:
        key = key[:MAX_KEY_LENGTH].rsplit("_", 1)[0] or key[:MAX_KEY_LENGTH]
    if not key:
        return fallback
    if not key[0].isalpha():
        key = f"{fallback}_{key}"
    return key


def title_case(text: str) -> str:
    """Title Case keeping small words lowercase and known acronyms upper."""
    words = re.split(r"(\s+)", text.strip())
    result: list[str] = []
    index = 0
    for word in words:
        if not word or word.isspace():
            result.append(word)
            continue
        bare = re.sub(r"[^A-Za-z]", "", word).lower()
        if bare in _TITLE_ACRONYMS and len(bare) == len(re.sub(r"[^A-Za-z0-9]", "", word)):
            result.append(word.upper())
        elif index > 0 and bare in _SMALL_WORDS and word.lower() == bare:
            result.append(word.lower())
        elif word.isupper() and len(bare) > 3:
            result.append(word.capitalize())
        elif word[:1].islower() or word.isupper():
            result.append(word[:1].upper() + word[1:].lower())
        else:
            result.append(word[:1].upper() + word[1:])
        index += 1
    return "".join(result)


def key_to_label(key: str) -> str:
    """'meeting_date' -> 'Meeting Date', 'hod_name' -> 'HOD Name'."""
    return title_case(" ".join(part for part in key.split("_") if part))


def label_text_to_label(label: str) -> str:
    text = normalize_label(label)
    if not text:
        return ""
    return title_case(text)[:150]


def suggest_key(raw: str) -> str:
    """Normalize a malformed token (e.g. 'Meeting Title') into snake_case."""
    key = raw.strip()
    # camelCase / PascalCase -> snake_case before lowering.
    key = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    key = key.lower()
    key = re.sub(r"[\s\-./]+", "_", key)
    key = re.sub(r"[^a-z0-9_]", "", key)
    key = re.sub(r"_{2,}", "_", key).strip("_")
    if not key:
        return "field"
    if not key[0].isalpha():
        key = f"field_{key}"
    return key[:100]


# ── type / validation inference ──────────────────────────────────────


def _tokens(key: str) -> list[str]:
    return [token for token in key.split("_") if token]


def infer_field_type(
    key: str,
    label: str | None = None,
    value: str | None = None,
    allow_list: bool = True,
) -> str:
    tokens = _tokens(key)
    token_set = set(tokens)
    label_tokens = set(re.findall(r"[a-z]+", (label or "").lower()))
    all_tokens = token_set | label_tokens
    last = tokens[-1] if tokens else ""

    if all_tokens & _SIGNATURE_TOKENS and not (token_set & {"name", "date"}):
        return "signature"
    if token_set & _DATE_TOKENS or any(phrase in key for phrase in _DATE_PHRASES):
        return "date"
    if value and DATE_VALUE.fullmatch(value.strip()):
        return "date"
    if allow_list and (last in _LIST_TOKENS or (token_set & _LIST_TOKENS and last in {"list", "items", "points"})):
        return "list"
    if last in _TEXTAREA_TOKENS or token_set & {"description", "summary", "minutes", "remarks", "discussion", "details"}:
        return "textarea"
    if token_set & _NUMBER_TOKENS:
        identifier = bool(token_set & _IDENTIFIER_TOKENS) or bool(
            all_tokens & _PHONE_TOKENS
        )
        if not identifier:
            if value is None or not value.strip() or NUMBER_VALUE.match(value):
                return "number"
    if value and NUMBER_VALUE.match(value) and token_set & {"total", "amount", "count", "marks"}:
        return "number"
    if value and len(value) > 120:
        return "textarea"
    if not allow_list and last in _LIST_TOKENS:
        return "textarea"
    return "text"


def infer_validation_rule(key: str, field_type: str, value: str | None = None) -> str | None:
    token_set = set(_tokens(key))
    if token_set & _EMAIL_TOKENS or "e_mail" in key or (value and EMAIL_VALUE.fullmatch(value.strip())):
        return "email"
    if field_type == "text" and (
        token_set & {"phone", "mobile", "telephone", "tel"} or "contact_no" in key
        or (value and is_phone(value) and not EMAIL_VALUE.search(value))
    ):
        return "min:10|max:20"
    return None


def infer_required(key: str, field_type: str) -> bool:
    token_set = set(_tokens(key))
    if token_set & _OPTIONAL_TOKENS:
        return False
    return True


def infer_ai_enabled(key: str, field_type: str) -> bool:
    token_set = set(_tokens(key))
    if field_type in ("date", "number", "signature"):
        return False
    return bool(token_set & _AI_TOKENS) or field_type == "textarea"


_SIGNATORY_ROLE_NAME = re.compile(
    r"^(director|principal|dean|hod|head_of_department|registrar|"
    r"\w+_incharge|\w*coordinator|convener|convenor|secretary|president)_name$"
)


def infer_section_override(key: str, field_type: str) -> str | None:
    if field_type == "signature" or _SIGNATORY_KEY.search(key) or _SIGNATORY_ROLE_NAME.match(key):
        return "Signatures"
    return None


@dataclass(frozen=True)
class FieldMeta:
    field_label: str
    field_type: str
    validation_rule: str | None
    is_required: bool
    ai_enabled: bool
    section: str | None
    example_value: str | None


def infer_field_meta(
    key: str,
    label: str | None = None,
    value: str | None = None,
    section: str | None = None,
    field_type: str | None = None,
    allow_list: bool = True,
) -> FieldMeta:
    """One-stop inference used by detection, suggestions and /clean."""
    resolved_type = field_type if field_type in FIELD_TYPES else infer_field_type(
        key, label, value, allow_list=allow_list
    )
    field_label = label_text_to_label(label) if label else ""
    if not field_label or len(field_label) > 80:
        field_label = key_to_label(key)
    example = value.strip()[:255] if value and value.strip() else None
    override = infer_section_override(key, resolved_type)
    resolved_section = override or (section.strip()[:100] if section else None)
    return FieldMeta(
        field_label=field_label[:150],
        field_type=resolved_type,
        validation_rule=infer_validation_rule(key, resolved_type, value),
        is_required=infer_required(key, resolved_type),
        ai_enabled=infer_ai_enabled(key, resolved_type),
        section=resolved_section,
        example_value=example,
    )
