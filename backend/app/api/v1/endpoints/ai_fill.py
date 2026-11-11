"""
AI fill assistant endpoints (V1.7 Phase 2.2 - Member 2).

- GET    /documents/{id}/ai-fill           the chat, its open questions, budgets
- POST   /documents/{id}/ai-fill/messages  one chat turn -> proposals + questions
- DELETE /documents/{id}/ai-fill           clear the chat (values untouched)
- GET    /documents/{id}/fit-report        does a generated version fit the template

Rules:
- PROPOSALS ONLY: no route here writes document_values or generates files.
  The browser applies proposals to the form and saves through
  PUT /documents/{id}/values (ai_action "ai_fill").
- Owner only, and only while the document can still be edited.
- The user's text is stored in ai_fill_messages and nowhere else:
  ai_generations, audit_logs and log lines carry counts and field names.
- 503 (AI not configured / provider failure) stores nothing but the lean
  ai_generations error row; the browser keeps the typed message.
"""

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.crud import ai_fill_crud
from app.crud.ai_generation_crud import log_ai_generation
from app.crud.document_crud import get_document_by_id
from app.crud.document_version_crud import get_version, latest_version_number
from app.crud.template_crud import get_template_by_id
from app.crud.template_field_crud import get_fields_by_template
from app.models.ai_fill_message import AiFillMessage
from app.models.ai_fill_session import AiFillSession
from app.models.document import Document
from app.models.template import Template
from app.models.user import User
from app.schemas.ai_fill import (
    AiFillMessageCreate,
    AiFillMessageRead,
    AiFillProposalRead,
    AiFillQuestionRead,
    AiFillSessionInfo,
    AiFillSessionRead,
    AiFillTurnResponse,
    FieldBudgetRead,
    FitReport,
    QuestionAnswer,
)
from app.services import ai_fill_service, audit_service, fit_check
from app.services.ai_service import AiUnavailableError
from app.services.document_permissions import document_permissions, require_document_viewer
from app.services.field_placement import cached_field_budgets

router = APIRouter()
logger = logging.getLogger(__name__)

AI_NOT_CONFIGURED = "AI is not configured on this server"
TURN_LIMIT = "This chat reached its limit. Clear the chat to start again."


def _editable_document(db, user: User, document_id: int) -> tuple[Document, Template]:
    """The caller's own, still editable draft and its template."""
    document = get_document_by_id(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.created_by != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You can only fill your own drafts"
        )
    if not document_permissions(user, document).can_edit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This document can no longer be edited"
        )
    template = get_template_by_id(db, document.template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return document, template


def _session_info(session: AiFillSession) -> AiFillSessionInfo:
    return AiFillSessionInfo(
        id=session.id,
        status=session.status,
        turn_count=session.turn_count,
        max_turns=settings.ai_fill_max_turns,
    )


def _questions(raw: list) -> list[AiFillQuestionRead]:
    questions: list[AiFillQuestionRead] = []
    for item in raw:
        try:
            questions.append(AiFillQuestionRead.model_validate(item))
        except ValueError:  # a row written by an older / broken build
            continue
    return questions


def _proposals(raw: list) -> list[AiFillProposalRead]:
    proposals: list[AiFillProposalRead] = []
    for item in raw:
        try:
            proposals.append(AiFillProposalRead.model_validate(item))
        except ValueError:
            continue
    return proposals


def message_read(message: AiFillMessage) -> AiFillMessageRead:
    answers, skipped = ai_fill_crud.parse_answers(message.answers)
    parsed_answers: list[QuestionAnswer] = []
    for answer in answers:
        try:
            parsed_answers.append(QuestionAnswer.model_validate(answer))
        except ValueError:
            continue
    return AiFillMessageRead(
        id=message.id,
        turn=message.turn,
        role=message.role,
        content=message.content,
        answers=parsed_answers,
        skipped=skipped,
        proposals=_proposals(ai_fill_crud.parse_json_list(message.proposals)),
        questions=_questions(ai_fill_crud.parse_json_list(message.questions)),
        stage=message.stage,
        created_at=message.created_at,
    )


def _budget_list(template: Template, fields) -> list[FieldBudgetRead]:
    budgets = cached_field_budgets(template, fields)
    return [FieldBudgetRead.model_validate(budgets[f.field_name]) for f in fields if f.field_name in budgets]


@router.get(
    "/{document_id}/ai-fill",
    response_model=AiFillSessionRead,
    summary="The AI fill chat of a draft",
)
def get_ai_fill(db: DbSession, current_user: CurrentUser, document_id: int) -> AiFillSessionRead:
    """
    The stored chat (empty before the first message), the questions that can
    still be answered (latest turn) and each field's length budget.
    """
    document, template = _editable_document(db, current_user, document_id)
    fields = get_fields_by_template(db, template.id)
    budgets = _budget_list(template, fields)
    session = ai_fill_crud.get_session(db, document.id)
    if session is None:
        return AiFillSessionRead(budgets=budgets)
    return AiFillSessionRead(
        session=_session_info(session),
        messages=[message_read(m) for m in ai_fill_crud.list_messages(db, session)],
        open_questions=_questions(ai_fill_crud.open_questions(db, session)),
        budgets=budgets,
    )


def _guard_texts(db, session: AiFillSession | None) -> list[str]:
    """What the user wrote so far (messages and clicked choices), for the fact guard."""
    if session is None:
        return []
    texts: list[str] = []
    for message in ai_fill_crud.list_messages(db, session):
        if message.role != "user":
            continue
        texts.append(message.content)
        answers, _ = ai_fill_crud.parse_answers(message.answers)
        texts.extend(str(a["choice"]) for a in answers if a.get("choice"))
    return texts


@router.post(
    "/{document_id}/ai-fill/messages",
    response_model=AiFillTurnResponse,
    summary="Send a message to the AI fill assistant",
)
def send_ai_fill_message(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
    payload: AiFillMessageCreate,
    http_request: Request,
) -> AiFillTurnResponse:
    """
    One chat turn. The reply holds proposals (never saved by the server), up
    to AI_FILL_MAX_QUESTIONS questions and the stage of the clarification
    loop (asking / filling / ready).

    - 503 when AI is not configured or the provider fails: nothing is stored
    - 409 {"code": "turn_limit"} after AI_FILL_MAX_TURNS turns
    - 422 [{field_name, error}] for a form_state field the template does not have
    - 404 / 403 / 409 like the other draft routes (owner, editable)
    """
    document, template = _editable_document(db, current_user, document_id)
    if not settings.ai_is_configured or not settings.fill_model:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=AI_NOT_CONFIGURED)

    fields = get_fields_by_template(db, template.id)
    known = {f.field_name for f in fields}
    unknown = [item.field_name for item in payload.form_state if item.field_name not in known]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"field_name": name, "error": "Field not found in template"} for name in unknown],
        )

    session = ai_fill_crud.get_session(db, document.id)
    if session is not None and session.turn_count >= settings.ai_fill_max_turns:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": TURN_LIMIT, "code": "turn_limit"},
        )

    # Earlier turns: only the latest turn's questions can be answered / skipped.
    open_questions = ai_fill_crud.open_questions(db, session) if session else []
    open_by_id = {str(q.get("id")): q for q in open_questions}
    answers = [a for a in payload.answers if a.question_id in open_by_id]
    chosen = {a.question_id: a.choice.strip() for a in answers if a.choice and a.choice.strip()}
    skipped_ids = [qid for qid in dict.fromkeys(payload.skipped) if qid in open_by_id and qid not in chosen]
    ask_counts = ai_fill_crud.ask_counts(db, session) if session else {}
    skipped_names = ai_fill_crud.skipped_fields(db, session) if session else set()
    for question_id in skipped_ids:
        skipped_names.update(open_by_id[question_id].get("field_names") or [])
    history = (
        ai_fill_crud.user_history_text(db, session, settings.ai_fill_max_history_chars) if session else ""
    )
    user_texts = _guard_texts(db, session) + [payload.message, *chosen.values()]

    budgets = cached_field_budgets(template, fields)
    state = {item.field_name: item for item in payload.form_state}
    at_limit, still_skipped = ai_fill_service.blocked_fields(
        ask_counts, skipped_names, ai_fill_service.mentioned_fields(fields, payload.message)
    )
    turn_number = (session.turn_count if session else 0) + 1
    today = date.today()
    user_content = ai_fill_service.build_user_content(
        catalog=ai_fill_service.build_field_catalog(fields, budgets, state, ask_counts, at_limit, still_skipped),
        history_text=history,
        open_questions=open_questions,
        answers=chosen,
        skipped_ids=skipped_ids,
        message=payload.message,
        today=today,
    )

    logger.info(
        "AI fill turn started: document=%s template=%s user=%s turn=%s fields=%s chars=%s",
        document.id, template.id, current_user.id, turn_number, len(fields), len(payload.message),
    )
    try:
        raw_turn = ai_fill_service.run_turn(user_content)
    except AiUnavailableError as exc:
        log_ai_generation(
            db,
            action_type=ai_fill_service.FILL_ACTION,
            model=settings.fill_model or "unconfigured",
            template_id=template.id,
            document_id=document.id,
            created_by=current_user.id,
            status="error",
            detail=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    processed = ai_fill_service.postprocess(
        raw_turn,
        fields=fields,
        budgets=budgets,
        form_state=payload.form_state,
        user_texts=user_texts,
        turn_number=turn_number,
        ask_counts=ask_counts,
        skipped=skipped_names,
        message=payload.message,
        today=today,
    )

    if session is None:
        session = ai_fill_crud.get_or_create_session(db, document.id, current_user.id)
    user_message, assistant_message = ai_fill_crud.add_turn(
        db,
        session,
        user_text=payload.message,
        answers=[{"question_id": a.question_id, "choice": chosen.get(a.question_id)} for a in answers],
        skipped=skipped_ids,
        assistant_text=processed.message,
        proposals=[p.model_dump() for p in processed.proposals],
        questions=[q.model_dump() for q in processed.questions],
        stage=processed.stage,
        model=settings.fill_model,
    )
    if processed.done:
        ai_fill_crud.mark_completed(db, session)

    counts = processed.counts
    audit_service.record(
        db,
        http_request,
        actor=current_user,
        action="ai.fill_document",
        entity_type="document",
        entity_id=document.id,
        summary=(
            f"AI fill turn {turn_number} on '{document.name}': {counts['kept']} field(s) proposed, "
            f"{counts['questions']} question(s)"
        ),
        details={
            "turn": turn_number,
            "stage": processed.stage,
            "proposed_fields": [p.field_name for p in processed.proposals],
            "question_count": counts["questions"],
            "dropped": counts["dropped"],
            "template_id": template.id,
        },
        template=template,
    )
    # Commits the turn, the audit row and the lean AI row together.
    log_ai_generation(
        db,
        action_type=ai_fill_service.FILL_ACTION,
        model=settings.fill_model,
        template_id=template.id,
        document_id=document.id,
        created_by=current_user.id,
        suggestions_count=counts["kept"],
        detail=f"questions={counts['questions']}, dropped={counts['dropped']}, low={counts['low']}",
    )
    logger.info(
        "AI fill turn done: document=%s turn=%s stage=%s kept=%s dropped=%s questions=%s",
        document.id, turn_number, processed.stage, counts["kept"], counts["dropped"], counts["questions"],
    )

    return AiFillTurnResponse(
        session=_session_info(session),
        user_message=message_read(user_message),
        assistant_message=message_read(assistant_message),
        stage=processed.stage,
        missing_required=processed.missing_required,
        needs_user=processed.needs_user,
        required_total=processed.required_total,
        required_filled=processed.required_filled,
        done=processed.done,
    )


@router.delete(
    "/{document_id}/ai-fill",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear the AI fill chat of a draft",
)
def clear_ai_fill(
    db: DbSession, current_user: CurrentUser, document_id: int, http_request: Request
) -> Response:
    """Delete the chat. The form's values are not touched. 204 also without a chat."""
    document, template = _editable_document(db, current_user, document_id)
    session = ai_fill_crud.get_session(db, document.id)
    if session is not None:
        turns = session.turn_count
        ai_fill_crud.clear_session(db, session)
        audit_service.record_and_commit(
            db,
            http_request,
            actor=current_user,
            action="ai.fill_clear",
            entity_type="document",
            entity_id=document.id,
            summary=f"Cleared the AI fill chat of '{document.name}' ({turns} turn(s))",
            details={"turns": turns, "template_id": template.id},
            template=template,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def document_fit_report(db, document: Document, version_number: int | None) -> FitReport:
    """The fit report of one version (default: the latest). 404 for an unknown version."""
    number = version_number or latest_version_number(db, document.id)
    version = get_version(db, document.id, number) if number else None
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    template = get_template_by_id(db, document.template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    fields = get_fields_by_template(db, template.id)
    report = fit_check.fit_report(db, template, version, fields, cached_field_budgets(template, fields))
    db.commit()  # a freshly computed baseline page count
    return report


@router.get(
    "/{document_id}/fit-report",
    response_model=FitReport,
    summary="Does a generated version fit the template?",
)
def get_fit_report(
    db: DbSession,
    current_user: CurrentUser,
    document_id: int,
    version: int | None = Query(default=None, ge=1),
) -> FitReport:
    """
    Pages of the version's PDF against the template's baseline, and the
    fields longer than their budget. Advisory only.
    """
    document = get_document_by_id(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    require_document_viewer(current_user, document)
    return document_fit_report(db, document, version)
