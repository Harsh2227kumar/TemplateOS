"""
V1.7 Phase 2.2 (Member 2): the deterministic post-processing of an AI fill
turn (app.services.ai_fill_service.postprocess) and its helpers. Pure: no
database, no model.

Coverage:
- proposals: unknown / signature / locked / duplicate dropped; list vs value
  shape; Markdown stripped; numbers and dates normalized.
- dates: ambiguous 3/4 -> question with both readings; unambiguous and text
  months pass; a clicked choice settles it; relative dates capped at medium;
  an unknown date is asked about.
- fact guard: invented phone / email -> question; case and spacing ignored;
  short numbers tolerated.
- ai_enabled False capped at medium; over_budget for chars and items.
- questions: cap, required first, kind order, ids, attempts.
- clarification loop: ask limit -> needs_user + "fill it in the form",
  skipped fields not re-asked unless mentioned, safety-net questions for
  missing required fields, stage asking / filling / ready.
"""

import os
from datetime import date
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-that-is-long-enough-for-auth-tests")

from app.schemas.ai_fill import (  # noqa: E402
    AiFillProposalOut,
    AiFillQuestionOut,
    AiFillTurn,
    FormStateItem,
)
from app.services.ai_fill_service import (  # noqa: E402
    AMBIGUOUS_DATE_REASON,
    UNKNOWN_DETAILS_REASON,
    build_field_catalog,
    build_user_content,
    check_date,
    date_mentions,
    fact_guard,
    mentioned_fields,
    normalize_date,
    postprocess,
)
from app.services.field_placement import FieldBudget  # noqa: E402

TODAY = date(2026, 11, 11)


def field(name, field_type="text", required=True, label=None, ai_enabled=True, **extra):
    return SimpleNamespace(
        field_name=name,
        field_label=label or name.replace("_", " ").title(),
        field_type=field_type,
        is_required=required,
        ai_enabled=ai_enabled,
        section=extra.get("section"),
        description=extra.get("description"),
        example_value=extra.get("example_value"),
        validation_rule=None,
    )


FIELDS = [
    field("student_name"),
    field("roll_number"),
    field("project_title"),
    field("abstract", "textarea"),
    field("technologies", "list", required=False),
    field("submission_date", "date"),
    field("team_size", "number", required=False),
    field("guide_name"),
    field("phone", required=False),
    field("remarks", "textarea", required=False, ai_enabled=False),
    field("signature", "signature"),
]
BUDGETS = {
    "student_name": FieldBudget("student_name", "inline", 80, "chars"),
    "abstract": FieldBudget("abstract", "line", 60, "chars"),
    "technologies": FieldBudget("technologies", "line", 2, "items", item_budget=10),
}
USER_TEXT = (
    "hi i am harsh kumar roll 22cs045, did projct on smart attendence using face recog with "
    "python opencv, guide is dr mehta, sumbit on 3/4, mail harsh@Example.com phone 98765 43210"
)


def proposal(name, value=None, items=None, confidence="high", **extra):
    return AiFillProposalOut(field_name=name, value=value, items=items, confidence=confidence, **extra)


def question(text, fields, choices=None, kind="missing"):
    return AiFillQuestionOut(text=text, field_names=fields, choices=choices or [], kind=kind)


def run(proposals=(), questions=(), *, form=(), user_texts=(USER_TEXT,), turn=1, reply="filled", **extra):
    """`reply` is the model's message; pass message=... for the user's new message."""
    return postprocess(
        AiFillTurn(message=reply, proposals=list(proposals), questions=list(questions)),
        fields=FIELDS,
        budgets=BUDGETS,
        form_state=[FormStateItem(field_name=n, value=v, origin=o) for n, v, o in form],
        user_texts=list(user_texts),
        turn_number=turn,
        today=TODAY,
        **extra,
    )


def by_name(result):
    return {p.field_name: p for p in result.proposals}


# ── proposals ────────────────────────────────────────────────────


def test_drops_unknown_signature_locked_and_duplicate_proposals():
    result = run(
        [
            proposal("student_name", "Harsh Kumar"),
            proposal("student_name", "Someone Else"),
            proposal("not_a_field", "x"),
            proposal("signature", "Harsh"),
            proposal("guide_name", "Dr. Mehta"),
            proposal("project_title", "   "),
        ],
        form=[("guide_name", "Dr. R. Mehta", "user")],
    )
    assert list(by_name(result)) == ["student_name"]
    assert by_name(result)["student_name"].value == "Harsh Kumar"
    assert result.counts["dropped"] == 5


def test_a_field_filled_by_ai_may_be_replaced_but_a_blank_user_field_is_not_locked():
    result = run(
        [proposal("student_name", "Harsh Kumar"), proposal("guide_name", "Dr. Mehta")],
        form=[("student_name", "harsh", "ai"), ("guide_name", "  ", "user")],
    )
    assert set(by_name(result)) == {"student_name", "guide_name"}


def test_value_shapes_and_normalization():
    result = run(
        [
            proposal("technologies", items=["- Python", "2. **OpenCV**", "  "]),
            proposal("project_title", "**Smart Attendance System**\nUsing Face Recognition"),
            proposal("abstract", "## Summary\nThis project marks attendance.\nIt uses face recognition."),
            proposal("team_size", "4"),
        ],
        user_texts=[USER_TEXT + " we are 4 members"],
    )
    values = by_name(result)
    assert values["technologies"].items == ["Python", "OpenCV"] and values["technologies"].value is None
    assert values["project_title"].value == "Smart Attendance System Using Face Recognition"
    assert values["abstract"].value == "Summary\nThis project marks attendance.\nIt uses face recognition."
    assert values["team_size"].value == "4"


def test_list_from_value_lines_and_value_from_items():
    result = run(
        [
            proposal("technologies", value="Python\nOpenCV"),
            proposal("project_title", items=["Smart", "Attendance"]),
        ]
    )
    assert by_name(result)["technologies"].items == ["Python", "OpenCV"]
    assert by_name(result)["project_title"].value == "Smart Attendance"


def test_unreadable_number_and_date_become_questions():
    result = run([proposal("team_size", "about five"), proposal("submission_date", "soon")])
    assert result.proposals == []
    asked = {name for q in result.questions for name in q.field_names}
    assert "submission_date" in asked


def test_ai_disabled_field_is_capped_at_medium_and_budgets_are_flagged():
    result = run(
        [
            proposal("remarks", "did projct on smart attendence"),
            proposal("abstract", "x" * 61),
            proposal("student_name", "Harsh Kumar"),
            proposal("technologies", items=["Python", "OpenCV", "Flask"]),
        ]
    )
    values = by_name(result)
    assert values["remarks"].confidence == "medium"
    assert values["abstract"].over_budget is True
    assert values["student_name"].over_budget is False
    assert values["technologies"].over_budget is True  # 3 items, budget 2
    result = run([proposal("technologies", items=["Python", "A very long item"])])
    assert by_name(result)["technologies"].over_budget is True  # one item over 10 chars


# ── dates ────────────────────────────────────────────────────────


def test_normalize_date_formats():
    assert normalize_date("2026-04-03") == "2026-04-03"
    assert normalize_date("03/04/2026") == "2026-04-03"  # day first
    assert normalize_date("3 April 2026") == "2026-04-03"
    assert normalize_date("April 3, 2026") == "2026-04-03"
    assert normalize_date("3rd Apr 2026") == "2026-04-03"
    assert normalize_date("31/02/2026") is None
    assert normalize_date("next week") is None


def test_date_mentions_and_check_date():
    assert {(m.day, m.month, m.ambiguous) for m in date_mentions("sumbit on 3/4")} == {(3, 4, True), (4, 3, True)}
    assert [(m.day, m.month, m.year, m.ambiguous) for m in date_mentions("on 13/04/26")] == [(13, 4, 2026, False)]
    assert check_date("2026-04-03", "sumbit on 3/4") == ("ambiguous", ["3 April 2026", "4 March 2026"])
    assert check_date("2026-04-13", "due 13/4") == ("ok", [])
    assert check_date("2026-04-03", "sumbit on 3/4\n3 April 2026") == ("ok", [])
    assert check_date("2026-04-03", "on 3rd april") == ("ok", [])
    assert check_date("2026-11-12", "submit tomorrow") == ("relative", [])
    assert check_date("2026-04-03", "no date here") == ("unknown", [])
    assert check_date("2027-04-03", "on 3 April 2026") == ("unknown", [])


def test_ambiguous_date_is_asked_with_both_readings():
    result = run([proposal("submission_date", "2026-04-03")])
    assert result.proposals == []
    asked = next(q for q in result.questions if q.field_names == ["submission_date"])
    assert asked.choices == ["3 April 2026", "4 March 2026"]
    assert asked.kind == "unclear"


def test_the_models_own_question_about_an_ambiguous_date_is_kept():
    result = run(
        [proposal("submission_date", "2026-04-03")],
        [question("Is the submission date 3 April or 4 March?", ["submission_date"], ["3 April", "4 March"], "unclear")],
    )
    asked = [q for q in result.questions if "submission_date" in q.field_names]
    assert len(asked) == 1 and asked[0].text.startswith("Is the submission date")


def test_clicked_choice_settles_the_date():
    result = run([proposal("submission_date", "2026-04-03")], user_texts=[USER_TEXT, "3 April 2026"], turn=2)
    assert by_name(result)["submission_date"].value == "2026-04-03"
    assert by_name(result)["submission_date"].confidence == "high"


def test_relative_date_is_medium_and_unknown_date_is_asked():
    result = run([proposal("submission_date", "2026-11-12")], user_texts=["i will submit tomorrow"])
    assert by_name(result)["submission_date"].confidence == "medium"
    result = run([proposal("submission_date", "2026-12-25")], user_texts=["no date given"])
    assert result.proposals == []
    assert any(q.field_names == ["submission_date"] and q.choices == [] for q in result.questions)


# ── fact guard ───────────────────────────────────────────────────


def test_fact_guard_helper():
    assert fact_guard(["22CS045"], USER_TEXT, today=TODAY) == "ok"
    assert fact_guard(["9876543210"], USER_TEXT, today=TODAY) == "ok"  # the user spaced it
    assert fact_guard(["98765 43210"], "my phone is 9876543210", today=TODAY) == "ok"
    assert fact_guard(["Harsh@example.COM"], USER_TEXT, today=TODAY) == "ok"
    assert fact_guard(["9123456780"], USER_TEXT, today=TODAY) == "unknown"
    assert fact_guard(["someone@else.com"], USER_TEXT, today=TODAY) == "unknown"
    assert fact_guard(["see https://evil.example/x"], USER_TEXT, today=TODAY) == "unknown"
    assert fact_guard(["Academic year 2026"], USER_TEXT, today=TODAY) == "ok"  # this year
    assert fact_guard(["In 1998 the lab opened"], USER_TEXT, today=TODAY) == "unknown"
    assert fact_guard(["It uses 2 cameras"], USER_TEXT, today=TODAY) == "ok"  # short numbers are tolerated
    assert fact_guard(["5"], USER_TEXT, today=TODAY, strict_numbers=True) == "soft"
    assert fact_guard(["12, 15"], "items 12 and 15", today=TODAY) == "ok"


def test_invented_details_are_never_applied():
    result = run(
        [
            proposal("phone", "9123456780"),
            proposal("roll_number", "22CS045"),
            proposal("guide_name", "Dr. Mehta (mehta@college.edu)"),
            proposal("team_size", "5"),
        ]
    )
    values = by_name(result)
    assert set(values) == {"roll_number", "team_size"}
    assert values["roll_number"].confidence == "high"
    assert values["team_size"].confidence == "medium"  # a short number the user did not type
    asked = {name for q in result.questions for name in q.field_names}
    assert "guide_name" in asked  # required: asked first
    assert result.counts["low"] == 2


def test_low_confidence_from_the_model_is_not_applied():
    result = run([proposal("guide_name", "Dr. Mehta", confidence="low")])
    assert result.proposals == []
    assert any(q.field_names == ["guide_name"] for q in result.questions)


# ── questions and the loop ───────────────────────────────────────


def filled_form(*missing):
    values = {
        "student_name": "Harsh Kumar",
        "roll_number": "22CS045",
        "project_title": "Smart Attendance",
        "abstract": "A project.",
        "submission_date": "2026-04-03",
        "guide_name": "Dr. Mehta",
    }
    return [(name, "" if name in missing else value, "empty" if name in missing else "ai") for name, value in values.items()]


def test_question_cap_order_ids_and_attempts():
    result = run(
        [],
        [
            question("Any remarks?", ["remarks"], kind="more_detail"),
            question("Phone number?", ["phone"]),
            question("Guide's full name?", ["guide_name"], kind="unclear"),
            question("Two titles were given. Which one?", ["project_title"], ["A", "B"], "conflict"),
            question("Roll number?", ["roll_number"]),
            question("About nothing", ["nope"]),
        ],
        form=filled_form("guide_name", "project_title", "roll_number"),
        turn=2,
        ask_counts={"guide_name": 1},
    )
    assert [q.id for q in result.questions] == ["t2-q1", "t2-q2", "t2-q3"]
    # required first, then conflict > missing > unclear
    assert [q.field_names[0] for q in result.questions] == ["project_title", "roll_number", "guide_name"]
    assert [q.attempt for q in result.questions] == [1, 1, 2]
    assert result.questions[0].choices == ["A", "B"]


def test_missing_required_fields_are_asked_even_when_the_model_forgets():
    result = run([proposal("student_name", "Harsh Kumar")], form=filled_form("student_name", "guide_name"))
    assert [q.field_names for q in result.questions] == [["guide_name"]]
    assert result.questions[0].text == "What should I put for 'Guide Name'?"
    assert result.missing_required == ["guide_name"]
    assert (result.stage, result.done) == ("filling", False)
    assert (result.required_total, result.required_filled) == (6, 5)


def test_ask_limit_moves_the_field_to_needs_user():
    result = run(
        [],
        [question("Guide's first name, please?", ["guide_name"], kind="unclear")],
        form=filled_form("guide_name"),
        turn=4,
        ask_counts={"guide_name": 3},
    )
    assert result.questions == []
    assert result.needs_user == ["guide_name"] and result.missing_required == ["guide_name"]
    assert "I couldn't get 'Guide Name' from the chat. Please fill it in the form." in result.message
    # Everything else is done: the chat is ready although the field is empty.
    assert (result.stage, result.done) == ("ready", True)


def test_re_asked_question_text_and_attempt():
    result = run([], form=filled_form("guide_name"), turn=2, ask_counts={"guide_name": 1})
    assert result.questions[0].text == "I still need 'Guide Name'. What should I put there?"
    assert result.questions[0].attempt == 2


def test_skipped_field_is_not_asked_again_unless_mentioned():
    quiet = run(
        [], [question("Guide's name?", ["guide_name"])], form=filled_form("guide_name"), turn=2, skipped={"guide_name"},
        message="the title is fine",
    )
    assert quiet.questions == [] and quiet.needs_user == ["guide_name"]
    assert "Please fill it in the form" not in quiet.message  # skipped by choice: no nagging

    mentioned = run(
        [], [question("Guide's name?", ["guide_name"])], form=filled_form("guide_name"), turn=2, skipped={"guide_name"},
        message="actually the guide name is with my friend",
    )
    assert [q.field_names for q in mentioned.questions] == [["guide_name"]]


def test_mentioned_fields_matches_labels_and_keys():
    assert mentioned_fields(FIELDS, "my Guide  Name is dr mehta, roll number later") == {"guide_name", "roll_number"}
    assert mentioned_fields(FIELDS, "") == set()


def test_stage_asking_for_a_vague_first_message():
    result = run([], user_texts=["make my project report"], reply="I need a few details.")
    assert result.stage == "asking" and not result.done
    assert len(result.questions) == 3  # the server asks for the first missing required fields
    assert all(q.attempt == 1 and q.kind == "missing" for q in result.questions)
    assert (result.required_total, result.required_filled) == (6, 0)


def test_stage_ready_when_everything_required_is_there():
    result = run(
        [proposal("guide_name", "Dr. Mehta")],
        form=filled_form("guide_name"),
        reply="",
    )
    assert (result.stage, result.done, result.missing_required, result.questions) == ("ready", True, [], [])
    assert result.message == "I have everything I need. Review the form, then save and generate."


def test_optional_question_keeps_the_stage_at_filling():
    result = run([], [question("Phone number?", ["phone"])], form=filled_form())
    assert result.stage == "filling" and [q.field_names for q in result.questions] == [["phone"]]


def test_questions_about_locked_fields_are_dropped():
    form = filled_form()
    form = [(n, v, "user" if n == "guide_name" else o) for n, v, o in form]
    result = run([], [question("Is the guide Dr. Mehta or Dr. Mehra?", ["guide_name"], kind="conflict")], form=form)
    assert result.questions == [] and result.stage == "ready"


# ── prompt building ──────────────────────────────────────────────


def test_field_catalog_marks_locked_blocked_and_skips_signature():
    state = {
        "student_name": FormStateItem(field_name="student_name", value="Harsh", origin="user"),
        "technologies": FormStateItem(field_name="technologies", value='["Python", "OpenCV"]', origin="ai"),
    }
    catalog = build_field_catalog(FIELDS, BUDGETS, state, {"guide_name": 3}, {"guide_name"}, {"phone"})
    lines = {line.split(" | ")[0][len("- key="):]: line for line in catalog.splitlines()}
    assert "signature" not in lines
    assert "status=LOCKED (written by the user)" in lines["student_name"] and "current=Harsh" in lines["student_name"]
    assert "status=filled by AI" in lines["technologies"] and "current=Python; OpenCV" in lines["technologies"]
    assert "budget=2 items, each <= 10 chars" in lines["technologies"]
    assert "ask=ask_limit_reached" in lines["guide_name"] and "asked=3 times" in lines["guide_name"]
    assert "ask=skipped" in lines["phone"]
    assert "status=empty" in lines["abstract"] and "budget=60 chars" in lines["abstract"]
    assert "ai_rewrite=no" in lines["remarks"]


def test_user_content_sections():
    content = build_user_content(
        catalog="- key=a",
        history_text="[Turn 1]\nhello",
        open_questions=[{"id": "t1-q1", "text": "Which date?"}, {"id": "t1-q2", "text": "Guide?"},
                        {"id": "t1-q3", "text": "Year?"}],
        answers={"t1-q1": "3 April 2026"},
        skipped_ids=["t1-q2"],
        message="",
        today=TODAY,
    )
    assert content.startswith("TODAY: 2026-11-11")
    assert "- Which date? -> the user chose: 3 April 2026" in content
    assert "- Guide? -> SKIPPED by the user" in content
    assert "- Year? -> see NEW MESSAGE" in content
    assert content.endswith("(no text: see the chosen answers above)")
