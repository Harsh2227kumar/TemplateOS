"""
V1.7 Phase 2.2 data layer (Member 3): the AI fill chat.

Coverage:
- get_or_create_session: one chat per document.
- add_turn: turn numbering, JSON round trip, distinct filled_count, stage.
- user_history_text: answers rendered, the first turn always kept, the
  oldest of the others dropped when over the limit.
- open_questions / last_proposals: latest assistant turn only.
- ask_counts (a multi-field question counts for each field) and
  skipped_fields.
- clear_session and the cascade from documents.
- parse_json_list / parse_answers on bad data.

Database: in-memory SQLite with PRAGMA foreign_keys=ON.
"""

import os

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

import app.models  # noqa: F401,E402
from app.crud import ai_fill_crud as chat  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.ai_fill_message import AiFillMessage  # noqa: E402
from app.models.ai_fill_session import AiFillSession  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.template import Template  # noqa: E402
from app.models.user import User  # noqa: E402

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    with TestSession() as session:
        yield session


_n = {"value": 0}


@pytest.fixture
def document(db) -> Document:
    _n["value"] += 1
    user = User(email=f"fill{_n['value']}@example.com", full_name="Fill User", role="faculty")
    db.add(user)
    db.flush()
    template = Template(name="Report", category="report", visibility="private", status="active", uploaded_by=user.id)
    db.add(template)
    db.flush()
    doc = Document(template_id=template.id, created_by=user.id, name="Draft", status="draft")
    db.add(doc)
    db.commit()
    return doc


def _turn(db, session, text, *, answers=None, skipped=None, proposals=None, questions=None, stage="filling"):
    return chat.add_turn(
        db,
        session,
        user_text=text,
        answers=answers or [],
        skipped=skipped or [],
        assistant_text="ok",
        proposals=proposals or [],
        questions=questions or [],
        stage=stage,
        model="test-model",
    )


def _proposal(name, confidence="high"):
    return {"field_name": name, "value": "v", "items": None, "confidence": confidence, "over_budget": False}


def _question(qid, text, fields, choices=None):
    return {"id": qid, "text": text, "field_names": fields, "choices": choices or [], "kind": "missing", "attempt": 1}


def test_one_session_per_document(db, document):
    assert chat.get_session(db, document.id) is None
    first = chat.get_or_create_session(db, document.id, document.created_by)
    second = chat.get_or_create_session(db, document.id, document.created_by)
    db.commit()
    assert first.id == second.id
    assert (first.status, first.turn_count, first.filled_count) == ("active", 0, 0)


def test_add_turn_numbers_turns_and_round_trips_json(db, document):
    session = chat.get_or_create_session(db, document.id, document.created_by)
    user_1, assistant_1 = _turn(
        db,
        session,
        "i am harsh, roll 22cs045",
        proposals=[_proposal("student_name"), _proposal("roll_number", "medium"), _proposal("guess", "low")],
        questions=[_question("t1-q1", "Which year?", ["academic_year"], ["2025-26", "2026-27"])],
        stage="asking",
    )
    user_2, assistant_2 = _turn(
        db,
        session,
        "",
        answers=[{"question_id": "t1-q1", "choice": "2025-26"}],
        skipped=["t1-q9"],
        proposals=[_proposal("student_name"), _proposal("academic_year")],
        stage="ready",
    )
    db.commit()

    assert (user_1.turn, assistant_1.turn, user_2.turn, assistant_2.turn) == (1, 1, 2, 2)
    assert (assistant_1.stage, assistant_2.stage, assistant_2.model) == ("asking", "ready", "test-model")
    assert user_1.stage is None
    # high / medium proposals, distinct across turns (the low one is not counted)
    assert (session.turn_count, session.filled_count) == (2, 3)

    messages = chat.list_messages(db, session)
    assert [(m.turn, m.role) for m in messages] == [(1, "user"), (1, "assistant"), (2, "user"), (2, "assistant")]
    assert chat.parse_answers(user_2.answers) == ([{"question_id": "t1-q1", "choice": "2025-26"}], ["t1-q9"])
    assert chat.parse_json_list(assistant_1.questions)[0]["choices"] == ["2025-26", "2026-27"]
    assert [p["field_name"] for p in chat.last_proposals(db, session)] == ["student_name", "academic_year"]
    # Only the latest assistant turn has answerable questions.
    assert chat.open_questions(db, session) == []
    # The relationship gives the same chat order.
    db.refresh(session)
    assert [(m.turn, m.role) for m in session.messages] == [(m.turn, m.role) for m in messages]


def test_history_renders_answers_and_keeps_the_first_turn(db, document):
    session = chat.get_or_create_session(db, document.id, document.created_by)
    _turn(db, session, "first message with the main facts",
          questions=[_question("t1-q1", "Is it 3 April or 4 March?", ["submission_date"])])
    _turn(db, session, "second " + "x" * 300, answers=[{"question_id": "t1-q1", "choice": "3 April 2026"}])
    _turn(db, session, "third " + "y" * 300)
    _turn(db, session, "fourth short")
    db.commit()

    full = chat.user_history_text(db, session, max_chars=10_000)
    assert full.startswith("[Turn 1]\nfirst message with the main facts")
    assert 'Answer to "Is it 3 April or 4 March?": 3 April 2026' in full
    assert full.index("[Turn 2]") < full.index("[Turn 3]") < full.index("[Turn 4]")

    short = chat.user_history_text(db, session, max_chars=450)
    assert short.startswith("[Turn 1]\nfirst message with the main facts")
    assert chat.OMITTED_MARK in short
    assert "[Turn 4]\nfourth short" in short
    assert "[Turn 2]" not in short  # the oldest of the others goes first
    assert len(short) <= 450

    assert chat.user_turn_texts(db, session)[3] == "[Turn 4]\nfourth short"


def test_history_is_empty_without_turns(db, document):
    session = chat.get_or_create_session(db, document.id, document.created_by)
    assert chat.user_history_text(db, session, max_chars=1000) == ""
    assert chat.open_questions(db, session) == []
    assert chat.last_proposals(db, session) == []
    assert chat.ask_counts(db, session) == {}
    assert chat.skipped_fields(db, session) == set()


def test_ask_counts_and_skipped_fields(db, document):
    session = chat.get_or_create_session(db, document.id, document.created_by)
    _turn(db, session, "one", questions=[
        _question("t1-q1", "Guide's full name and department?", ["guide_name", "guide_department"]),
        _question("t1-q2", "Which year?", ["academic_year"]),
    ])
    _turn(db, session, "two", skipped=["t1-q2"], questions=[
        _question("t2-q1", "Guide's first name?", ["guide_name"]),
    ])
    _turn(db, session, "three", questions=[_question("t3-q1", "Guide's first name, please?", ["guide_name"])])
    db.commit()

    assert chat.ask_counts(db, session) == {"guide_name": 3, "guide_department": 1, "academic_year": 1}
    assert chat.skipped_fields(db, session) == {"academic_year"}
    assert chat.fields_of_questions(db, session, ["t1-q1", "nope"]) == {"guide_name", "guide_department"}
    assert [q["id"] for q in chat.open_questions(db, session)] == ["t3-q1"]


def test_mark_completed_and_clear(db, document):
    session = chat.get_or_create_session(db, document.id, document.created_by)
    _turn(db, session, "hello")
    chat.mark_completed(db, session)
    db.commit()
    assert session.status == "completed"
    session_id = session.id

    chat.clear_session(db, session)
    db.commit()
    assert chat.get_session(db, document.id) is None
    assert db.execute(select(AiFillMessage).where(AiFillMessage.session_id == session_id)).scalars().all() == []


def test_document_delete_removes_the_chat(db, document):
    session = chat.get_or_create_session(db, document.id, document.created_by)
    _turn(db, session, "hello")
    db.commit()
    session_id, document_id = session.id, document.id
    db.expunge_all()

    db.delete(db.get(Document, document_id))
    db.commit()
    assert db.get(AiFillSession, session_id) is None
    assert db.execute(select(AiFillMessage).where(AiFillMessage.session_id == session_id)).scalars().all() == []


def test_models_reject_unknown_values(db, document):
    with pytest.raises(ValueError):
        AiFillSession(document_id=document.id, user_id=document.created_by, status="paused")
    with pytest.raises(ValueError):
        AiFillMessage(session_id=1, turn=1, role="system", content="x")
    with pytest.raises(ValueError):
        AiFillMessage(session_id=1, turn=1, role="assistant", content="x", stage="thinking")


@pytest.mark.parametrize("text", [None, "", "not json", '{"a": 1}', "12"])
def test_parse_json_list_is_safe(text):
    assert chat.parse_json_list(text) == []


@pytest.mark.parametrize("text", [None, "", "not json", "[1, 2]", '{"answers": "x", "skipped": 3}'])
def test_parse_answers_is_safe(text):
    assert chat.parse_answers(text) == ([], [])
