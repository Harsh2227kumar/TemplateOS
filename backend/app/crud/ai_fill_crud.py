"""
CRUD helpers for the AI fill chat (V1.7 Phase 2.2 - Member 3).

- get_session / get_or_create_session -> the one chat of a document
- add_turn            -> a user message plus the assistant's reply (same turn)
- user_history_text   -> the earlier user messages, as sent to the model
- open_questions / last_proposals -> from the latest assistant row
- ask_counts / skipped_fields     -> clarification loop bookkeeping, derived
                                     from the stored turns (no extra columns)
- mark_completed / clear_session

JSON columns are parsed and serialized here only. The chat text lives in
ai_fill_messages and nowhere else. None of the helpers commit.
"""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utc_now_naive
from app.models.ai_fill_message import AiFillMessage
from app.models.ai_fill_session import AiFillSession

FILLED_CONFIDENCES = ("high", "medium")
OMITTED_MARK = "[... earlier messages omitted ...]"


def parse_json_list(text: str | None) -> list:
    """A stored JSON list; anything else (NULL, bad JSON, an object) -> []."""
    if not text:
        return []
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def parse_answers(text: str | None) -> tuple[list[dict], list[str]]:
    """A user row's answers column -> (answers, skipped question ids)."""
    if not text:
        return [], []
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return [], []
    if not isinstance(data, dict):
        return [], []
    raw_answers = data.get("answers")
    raw_skipped = data.get("skipped")
    answers = [a for a in raw_answers if isinstance(a, dict)] if isinstance(raw_answers, list) else []
    skipped = [s for s in raw_skipped if isinstance(s, str)] if isinstance(raw_skipped, list) else []
    return answers, skipped


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def get_session(db: Session, document_id: int) -> AiFillSession | None:
    return db.execute(
        select(AiFillSession).where(AiFillSession.document_id == document_id)
    ).scalar_one_or_none()


def get_or_create_session(db: Session, document_id: int, user_id: int) -> AiFillSession:
    session = get_session(db, document_id)
    if session is None:
        session = AiFillSession(document_id=document_id, user_id=user_id)
        db.add(session)
        db.flush()
    return session


def list_messages(db: Session, session: AiFillSession) -> list[AiFillMessage]:
    """Chat order: by turn, the user row before the assistant row."""
    return list(
        db.execute(
            select(AiFillMessage)
            .where(AiFillMessage.session_id == session.id)
            .order_by(AiFillMessage.turn, AiFillMessage.role.desc())
        ).scalars()
    )


def _assistant_rows(db: Session, session: AiFillSession) -> list[AiFillMessage]:
    return [m for m in list_messages(db, session) if m.role == "assistant"]


def add_turn(
    db: Session,
    session: AiFillSession,
    *,
    user_text: str,
    answers: list[dict],
    skipped: list[str],
    assistant_text: str,
    proposals: list[dict],
    questions: list[dict],
    stage: str,
    model: str,
) -> tuple[AiFillMessage, AiFillMessage]:
    """Store one turn and update the session counters. Flushes, no commit."""
    turn = session.turn_count + 1
    user_message = AiFillMessage(
        session_id=session.id,
        turn=turn,
        role="user",
        content=user_text,
        answers=_dump({"answers": answers, "skipped": skipped}),
    )
    assistant_message = AiFillMessage(
        session_id=session.id,
        turn=turn,
        role="assistant",
        content=assistant_text,
        proposals=_dump(proposals),
        questions=_dump(questions),
        stage=stage,
        model=model,
    )
    db.add_all([user_message, assistant_message])
    db.flush()

    filled: set[str] = set()
    for row in _assistant_rows(db, session):
        for proposal in parse_json_list(row.proposals):
            if isinstance(proposal, dict) and proposal.get("confidence") in FILLED_CONFIDENCES:
                filled.add(str(proposal.get("field_name")))
    session.turn_count = turn
    session.filled_count = len(filled)
    session.updated_at = utc_now_naive()
    db.flush()
    return user_message, assistant_message


def _question_texts(db: Session, session: AiFillSession) -> dict[str, str]:
    texts: dict[str, str] = {}
    for row in _assistant_rows(db, session):
        for question in parse_json_list(row.questions):
            if isinstance(question, dict) and question.get("id"):
                texts[str(question["id"])] = str(question.get("text") or "")
    return texts


def render_user_turn(turn: int, content: str, answers: list[dict], question_texts: dict[str, str]) -> str:
    """One user turn as the model sees it later: answers first, then the text."""
    lines = [f"[Turn {turn}]"]
    for answer in answers:
        choice = answer.get("choice")
        if not choice:
            continue
        question = question_texts.get(str(answer.get("question_id")), "")
        lines.append(f"Answer to \"{question}\": {choice}" if question else f"Answer: {choice}")
    if content.strip():
        lines.append(content.strip())
    return "\n".join(lines)


def user_turn_texts(db: Session, session: AiFillSession) -> list[str]:
    """Every stored user turn rendered with render_user_turn, oldest first."""
    question_texts = _question_texts(db, session)
    texts: list[str] = []
    for row in list_messages(db, session):
        if row.role != "user":
            continue
        answers, _ = parse_answers(row.answers)
        texts.append(render_user_turn(row.turn, row.content, answers, question_texts))
    return texts


def user_history_text(db: Session, session: AiFillSession, max_chars: int) -> str:
    """
    The earlier user messages for the prompt. Longer than max_chars: the
    first turn is always kept, then the oldest of the others are dropped (a
    marker says so).
    """
    turns = user_turn_texts(db, session)
    if not turns:
        return ""
    text = "\n\n".join(turns)
    if len(text) <= max_chars:
        return text
    first, rest = turns[0], turns[1:]
    kept: list[str] = []
    used = len(first) + len(OMITTED_MARK) + 4
    for turn_text in reversed(rest):
        if used + len(turn_text) + 2 > max_chars:
            break
        kept.append(turn_text)
        used += len(turn_text) + 2
    return "\n\n".join([first[:max_chars], OMITTED_MARK, *reversed(kept)])


def latest_assistant(db: Session, session: AiFillSession) -> AiFillMessage | None:
    rows = _assistant_rows(db, session)
    return rows[-1] if rows else None


def open_questions(db: Session, session: AiFillSession) -> list[dict]:
    """The questions of the latest assistant turn (the only answerable ones)."""
    latest = latest_assistant(db, session)
    if latest is None:
        return []
    return [q for q in parse_json_list(latest.questions) if isinstance(q, dict)]


def last_proposals(db: Session, session: AiFillSession) -> list[dict]:
    latest = latest_assistant(db, session)
    if latest is None:
        return []
    return [p for p in parse_json_list(latest.proposals) if isinstance(p, dict)]


def ask_counts(db: Session, session: AiFillSession) -> dict[str, int]:
    """How many stored questions listed each field (a 2-field question counts for both)."""
    counts: dict[str, int] = {}
    for row in _assistant_rows(db, session):
        for question in parse_json_list(row.questions):
            if not isinstance(question, dict):
                continue
            for name in set(question.get("field_names") or []):
                counts[name] = counts.get(name, 0) + 1
    return counts


def fields_of_questions(db: Session, session: AiFillSession, question_ids: list[str]) -> set[str]:
    wanted = set(question_ids)
    names: set[str] = set()
    for row in _assistant_rows(db, session):
        for question in parse_json_list(row.questions):
            if isinstance(question, dict) and question.get("id") in wanted:
                names.update(question.get("field_names") or [])
    return names


def skipped_fields(db: Session, session: AiFillSession) -> set[str]:
    """Fields of every question the user skipped in an earlier turn."""
    skipped_ids: list[str] = []
    for row in list_messages(db, session):
        if row.role == "user":
            skipped_ids.extend(parse_answers(row.answers)[1])
    return fields_of_questions(db, session, skipped_ids) if skipped_ids else set()


def mark_completed(db: Session, session: AiFillSession) -> None:
    if session.status != "completed":
        session.status = "completed"
        db.flush()


def clear_session(db: Session, session: AiFillSession) -> None:
    """Delete the chat (messages go with it). Form values are not touched."""
    db.delete(session)
    db.flush()
