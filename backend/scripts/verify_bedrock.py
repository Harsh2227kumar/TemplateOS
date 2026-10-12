"""
Verify the AI (AWS Bedrock) configuration — no database involved.

Usage (from backend/):
    python scripts/verify_bedrock.py                  # config-only checks, no AWS calls
    python scripts/verify_bedrock.py --live           # ALSO one tiny real call PER MODEL
    python scripts/verify_bedrock.py --live --model nova-lite   # just one model

Models checked individually (each one the app actually uses):
  suggestions  BEDROCK_MODEL_SUGGESTIONS  Claude Sonnet — POST /templates/{id}/suggest-fields
  nova-micro   BEDROCK_MODEL_NOVA_MICRO   Amazon Nova Micro — improve-text "grammar"
  nova-lite    BEDROCK_MODEL_NOVA_LITE    Amazon Nova Lite — improve-text "tone"/"concise"/"formal"

What it checks (in order):
  1. Settings resolve (.env present, region, each model id)
  2. Python dependencies (anthropic / instructor / boto3)
  3. AWS auth (Bedrock long-term API key -> env vars -> shared profile -> instance role)
  4. --live only: one real call per model through the SAME service function
     the API uses (validates auth, IAM permission AND console model access —
     the only way to know for sure). A failing model does not stop the others.

Exit code 0 = everything it checked passed; 1 = something failed.
Failures print the same WHY text the API server logs on a 503.
"""

import argparse
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

PASS = "  [OK]  "
FAIL = "  [FAIL]"
SKIP = "  [SKIP]"

# key -> (env var, settings attribute, what it powers)
MODELS = {
    "suggestions": (
        "BEDROCK_MODEL_SUGGESTIONS",
        "bedrock_model_suggestions",
        "Claude — AI field suggestions",
    ),
    "nova-micro": (
        "BEDROCK_MODEL_NOVA_MICRO",
        "bedrock_model_nova_micro",
        "Nova Micro — improve-text: grammar",
    ),
    "nova-lite": (
        "BEDROCK_MODEL_NOVA_LITE",
        "bedrock_model_nova_lite",
        "Nova Lite — improve-text: tone / concise / formal",
    ),
}

problems = 0


def report(ok: bool, message: str) -> None:
    global problems
    print(f"{PASS if ok else FAIL} {message}")
    if not ok:
        problems += 1


def _probe_suggestions(ai_service) -> str:
    suggestions = ai_service.suggest_fields(
        "Invoice for services rendered to ACME Corp. Total due: $1500.",
        ["client_name"],
    )
    names = ", ".join(s.field_name for s in suggestions[:3]) or "none"
    return f"{len(suggestions)} proposal(s) for the probe document ({names})"


def _probe_improve(ai_service, action: str, text: str) -> str:
    improved = ai_service.improve_text(action, text)
    preview = improved if len(improved) <= 70 else improved[:67] + "..."
    return f'{action}: "{text}" -> "{preview}"'


def _live_check(key: str, settings, ai_service, AiUnavailableError) -> None:
    env_name, attr, purpose = MODELS[key]
    model_id = getattr(settings, attr)
    print(f"\n  -- {key}: {purpose}")
    print(f"     {env_name}={model_id!r}")
    if not model_id:
        report(False, f"{env_name} is not set in .env — skipping the live call")
        return

    if key == "suggestions":
        probe = lambda: _probe_suggestions(ai_service)  # noqa: E731
    elif key == "nova-micro":
        probe = lambda: _probe_improve(ai_service, "grammar", "we has went to the meeting yesterday")  # noqa: E731
    else:
        probe = lambda: _probe_improve(ai_service, "formal", "hey guys the budget thing is kinda done")  # noqa: E731

    started = time.perf_counter()
    try:
        result = probe()
    except AiUnavailableError as exc:
        elapsed = (time.perf_counter() - started) * 1000
        report(False, f"{key} failed after {elapsed:.0f} ms — WHY: {exc}")
        return
    elapsed = (time.perf_counter() - started) * 1000
    report(True, f"{key} replied in {elapsed:.0f} ms — {result}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Also make one tiny real Bedrock call per model (a few hundred tokens each)",
    )
    parser.add_argument(
        "--model",
        choices=sorted(MODELS),
        action="append",
        help="Only check this model (repeatable). Default: all models.",
    )
    args = parser.parse_args()
    selected = args.model or list(MODELS)

    print("=" * 66)
    print("TemplateOS — Bedrock AI configuration check")
    print("=" * 66)

    # ── 1. Settings ────────────────────────────────────────────────
    print("\n[1/4] Settings (app/core/config.py <- repository .env)")
    try:
        from app.core.config import settings
    except Exception as exc:
        report(False, f"Settings failed to load: {exc}")
        report(
            False,
            "Fix: copy .env.example to the repository root .env and set "
            "DATABASE_URL + JWT_SECRET_KEY first",
        )
        sys.exit(1)
    report(True, f"settings loaded (env={settings.app_env})")
    print(f"        AWS_REGION .................... {settings.aws_region!r}")
    print(f"        AI_MAX_OUTPUT_TOKENS .......... {settings.ai_max_output_tokens}")
    if not settings.aws_region:
        print(
            f"{SKIP} AI is intentionally OFF (AWS_REGION unset) — every AI "
            "endpoint will return 503 by design"
        )
    for key in selected:
        env_name, attr, purpose = MODELS[key]
        model_id = getattr(settings, attr)
        if model_id:
            report(True, f"{env_name:<27} = {model_id!r}  ({purpose})")
        elif settings.aws_region:
            report(False, f"{env_name:<27} is not set  ({purpose} will return 503)")
        else:
            print(f"{SKIP} {env_name:<27} not set (AI is off)")

    # ── 2. Dependencies ────────────────────────────────────────────
    print("\n[2/4] Python dependencies")
    try:
        import anthropic

        report(
            True,
            f"anthropic {getattr(anthropic, '__version__', '?')} "
            f"(AnthropicBedrock available: {hasattr(anthropic, 'AnthropicBedrock')})",
        )
    except ImportError as exc:
        report(False, f"anthropic missing ({exc}) — pip install -r requirements.txt")
    try:
        import instructor

        report(
            True,
            f"instructor {getattr(instructor, '__version__', '?')} "
            f"(from_bedrock available: {hasattr(instructor, 'from_bedrock')})",
        )
    except ImportError as exc:
        report(False, f"instructor missing ({exc}) — pip install -r requirements.txt")
    try:
        import boto3

        report(True, f"boto3 {boto3.__version__}")
    except ImportError as exc:
        report(False, f"boto3 missing ({exc}) — pip install 'anthropic[bedrock]'")

    # ── 3. Credential chain ────────────────────────────────────────
    print("\n[3/4] AWS auth")
    from app.services.ai_service import _auth_problem

    problem = _auth_problem()
    if problem is None:
        import os

        if os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
            via = "Bedrock long-term API key (AWS_BEARER_TOKEN_BEDROCK)"
        elif os.environ.get("AWS_ACCESS_KEY_ID"):
            via = "environment variables (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)"
        else:
            via = "shared AWS profile / instance role (boto3 default chain)"
        report(True, f"credentials resolve via {via}")
    else:
        report(False, problem)

    if not args.live:
        if problem is None:
            print(
                "\nConfig-only check done. Run with --live to verify IAM "
                "permission + console model access with a real call per model."
            )
        print(f"\nResult: {'FAIL' if problems else 'OK'} ({problems} problem(s))")
        sys.exit(1 if problems else 0)

    # ── 4. Live calls, one per model ───────────────────────────────
    print(f"\n[4/4] Live Bedrock calls (--live): {', '.join(selected)}")
    if problem is not None:
        report(False, "skipping live calls — fix AWS auth (step 3) first")
        print(f"\nResult: FAIL ({problems} problem(s))")
        sys.exit(1)

    from app.services import ai_service
    from app.services.ai_service import AiUnavailableError

    for key in selected:
        _live_check(key, settings, ai_service, AiUnavailableError)

    print(
        "\n        (the running API server logs the same WHY on every 503 — "
        "see the uvicorn console)"
    )
    print(f"\nResult: {'FAIL' if problems else 'OK'} ({problems} problem(s))")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
