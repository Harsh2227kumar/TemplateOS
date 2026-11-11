"""
V1.7 Phase 2.2 API (Member 2): the AI fill assistant and the fit check.

Coverage:
- POST /documents/{id}/ai-fill/messages: proposals + questions returned and
  stored, stage and required counts, one lean ai_generations row and one
  audit row (neither holds the user's text), nothing written to
  document_values; turn 2 with a clicked choice (history sent to the model,
  locked fields never proposed); the clarification loop over four turns
  (attempts 1-3, then needs_user); skipped questions.
- GET (chat, open questions, budgets) and DELETE (chat gone, values kept,
  audited).
- Errors: 503 not configured / provider failure (nothing stored but the
  error row), 409 turn_limit, 422 long message / empty message / unknown
  form_state field, 403 other user, 404, 409 non-editable document.
- PUT /values accepts ai_action "ai_fill".
- Fit check: baseline computed once per template version, overflow, long
  fields, converter off, `fit` in the generate response, a failing fit check
  never fails the generation, GET /fit-report (latest, by version, 404, 403).
- GET /system/ai-config.

No network: the model client and the PDF converter are fakes.
"""

import io
import json
import logging
import os

import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

from app.core.config import settings  # noqa: E402
from app.crud.template_field_crud import create_field  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.ai_fill_message import AiFillMessage  # noqa: E402
from app.models.ai_fill_session import AiFillSession  # noqa: E402
from app.models.ai_generation import AiGeneration  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.document_value import DocumentValue  # noqa: E402
from app.models.template import Template  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.ai_fill import AiFillProposalOut, AiFillQuestionOut, AiFillTurn  # noqa: E402
from app.schemas.template_field import TemplateFieldCreate  # noqa: E402
from app.services import ai_service, document_generation, fit_check, pdf_service  # noqa: E402
from app.services.ai_service import AiUnavailableError  # noqa: E402
from app.services.field_placement import clear_budget_cache  # noqa: E402
from app.services.storage_service import storage_service  # noqa: E402

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_get_db():
    with TestSession() as db:
        yield db


client = TestClient(app)
OWNER = "p22_owner@example.com"
STRANGER = "p22_stranger@example.com"
DOCS = "/api/v1/documents"
MODEL = "test.claude-fill"
SECRET_PHRASE = "zebra-umbrella-harsh"
FIRST_MESSAGE = (
    f"hi i am harsh kumar roll 22cs045 {SECRET_PHRASE}, did projct on smart attendence, "
    "guide is dr mehta, sumbit on 3/4"
)


@pytest.fixture(scope="module", autouse=True)
def setup_db(tmp_path_factory):
    old = app.dependency_overrides.get(get_db)
    old_root = storage_service.root_path
    storage_service.root_path = tmp_path_factory.mktemp("p22-storage").resolve()
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    clear_budget_cache()
    yield
    Base.metadata.drop_all(bind=engine)
    storage_service.root_path = old_root
    clear_budget_cache()
    if old is not None:
        app.dependency_overrides[get_db] = old
    else:
        app.dependency_overrides.pop(get_db, None)


def pdf_with_pages(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class FakeConverter:
    """The baseline render has 1 page; generated documents have `pages`."""

    def __init__(self):
        self.pages = 1
        self.baseline_calls = 0

    def convert(self, docx_bytes: bytes, filename: str) -> bytes:
        if filename == "baseline.docx":
            self.baseline_calls += 1
            return pdf_with_pages(1)
        return pdf_with_pages(self.pages)


@pytest.fixture(autouse=True)
def converter(monkeypatch):
    fake = FakeConverter()
    monkeypatch.setattr(document_generation, "get_pdf_converter", lambda: fake)
    monkeypatch.setattr(pdf_service, "get_pdf_converter", lambda: fake)
    return fake


class FakeModel:
    """Stands in for the instructor client: returns queued AiFillTurn replies."""

    def __init__(self):
        self.replies: list = []
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    @property
    def last_prompt(self) -> str:
        return self.calls[-1]["messages"][0]["content"]


@pytest.fixture()
def model(monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr(settings, "aws_region", "ap-south-1")
    monkeypatch.setattr(settings, "bedrock_model_suggestions", MODEL)
    monkeypatch.setattr(settings, "bedrock_model_fill", "")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "test-key")
    monkeypatch.setattr(ai_service, "_build_client", lambda: fake)
    return fake


def _login(email: str, name: str) -> str:
    client.post("/api/v1/auth/signup", json={"full_name": name, "email": email, "password": "strong-password"})
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "strong-password"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def owner(setup_db) -> str:
    return _login(OWNER, "Harsh Owner")


@pytest.fixture(scope="module")
def stranger(setup_db) -> str:
    return _login(STRANGER, "Sam Stranger")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


FIELDS = [
    ("student_name", "text", True),
    ("roll_number", "text", True),
    ("abstract", "textarea", True),
    ("guide_name", "text", True),
    ("submission_date", "date", False),
    ("technologies", "list", False),
]


def _template_docx() -> bytes:
    document = DocxDocument()
    document.add_paragraph("Name: {{ student_name }}    Roll: {{ roll_number }}")
    document.add_paragraph("{{ abstract }}")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Guide"
    table.cell(0, 1).text = "{{ guide_name }}"
    document.add_paragraph("Submitted on {{ submission_date }}")
    document.add_paragraph("{{ technologies }}")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _make_template() -> int:
    stored = storage_service.save_bytes("templates_processed", "p22.docx", _template_docx())
    with TestSession() as session:
        owner_id = session.execute(select(User.id).where(User.email == OWNER)).scalar_one()
        template = Template(
            name="Project Report",
            category="report",
            visibility="public",
            uploaded_by=owner_id,
            status="field_configured",
            processed_file_path=stored.path,
        )
        session.add(template)
        session.commit()
        for name, field_type, required in FIELDS:
            create_field(
                session,
                template.id,
                TemplateFieldCreate(field_name=name, field_type=field_type, is_required=required),
            )
        return template.id


@pytest.fixture()
def draft(owner) -> int:
    response = client.post(
        f"{DOCS}/create", headers=_auth(owner), json={"template_id": _make_template(), "name": "My Report"}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def form_state(**values) -> list[dict]:
    """Every field of the form; values given as name=(value, origin) or name=value (origin ai)."""
    state = []
    for name, _type, _required in FIELDS:
        value = values.get(name, "")
        origin = "empty"
        if isinstance(value, tuple):
            value, origin = value
        elif value:
            origin = "ai"
        state.append({"field_name": name, "value": value, "origin": origin})
    return state


def send(token: str, document_id: int, message: str = "", **body):
    payload = {"message": message, "form_state": form_state(), **body}
    return client.post(f"{DOCS}/{document_id}/ai-fill/messages", headers=_auth(token), json=payload)


def proposal(name, value=None, items=None, confidence="high", **extra):
    return AiFillProposalOut(field_name=name, value=value, items=items, confidence=confidence, **extra)


def question(text, fields, choices=None, kind="missing"):
    return AiFillQuestionOut(text=text, field_names=fields, choices=choices or [], kind=kind)


FIRST_REPLY = AiFillTurn(
    message="I filled 3 fields. I have 2 questions.",
    proposals=[
        proposal("student_name", "Harsh Kumar", source_text="i am harsh kumar"),
        proposal("roll_number", "22CS045", source_text="roll 22cs045"),
        proposal("abstract", "This project develops a smart attendance system.", confidence="medium",
                 reason="Written from one line."),
        proposal("submission_date", "2026-04-03"),
        proposal("guide_name", "Dr. Mehta (9123456780)"),  # an invented phone number
    ],
    questions=[question("What is Dr. Mehta's full name?", ["guide_name"], kind="unclear")],
)


def _rows(model_class, **filters):
    with TestSession() as session:
        query = select(model_class)
        for name, value in filters.items():
            query = query.where(getattr(model_class, name) == value)
        return list(session.execute(query).scalars())


# ── a turn ───────────────────────────────────────────────────────


def test_first_turn_returns_proposals_and_questions_and_stores_the_chat(owner, draft, model, caplog):
    model.replies.append(FIRST_REPLY)
    with caplog.at_level(logging.DEBUG):
        response = send(owner, draft, FIRST_MESSAGE)
    assert response.status_code == 200, response.text
    body = response.json()

    proposals = {p["field_name"]: p for p in body["assistant_message"]["proposals"]}
    assert set(proposals) == {"student_name", "roll_number", "abstract"}
    assert proposals["roll_number"]["value"] == "22CS045"
    assert proposals["abstract"]["confidence"] == "medium"
    assert proposals["student_name"]["source_text"] == "i am harsh kumar"

    questions = body["assistant_message"]["questions"]
    assert [q["id"] for q in questions] == ["t1-q1", "t1-q2"]
    assert questions[0]["field_names"] == ["guide_name"] and questions[0]["attempt"] == 1
    # the ambiguous 3/4 date is asked with both readings instead of being filled
    assert questions[1]["field_names"] == ["submission_date"]
    assert questions[1]["choices"] == ["3 April 2026", "4 March 2026"]

    assert body["stage"] == "filling" and body["done"] is False
    assert body["missing_required"] == ["guide_name"] and body["needs_user"] == []
    assert (body["required_total"], body["required_filled"]) == (4, 3)
    assert body["session"]["turn_count"] == 1 and body["session"]["max_turns"] == settings.ai_fill_max_turns
    assert body["user_message"]["content"] == FIRST_MESSAGE
    assert body["assistant_message"]["stage"] == "filling"

    # The model got the field catalog, today's date and the message.
    call = model.calls[0]
    assert call["model"] == MODEL and call["response_model"] is AiFillTurn
    assert "key=student_name" in model.last_prompt and FIRST_MESSAGE in model.last_prompt
    assert "budget=120 chars" in model.last_prompt  # guide_name sits in a table cell

    # Nothing was saved to the form.
    assert _rows(DocumentValue, document_id=draft) == []

    # One lean AI row and one audit row; neither holds the user's text.
    generation = _rows(AiGeneration, document_id=draft)
    assert len(generation) == 1
    assert (generation[0].action_type, generation[0].status, generation[0].suggestions_count) == ("ai_fill", "success", 3)
    assert generation[0].model == MODEL and generation[0].detail == "questions=2, dropped=0, low=2"
    audit = _rows(AuditLog, action="ai.fill_document", entity_id=draft)
    assert len(audit) == 1
    details = json.loads(audit[0].details)
    assert details["proposed_fields"] == ["student_name", "roll_number", "abstract"]
    assert details["question_count"] == 2 and details["stage"] == "filling"
    for text in (generation[0].detail, audit[0].summary, audit[0].details, caplog.text):
        assert SECRET_PHRASE not in text


def test_second_turn_uses_history_answers_and_respects_locked_fields(owner, draft, model):
    model.replies.append(FIRST_REPLY)
    assert send(owner, draft, FIRST_MESSAGE).status_code == 200

    model.replies.append(
        AiFillTurn(
            message="Done.",
            proposals=[
                proposal("submission_date", "2026-04-03"),
                proposal("guide_name", "Dr. Rakesh Mehta"),
                proposal("student_name", "Harsh K."),  # the user edited this field: locked
            ],
        )
    )
    response = send(
        owner,
        draft,
        "dr rakesh mehta",
        answers=[{"question_id": "t1-q2", "choice": "3 April 2026"}, {"question_id": "t9-q9", "choice": "x"}],
        form_state=form_state(
            student_name=("Harsh Kumar Singh", "user"),
            roll_number="22CS045",
            abstract="This project develops a smart attendance system.",
        ),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    proposals = {p["field_name"]: p for p in body["assistant_message"]["proposals"]}
    assert set(proposals) == {"submission_date", "guide_name"}
    assert proposals["submission_date"]["confidence"] == "high"  # the clicked choice settled it
    assert (body["stage"], body["done"], body["missing_required"]) == ("ready", True, [])
    assert body["user_message"]["answers"] == [{"question_id": "t1-q2", "choice": "3 April 2026"}]
    assert body["session"]["status"] == "completed"

    prompt = model.last_prompt
    assert f"[Turn 1]\n{FIRST_MESSAGE}" in prompt
    assert "the user chose: 3 April 2026" in prompt
    assert "status=LOCKED (written by the user)" in prompt
    assert "What is Dr. Mehta's full name? -> see NEW MESSAGE" in prompt


def test_clarification_loop_asks_again_then_hands_the_field_to_the_user(owner, draft, model):
    filled = form_state(student_name="Harsh Kumar", roll_number="22CS045", abstract="A project.")
    asks = AiFillTurn(message="I still need the guide's name.", questions=[
        question("What is the guide's full name?", ["guide_name"], kind="unclear")
    ])
    attempts = []
    for turn in range(1, 4):
        model.replies.append(asks)
        body = send(owner, draft, f"it is mehta sir {turn}", form_state=filled).json()
        attempts.append(body["assistant_message"]["questions"][0]["attempt"])
        assert body["stage"] == "filling" and body["needs_user"] == []
    assert attempts == [1, 2, 3]

    model.replies.append(asks)
    body = send(owner, draft, "mehta", form_state=filled).json()
    assert body["assistant_message"]["questions"] == []
    assert body["needs_user"] == ["guide_name"] and body["missing_required"] == ["guide_name"]
    assert (body["stage"], body["done"]) == ("ready", True)
    assert "Please fill it in the form" in body["assistant_message"]["content"]
    assert "ask=ask_limit_reached" in model.last_prompt and "asked=3 times" in model.last_prompt


def test_skipped_question_is_not_asked_again(owner, draft, model):
    filled = form_state(student_name="Harsh Kumar", roll_number="22CS045", abstract="A project.")
    asks = AiFillTurn(message="One question.", questions=[question("Guide's name?", ["guide_name"])])
    model.replies.append(asks)
    assert send(owner, draft, "hello there", form_state=filled).json()["assistant_message"]["questions"]

    model.replies.append(asks)
    body = send(owner, draft, "moving on", skipped=["t1-q1"], form_state=filled).json()
    assert body["assistant_message"]["questions"] == []
    assert body["needs_user"] == ["guide_name"] and body["stage"] == "ready"
    assert body["user_message"]["skipped"] == ["t1-q1"]
    assert "SKIPPED by the user" in model.last_prompt and "ask=skipped" in model.last_prompt


def test_get_and_clear_the_chat(owner, draft, model):
    empty = client.get(f"{DOCS}/{draft}/ai-fill", headers=_auth(owner))
    assert empty.status_code == 200
    assert empty.json()["session"] is None and empty.json()["messages"] == []
    budgets = {b["field_name"]: b for b in empty.json()["budgets"]}
    assert budgets["guide_name"] == {
        "field_name": "guide_name", "placement": "table_cell", "budget": 120, "unit": "chars",
        "item_budget": None, "hard": False,
    }
    assert budgets["abstract"]["budget"] == 1200 and budgets["technologies"]["unit"] == "items"
    assert "submission_date" not in budgets

    saved = client.put(
        f"{DOCS}/{draft}/values",
        headers=_auth(owner),
        json={"values": [{"field_name": "student_name", "value": "Harsh Kumar", "ai_modified": True,
                          "ai_action": "ai_fill"}]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["values"][0]["ai_action"] == "ai_fill"

    model.replies.append(FIRST_REPLY)
    assert send(owner, draft, FIRST_MESSAGE).status_code == 200
    chat = client.get(f"{DOCS}/{draft}/ai-fill", headers=_auth(owner)).json()
    assert [(m["turn"], m["role"]) for m in chat["messages"]] == [(1, "user"), (1, "assistant")]
    assert [q["id"] for q in chat["open_questions"]] == ["t1-q1", "t1-q2"]
    assert chat["session"]["turn_count"] == 1

    cleared = client.delete(f"{DOCS}/{draft}/ai-fill", headers=_auth(owner))
    assert cleared.status_code == 204
    assert client.delete(f"{DOCS}/{draft}/ai-fill", headers=_auth(owner)).status_code == 204
    assert client.get(f"{DOCS}/{draft}/ai-fill", headers=_auth(owner)).json()["session"] is None
    assert _rows(AiFillSession, document_id=draft) == []
    assert len(_rows(AuditLog, action="ai.fill_clear", entity_id=draft)) == 1
    assert [v.value for v in _rows(DocumentValue, document_id=draft)] == ["Harsh Kumar"]


# ── errors ───────────────────────────────────────────────────────


def test_not_configured_is_503_and_stores_nothing(owner, draft, monkeypatch):
    monkeypatch.setattr(settings, "aws_region", None)
    response = send(owner, draft, FIRST_MESSAGE)
    assert response.status_code == 503
    assert _rows(AiFillSession, document_id=draft) == []
    assert _rows(AiGeneration, document_id=draft) == []


def test_provider_failure_is_503_with_only_an_error_row(owner, draft, model):
    model.replies.append(AiUnavailableError("AI is currently unavailable: throttled"))
    response = send(owner, draft, FIRST_MESSAGE)
    assert response.status_code == 503
    assert "throttled" in response.json()["detail"]
    assert _rows(AiFillSession, document_id=draft) == []
    rows = _rows(AiGeneration, document_id=draft)
    assert [(r.action_type, r.status) for r in rows] == [("ai_fill", "error")]
    assert SECRET_PHRASE not in (rows[0].detail or "")

    # A raw provider exception is classified and mapped the same way.
    model.replies.append(RuntimeError("boom"))
    assert send(owner, draft, FIRST_MESSAGE).status_code == 503
    assert _rows(AiFillSession, document_id=draft) == []


def test_turn_limit(owner, draft, model, monkeypatch):
    monkeypatch.setattr(settings, "ai_fill_max_turns", 1)
    model.replies.append(FIRST_REPLY)
    assert send(owner, draft, FIRST_MESSAGE).status_code == 200
    response = send(owner, draft, "one more")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "turn_limit"
    assert len(model.calls) == 1


def test_validation_errors(owner, draft, model, monkeypatch):
    monkeypatch.setattr(settings, "ai_fill_max_message_chars", 100)
    assert send(owner, draft, "x" * 101).status_code == 422
    assert send(owner, draft, "   ").status_code == 422  # nothing to say and no answer
    unknown = send(owner, draft, "hello", form_state=[{"field_name": "nope", "value": "", "origin": "empty"}])
    assert unknown.status_code == 422
    assert unknown.json()["detail"] == [{"field_name": "nope", "error": "Field not found in template"}]
    assert model.calls == []


def test_only_the_owner_of_an_editable_draft(owner, stranger, draft, model):
    for call in (
        lambda: send(stranger, draft, "hello"),
        lambda: client.get(f"{DOCS}/{draft}/ai-fill", headers=_auth(stranger)),
        lambda: client.delete(f"{DOCS}/{draft}/ai-fill", headers=_auth(stranger)),
        lambda: client.get(f"{DOCS}/{draft}/fit-report", headers=_auth(stranger)),
    ):
        assert call().status_code == 403
    assert send(owner, 999_999, "hello").status_code == 404
    assert client.get(f"{DOCS}/{draft}/ai-fill").status_code == 401

    with TestSession() as session:
        session.get(Document, draft).status = "submitted"
        session.commit()
    assert send(owner, draft, "hello").status_code == 409
    assert client.get(f"{DOCS}/{draft}/ai-fill", headers=_auth(owner)).status_code == 409
    assert model.calls == []


def test_ai_config(owner, model, monkeypatch):
    assert client.get("/api/v1/system/ai-config").status_code == 401
    response = client.get("/api/v1/system/ai-config", headers=_auth(owner))
    assert response.json() == {"enabled": True, "fill_enabled": True}
    monkeypatch.setattr(settings, "aws_region", None)
    response = client.get("/api/v1/system/ai-config", headers=_auth(owner))
    assert response.json() == {"enabled": False, "fill_enabled": False}


# ── fit check ────────────────────────────────────────────────────


def _save_all(token: str, document_id: int, abstract: str = "A short abstract."):
    values = [
        {"field_name": "student_name", "value": "Harsh Kumar", "ai_modified": True, "ai_action": "ai_fill"},
        {"field_name": "roll_number", "value": "22CS045"},
        {"field_name": "abstract", "value": abstract},
        {"field_name": "guide_name", "value": "Dr. Rakesh Mehta"},
        {"field_name": "technologies", "value": json.dumps(["Python", "OpenCV"])},
    ]
    response = client.put(f"{DOCS}/{document_id}/values", headers=_auth(token), json={"values": values})
    assert response.status_code == 200, response.text


def _generate(token: str, document_id: int):
    return client.post(f"{DOCS}/{document_id}/generate", headers=_auth(token))


def test_generate_reports_fit_and_caches_the_baseline(owner, draft, converter):
    _save_all(owner, draft)
    first = _generate(owner, draft)
    assert first.status_code == 200, first.text
    assert first.json()["fit"] == {
        "version": 1, "pages": 1, "baseline_pages": 1, "overflow": False, "long_fields": [],
        "checked": True, "reason": None,
    }

    converter.pages = 3
    _save_all(owner, draft, abstract="word " * 300)  # 1500 characters, budget 1200
    second = _generate(owner, draft)
    fit = second.json()["fit"]
    assert (fit["version"], fit["pages"], fit["baseline_pages"], fit["overflow"]) == (2, 3, 1, True)
    assert fit["long_fields"] == [
        {"field_name": "abstract", "label": "abstract", "length": 1500, "budget": 1200, "unit": "chars"}
    ]
    assert converter.baseline_calls == 1  # one baseline render per template version

    latest = client.get(f"{DOCS}/{draft}/fit-report", headers=_auth(owner))
    assert latest.status_code == 200 and latest.json() == fit
    older = client.get(f"{DOCS}/{draft}/fit-report?version=1", headers=_auth(owner)).json()
    assert (older["version"], older["overflow"], older["long_fields"]) == (1, False, [])
    assert client.get(f"{DOCS}/{draft}/fit-report?version=9", headers=_auth(owner)).status_code == 404
    assert converter.baseline_calls == 1

    # A new template version gets a new baseline.
    with TestSession() as session:
        document = session.get(Document, draft)
        session.get(Template, document.template_id).version += 1
        session.commit()
    _generate(owner, draft)
    assert converter.baseline_calls == 2


def test_fit_without_a_pdf_still_lists_long_fields(owner, draft, monkeypatch):
    monkeypatch.setattr(document_generation, "get_pdf_converter", lambda: None)
    monkeypatch.setattr(pdf_service, "get_pdf_converter", lambda: None)
    _save_all(owner, draft, abstract="word " * 300)
    fit = _generate(owner, draft).json()["fit"]
    assert (fit["checked"], fit["pages"], fit["overflow"], fit["reason"]) == (False, None, False, "No PDF for this version")
    assert [f["field_name"] for f in fit["long_fields"]] == ["abstract"]


def test_fit_before_any_generation_is_404(owner, draft):
    assert client.get(f"{DOCS}/{draft}/fit-report", headers=_auth(owner)).status_code == 404


def test_a_failing_fit_check_never_fails_the_generation(owner, draft, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("fit check exploded")

    monkeypatch.setattr(fit_check, "fit_report", broken)
    _save_all(owner, draft)
    response = _generate(owner, draft)
    assert response.status_code == 200, response.text
    assert response.json()["fit"] is None and response.json()["version"] == 1


def test_baseline_survives_a_failing_conversion(owner, draft, converter, monkeypatch):
    def broken(_docx, _name):
        raise pdf_service.PdfConversionError("converter down")

    _save_all(owner, draft)
    real = converter.convert
    monkeypatch.setattr(
        converter, "convert", lambda docx, name: broken(docx, name) if name == "baseline.docx" else real(docx, name)
    )
    fit = _generate(owner, draft).json()["fit"]
    assert (fit["checked"], fit["pages"], fit["baseline_pages"], fit["overflow"]) == (True, 1, None, False)
    with TestSession() as session:
        template = session.get(Template, session.get(Document, draft).template_id)
        assert template.baseline_pages is None  # nothing cached: the next check tries again
    assert _rows(AiFillMessage) is not None
