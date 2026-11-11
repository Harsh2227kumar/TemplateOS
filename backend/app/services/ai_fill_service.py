"""
AI fill assistant (V1.7 Phase 2.2 - Member 2): one chat turn -> proposals for
the form's fields plus questions about what is missing or unclear.

Two halves:

- run_turn: ONE Bedrock call (Claude through instructor, like field
  suggestions) that returns an AiFillTurn.
- postprocess: deterministic and pure (no DB, no AI). The model is not
  trusted: unknown / locked / signature fields are dropped, values are
  normalized per field type, a fact guard rejects numbers, emails and dates
  the user never wrote, budgets are flagged, questions are capped and
  ordered, and the stage of the clarification loop (asking / filling / ready)
  is decided here, never by the model.

PROPOSALS ONLY: nothing in this module writes document_values. The user's
text is never logged; log lines carry counts and field names.
"""

import json
import logging
import math
import re
from dataclasses import dataclass, field as dataclass_field
from datetime import date
from typing import TYPE_CHECKING, Iterable

from app.core.config import settings
from app.schemas.ai_fill import (
    AiFillProposalRead,
    AiFillQuestionRead,
    AiFillTurn,
    FormStateItem,
)
from app.services import ai_service
from app.services.ai_service import AiUnavailableError, to_plain_item, to_plain_text
from app.services.field_placement import FieldBudget, is_over_budget

if TYPE_CHECKING:
    from app.models.template_field import TemplateField

logger = logging.getLogger(__name__)

FILL_ACTION = "ai_fill"
# Field types the assistant never fills.
SKIPPED_FIELD_TYPES = ("signature",)
# Prose fields: reworded only when the field's ai_enabled is on. Short text
# (names, titles, IDs) is always cleaned up: the user chose AI filling.
REWRITE_FIELD_TYPES = ("textarea", "list")
CATALOG_VALUE_CHARS = 300
CATALOG_HINT_CHARS = 200
KIND_ORDER = {"conflict": 0, "missing": 1, "unclear": 2, "more_detail": 3}
UNKNOWN_DETAILS_REASON = "Contains details you did not give."
AMBIGUOUS_DATE_REASON = "The date can be read in two ways."

FILL_SYSTEM_PROMPT = (
    "You fill in the form of an official document for a user, from what they "
    "write in a chat. Reply only through the structured output.\n\n"
    "Rules:\n"
    "1. Use only facts the user wrote in this chat (EARLIER MESSAGES, their "
    "answers, NEW MESSAGE). Never invent names, dates, numbers, places, "
    "results or decisions.\n"
    "2. Fix grammar, spelling and abbreviations and write clear, formal "
    "English; translate Hindi or Hinglish to English. Copy names, numbers, "
    "dates, roll / registration numbers, emails, phone numbers, amounts and "
    "codes exactly as given (only fix the capitalisation of names and IDs).\n"
    "3. Respect each field's type and budget. text: one short line. "
    "textarea: full sentences; you may turn short notes into sentences using "
    "only the given facts. list: one entry per item in `items`. date: "
    "YYYY-MM-DD in `value` (use TODAY for relative dates). number: digits "
    "only. Stay within the budget.\n"
    "4. Never propose a value for a field whose status is LOCKED. For fields "
    "with ai_rewrite=no copy the user's words without rewording.\n"
    "5. Give every proposal a confidence: high = stated clearly; medium = "
    "stated but incomplete, or written from very little input; low = guessed "
    "or ambiguous. Do not propose low values: ask a question instead. A date "
    "like 3/4 that can be read two ways is ambiguous: ask, with both readings "
    "as choices. Put the user's own words in source_text.\n"
    "6. Ask at most {max_questions} questions, required fields first, one topic "
    "per question, with 2-4 choices when there are a few likely answers. Do "
    "not ask about fields that already have a value unless the new message "
    "contradicts it (then ask a `conflict` question with both values as "
    "choices).\n"
    "7. Keep asking until you are sure. After every answer check the whole "
    "form again: if a required field is still empty, an answer did not really "
    "answer the question, or a long text has too little to be written well, "
    "ask again in simpler words. Never ask about fields marked "
    "ask=ask_limit_reached or ask=skipped.\n"
    "8. If you cannot fill most required fields yet, set stage to `asking`, "
    "propose only what is certain and ask for the most important missing "
    "information first. Otherwise set stage to `filling`; set `ready` only "
    "when every required field has a value and you have no questions.\n"
    "9. Plain text only in values: no Markdown, no bullets, no numbering. "
    "`message` is one or two short friendly sentences about what you filled "
    "and what you still need."
)


# ── prompt building ──────────────────────────────────────────────


def _label(field: "TemplateField") -> str:
    return (field.field_label or "").strip() or field.field_name


def _one_line(text: str | None, limit: int) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


def parse_list(raw: str | None) -> list[str]:
    """A list field's stored value (JSON array of strings) -> non-blank items."""
    if not raw or not raw.strip():
        return []
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        return [raw.strip()]
    if not isinstance(items, list):
        return [str(items)]
    return [str(item).strip() for item in items if str(item).strip()]


def is_blank(field_type: str, raw: str | None) -> bool:
    if field_type == "list":
        return not parse_list(raw)
    return not (raw or "").strip()


def fillable_fields(fields: Iterable["TemplateField"]) -> list["TemplateField"]:
    return [f for f in fields if f.field_type not in SKIPPED_FIELD_TYPES]


def _budget_text(budget: FieldBudget | None) -> str:
    if budget is None:
        return "none"
    if budget.unit == "items":
        per_item = f", each <= {budget.item_budget} chars" if budget.item_budget else ""
        return f"{budget.budget} items{per_item}"
    return f"{budget.budget} chars"


def blocked_fields(
    ask_counts: dict[str, int], skipped: set[str], mentioned: set[str]
) -> tuple[set[str], set[str]]:
    """(fields at the ask limit, skipped fields the user did not bring up again)."""
    at_limit = {
        name for name, count in ask_counts.items() if count >= settings.ai_fill_max_asks_per_field
    }
    return at_limit, set(skipped) - set(mentioned)


def mentioned_fields(fields: Iterable["TemplateField"], message: str) -> set[str]:
    """Fields whose label (or key words) appear in the message."""
    text = " ".join(message.lower().split())
    if not text:
        return set()
    found: set[str] = set()
    for field in fields:
        names = {_label(field).lower(), field.field_name.replace("_", " ").lower()}
        if any(len(name) >= 3 and name in text for name in names):
            found.add(field.field_name)
    return found


def build_field_catalog(
    fields: Iterable["TemplateField"],
    budgets: dict[str, FieldBudget],
    form_state: dict[str, FormStateItem],
    ask_counts: dict[str, int],
    at_limit: set[str],
    skipped: set[str],
) -> str:
    lines: list[str] = []
    for field in fillable_fields(fields):
        item = form_state.get(field.field_name)
        blank = item is None or is_blank(field.field_type, item.value)
        if blank:
            status = "empty"
        elif item.origin == "user":
            status = "LOCKED (written by the user)"
        else:
            status = "filled by AI"
        if field.field_name in at_limit:
            ask = "ask_limit_reached"
        elif field.field_name in skipped:
            ask = "skipped"
        else:
            ask = "allowed"
        parts = [
            f"key={field.field_name}",
            f"label={_one_line(_label(field), 150)}",
            f"type={field.field_type}",
            f"required={'yes' if field.is_required else 'no'}",
        ]
        if (field.section or "").strip():
            parts.append(f"section={_one_line(field.section, 100)}")
        parts.append(f"budget={_budget_text(budgets.get(field.field_name))}")
        if field.field_type in REWRITE_FIELD_TYPES:
            parts.append(f"ai_rewrite={'yes' if field.ai_enabled else 'no'}")
        parts.append(f"status={status}")
        parts.append(f"asked={ask_counts.get(field.field_name, 0)} times")
        parts.append(f"ask={ask}")
        if not blank:
            current = item.value
            if field.field_type == "list":
                current = "; ".join(parse_list(item.value))
            parts.append(f"current={_one_line(current, CATALOG_VALUE_CHARS)}")
        if (field.description or "").strip():
            parts.append(f"about={_one_line(field.description, CATALOG_HINT_CHARS)}")
        if (field.example_value or "").strip():
            parts.append(f"example={_one_line(field.example_value, CATALOG_HINT_CHARS)}")
        lines.append("- " + " | ".join(parts))
    return "\n".join(lines) if lines else "(no fields)"


def build_user_content(
    *,
    catalog: str,
    history_text: str,
    open_questions: list[dict],
    answers: dict[str, str | None],
    skipped_ids: Iterable[str],
    message: str,
    today: date,
) -> str:
    skipped_ids = set(skipped_ids)
    asked_lines: list[str] = []
    for question in open_questions:
        question_id = str(question.get("id"))
        if question_id in skipped_ids:
            reply = "SKIPPED by the user (they will fill it themselves)"
        elif answers.get(question_id):
            reply = f"the user chose: {answers[question_id]}"
        else:
            reply = "see NEW MESSAGE (it may or may not answer this)"
        asked_lines.append(f"- {question.get('text')} -> {reply}")
    return (
        f"TODAY: {today.isoformat()}\n\n"
        f"FORM FIELDS:\n{catalog}\n\n"
        f"EARLIER MESSAGES FROM THE USER:\n{history_text or '(none)'}\n\n"
        "QUESTIONS YOU ASKED LAST TIME:\n"
        f"{chr(10).join(asked_lines) if asked_lines else '(none)'}\n\n"
        f"NEW MESSAGE:\n{message or '(no text: see the chosen answers above)'}"
    )


# ── the model call ───────────────────────────────────────────────


def run_turn(user_content: str) -> AiFillTurn:
    """One Bedrock call. Provider / validation failures -> AiUnavailableError."""
    client = ai_service._build_client()
    system = FILL_SYSTEM_PROMPT.format(max_questions=settings.ai_fill_max_questions)
    try:
        return client.messages.create(
            model=settings.fill_model,
            max_tokens=settings.ai_fill_max_output_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            response_model=AiFillTurn,
            max_retries=1,
        )
    except AiUnavailableError:
        raise
    except Exception as exc:
        reason = ai_service._classify_ai_error(exc, "BEDROCK_MODEL_FILL")
        logger.error(
            f"[ai] fill call failed — WHERE: ai_fill_service.run_turn -> Bedrock "
            f"(model={settings.fill_model}) — WHY: {reason}"
        )
        logger.debug("[ai] traceback:", exc_info=True)
        raise AiUnavailableError(f"AI is currently unavailable: {reason}") from exc


# ── dates ────────────────────────────────────────────────────────

_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"),
            ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"),
            ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"),
            ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}
_MONTH_NAMES = (
    "", "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
)
_MONTH_WORD = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_NUMERIC_DATE = re.compile(r"(?<![\d/.\-])(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{4}|\d{2}))?(?![\d/\-])")
_DAY_MONTH = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+({_MONTH_WORD})\b\.?(?:,?\s+(\d{{4}}))?", re.IGNORECASE
)
_MONTH_DAY = re.compile(
    rf"\b({_MONTH_WORD})\b\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", re.IGNORECASE
)
_RELATIVE_DATE = re.compile(
    r"\b(today|tomorrow|yesterday|tonight|next|last|coming|this\s+(?:week|month|year|mon|tue|wed|thu|fri|sat|sun)\w*"
    r"|aaj|kal|parso|(?:mon|tues|wednes|thurs|fri|satur|sun)day)\b",
    re.IGNORECASE,
)


def _valid_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _year(text: str | None) -> int | None:
    if not text:
        return None
    year = int(text)
    return year + 2000 if year < 100 else year


def normalize_date(value: str) -> str | None:
    """A model date as YYYY-MM-DD (numeric forms are read day first); None if unreadable."""
    text = value.strip()
    match = _ISO_DATE.search(text)
    if match:
        parsed = _valid_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        return parsed.isoformat() if parsed else None
    match = _DAY_MONTH.search(text)
    if match and match.group(3):
        parsed = _valid_date(int(match.group(3)), _MONTHS[match.group(2).lower()], int(match.group(1)))
        return parsed.isoformat() if parsed else None
    match = _MONTH_DAY.search(text)
    if match and match.group(3):
        parsed = _valid_date(int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2)))
        return parsed.isoformat() if parsed else None
    match = _NUMERIC_DATE.search(text)
    if match and match.group(3):
        parsed = _valid_date(_year(match.group(3)), int(match.group(2)), int(match.group(1)))
        return parsed.isoformat() if parsed else None
    return None


@dataclass(frozen=True)
class DateMention:
    """A date the user wrote: day / month, a year when given, and whether day and month could be swapped."""

    day: int
    month: int
    year: int | None
    ambiguous: bool = False


def date_mentions(text: str) -> list[DateMention]:
    mentions: list[DateMention] = []
    for match in _ISO_DATE.finditer(text):
        mentions.append(DateMention(int(match.group(3)), int(match.group(2)), int(match.group(1))))
    without_iso = _ISO_DATE.sub(" ", text)
    for match in _DAY_MONTH.finditer(without_iso):
        mentions.append(DateMention(int(match.group(1)), _MONTHS[match.group(2).lower()], _year(match.group(3))))
    for match in _MONTH_DAY.finditer(without_iso):
        mentions.append(DateMention(int(match.group(2)), _MONTHS[match.group(1).lower()], _year(match.group(3))))
    for match in _NUMERIC_DATE.finditer(without_iso):
        first, second, year = int(match.group(1)), int(match.group(2)), _year(match.group(3))
        day_first = 1 <= first <= 31 and 1 <= second <= 12
        month_first = 1 <= second <= 31 and 1 <= first <= 12 and first != second
        both = day_first and month_first
        if day_first:
            mentions.append(DateMention(first, second, year, ambiguous=both))
        if month_first:
            mentions.append(DateMention(second, first, year, ambiguous=both))
    return mentions


def _matches(mention: DateMention, value: date) -> bool:
    return (
        mention.day == value.day
        and mention.month == value.month
        and (mention.year is None or mention.year == value.year)
    )


def check_date(iso: str, user_text: str) -> tuple[str, list[str]]:
    """
    Is this date something the user wrote? -> (verdict, choices):
    "ok", "ambiguous" (only a 3/4-style mention matches; choices are both
    readings), "relative" (the user wrote "tomorrow", "next Monday", ...) or
    "unknown".
    """
    value = date.fromisoformat(iso)
    mentions = date_mentions(user_text)
    if any(_matches(m, value) and not m.ambiguous for m in mentions):
        return "ok", []
    ambiguous = [m for m in mentions if m.ambiguous and _matches(m, value)]
    if ambiguous:
        mention = ambiguous[0]
        year = mention.year or value.year
        readings = [(mention.day, mention.month), (mention.month, mention.day)]
        return "ambiguous", [f"{day} {_MONTH_NAMES[month]} {year}" for day, month in readings]
    if _RELATIVE_DATE.search(user_text):
        return "relative", []
    return "unknown", []


# ── fact guard ───────────────────────────────────────────────────

_DIGIT_TOKEN = re.compile(r"\d(?:[\d\s,.\-/]*\d)?")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
# Shorter digit groups (counts, small amounts, days) are low risk and are
# often written as words by the user; long ones are IDs, phones and years.
GUARDED_DIGITS = 3


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def fact_guard(texts: Iterable[str], user_text: str, *, today: date, strict_numbers: bool = False) -> str:
    """
    "ok" when every number, email and URL in `texts` appears in what the user
    wrote; "unknown" when one does not; "soft" when only a short number of a
    number field is missing (strict_numbers).
    """
    haystack = user_text.lower()
    user_digits = _digits(user_text)
    user_runs = set(re.findall(r"\d+", user_text))
    allowed_years = {str(today.year - 1), str(today.year), str(today.year + 1)}
    verdict = "ok"
    for text in texts:
        for match in _EMAIL.finditer(text):
            if match.group(0).lower() not in haystack:
                return "unknown"
        for match in _URL.finditer(text):
            if match.group(0).lower().rstrip("/.,") not in haystack:
                return "unknown"
        for match in _DIGIT_TOKEN.finditer(_EMAIL.sub(" ", text)):
            # "98765 43210" is one number for the user's "9876543210"; "12, 15"
            # is two. Accept the joined form, else judge each run on its own.
            joined = _digits(match.group(0))
            if len(joined) >= GUARDED_DIGITS and joined in user_digits:
                continue
            for run in re.findall(r"\d+", match.group(0)):
                if len(run) >= GUARDED_DIGITS:
                    if run in user_digits or (len(run) == 4 and run in allowed_years):
                        continue
                    return "unknown"
                if run in user_runs:
                    continue
                if strict_numbers:
                    verdict = "soft"
    return verdict


# ── post-processing ──────────────────────────────────────────────


@dataclass
class ProcessedTurn:
    message: str
    stage: str
    proposals: list[AiFillProposalRead]
    questions: list[AiFillQuestionRead]
    missing_required: list[str]
    needs_user: list[str]
    required_total: int
    required_filled: int
    done: bool
    counts: dict[str, int] = dataclass_field(default_factory=dict)


def _normalize_number(value: str) -> str | None:
    cleaned = value.replace(",", "").replace(" ", "").strip()
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return cleaned if math.isfinite(number) else None


def _cap(confidence: str, limit: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return confidence if order[confidence] <= order[limit] else limit


def _server_question_text(label: str, attempt: int) -> str:
    if attempt > 1:
        return f"I still need '{label}'. What should I put there?"
    return f"What should I put for '{label}'?"


def postprocess(
    turn: AiFillTurn,
    *,
    fields: list["TemplateField"],
    budgets: dict[str, FieldBudget],
    form_state: list[FormStateItem],
    user_texts: list[str],
    turn_number: int,
    ask_counts: dict[str, int] | None = None,
    skipped: set[str] | None = None,
    message: str = "",
    today: date | None = None,
) -> ProcessedTurn:
    """
    Turn the model's raw reply into what the user gets (Prompts/V1.7-P2.2.md
    §2.3 and §3.4). `user_texts` is everything the user wrote in this chat,
    including this turn's message and clicked choices; `skipped` are the
    fields of skipped questions.
    """
    today = today or date.today()
    ask_counts = ask_counts or {}
    usable = fillable_fields(fields)
    by_name = {f.field_name: f for f in usable}
    state = {item.field_name: item for item in form_state}
    user_text = "\n".join(user_texts)

    def blank_in_form(name: str) -> bool:
        item = state.get(name)
        return item is None or is_blank(by_name[name].field_type, item.value)

    locked = {name for name, item in state.items() if name in by_name and item.origin == "user" and not blank_in_form(name)}
    at_limit, still_skipped = blocked_fields(ask_counts, skipped or set(), mentioned_fields(usable, message))
    blocked = at_limit | still_skipped

    kept: list[AiFillProposalRead] = []
    low: dict[str, tuple[str, list[str]]] = {}  # field -> (kind, choices) for the server question
    dropped = 0
    left_alone: list[str] = []  # locked fields the model tried to change
    seen: set[str] = set()
    for proposal in turn.proposals:
        name = proposal.field_name
        field = by_name.get(name)
        if field is None or name in locked or name in seen:
            dropped += 1
            if field is not None and name in locked and name not in left_alone:
                left_alone.append(name)
            continue
        seen.add(name)

        value: str | None = None
        items: list[str] | None = None
        confidence = proposal.confidence
        reason = (proposal.reason or "").strip() or None
        choices: list[str] = []
        kind = "unclear"

        if field.field_type == "list":
            raw_items = proposal.items
            if raw_items is None and proposal.value:
                raw_items = proposal.value.splitlines()
            items = [item for item in (to_plain_item(i) for i in raw_items or []) if item]
            if not items:
                dropped += 1
                continue
        else:
            raw = proposal.value
            if raw is None and proposal.items:
                raw = "\n".join(proposal.items) if field.field_type == "textarea" else " ".join(proposal.items)
            raw = to_plain_text(raw or "")
            if field.field_type != "textarea":
                raw = " ".join(raw.split())
            if not raw:
                dropped += 1
                continue
            if field.field_type == "date":
                iso = normalize_date(raw)
                if iso is None:
                    dropped += 1
                    low[name] = ("unclear", [])
                    continue
                raw = iso
            elif field.field_type == "number":
                number = _normalize_number(raw)
                if number is None:
                    dropped += 1
                    low[name] = ("unclear", [])
                    continue
                raw = number
            value = raw

        # Fact guard: nothing the user did not write.
        if field.field_type == "date":
            verdict, choices = check_date(value, user_text)
            if verdict == "ambiguous":
                confidence, reason = "low", AMBIGUOUS_DATE_REASON
            elif verdict == "relative":
                confidence = _cap(confidence, "medium")
                reason = reason or "Worked out from a relative date; please check."
            elif verdict == "unknown":
                confidence, reason = "low", UNKNOWN_DETAILS_REASON
        else:
            verdict = fact_guard(
                items if items is not None else [value],
                user_text,
                today=today,
                strict_numbers=field.field_type == "number",
            )
            if verdict == "unknown":
                confidence, reason = "low", UNKNOWN_DETAILS_REASON
            elif verdict == "soft":
                confidence = _cap(confidence, "medium")
                reason = reason or "Please check this number."

        # ai_enabled is about rewording prose; dates and numbers have none.
        if not field.ai_enabled and field.field_type in REWRITE_FIELD_TYPES:
            confidence = _cap(confidence, "medium")

        if confidence == "low":
            low[name] = (kind, choices)
            continue

        budget = budgets.get(name)
        kept.append(
            AiFillProposalRead(
                field_name=name,
                value=value,
                items=items,
                source_text=(proposal.source_text or "").strip() or None,
                confidence=confidence,
                reason=reason,
                over_budget=bool(budget and is_over_budget(budget, value, items)),
            )
        )

    proposed = {p.field_name for p in kept}
    required = [f.field_name for f in usable if f.is_required]
    missing_required = [name for name in required if blank_in_form(name) and name not in proposed]

    # Questions: the model's, then the server's for low proposals and for
    # required fields nobody asked about (the loop must not stall).
    raw_questions: list[dict] = []
    covered: set[str] = set()
    limit_hit: set[str] = set()
    for question in turn.questions:
        names = []
        for name in question.field_names:
            if name not in by_name or name in locked:
                continue
            if name in blocked:
                if name in at_limit:
                    limit_hit.add(name)
                continue
            if name not in names:
                names.append(name)
        text = to_plain_text(question.text or "")
        if not names or not text:
            continue
        covered.update(names)
        raw_questions.append(
            {"text": text, "field_names": names, "choices": list(question.choices), "kind": question.kind, "net": 0}
        )
    for name, (kind, choices) in low.items():
        if name in covered:
            continue
        if name in blocked:
            if name in at_limit:
                limit_hit.add(name)
            continue
        covered.add(name)
        attempt = ask_counts.get(name, 0) + 1
        text = (
            f"Which date is right for '{_label(by_name[name])}'?"
            if choices
            else _server_question_text(_label(by_name[name]), attempt)
        )
        raw_questions.append({"text": text, "field_names": [name], "choices": choices, "kind": kind, "net": 0})
    for name in missing_required:
        if name in covered:
            continue
        if name in blocked:
            if name in at_limit:
                limit_hit.add(name)
            continue
        covered.add(name)
        attempt = ask_counts.get(name, 0) + 1
        raw_questions.append(
            {
                "text": _server_question_text(_label(by_name[name]), attempt),
                "field_names": [name],
                "choices": [],
                "kind": "missing",
                "net": 1,
            }
        )

    def sort_key(indexed: tuple[int, dict]) -> tuple[int, int, int, int]:
        # Required fields first; what this turn touched (the model's questions,
        # rejected proposals) before the safety net; then by kind.
        index, question = indexed
        is_required = any(by_name[name].is_required for name in question["field_names"])
        return (0 if is_required else 1, question["net"], KIND_ORDER.get(question["kind"], 9), index)

    ordered = [q for _, q in sorted(enumerate(raw_questions), key=sort_key)]
    questions = [
        AiFillQuestionRead(
            id=f"t{turn_number}-q{number}",
            text=question["text"],
            field_names=question["field_names"],
            choices=question["choices"],
            kind=question["kind"],
            attempt=max(ask_counts.get(name, 0) for name in question["field_names"]) + 1,
        )
        for number, question in enumerate(ordered[: settings.ai_fill_max_questions], start=1)
    ]

    needs_user = [name for name in missing_required if name in blocked]
    required_total = len(required)
    required_filled = required_total - len(missing_required)
    open_required = [name for name in missing_required if name not in blocked]
    if not open_required and not questions:
        stage = "ready"
    elif questions and required_filled * 2 < required_total:
        stage = "asking"
    else:
        stage = "filling"

    text = to_plain_text(turn.message or "")
    if not text:
        if stage == "ready":
            text = "I have everything I need. Review the form, then save and generate."
        elif kept:
            text = f"I filled {len(kept)} field(s)."
        else:
            text = "I need a few details before I can fill the form."
    for name in left_alone:
        text += f"\nI left '{_label(by_name[name])}' as you wrote it."
    for name in missing_required:
        if name in limit_hit:
            text += f"\nI couldn't get '{_label(by_name[name])}' from the chat. Please fill it in the form."

    return ProcessedTurn(
        message=text,
        stage=stage,
        proposals=kept,
        questions=questions,
        missing_required=missing_required,
        needs_user=needs_user,
        required_total=required_total,
        required_filled=required_filled,
        done=stage == "ready",
        counts={
            "kept": len(kept),
            "dropped": dropped,
            "low": len(low),
            "questions": len(questions),
        },
    )
