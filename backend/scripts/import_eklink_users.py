"""
Pre-create EkLink's users in TemplateOS (so admins see the full roster and can
assign approvers before people sign in).

Every profile goes through the SAME rules as a real EkLink sign-in
(app.services.eklink.sync_user): matched by EkLink id, then login ID, then
email; existing users are updated, never duplicated; an admin role given in
TemplateOS is never lowered; deactivated TemplateOS users are skipped.
Nothing is ever deleted. Imported users have no password: they sign in with
EkLink.

Source: EkLink's Supabase REST API, using NEXT_PUBLIC_SUPABASE_URL and
SUPABASE_SECRET_KEY from EkLink's .env (read only).

Placement: EkLink's organization / institute / department codes when its
profiles carry them, otherwise --org-code / --institute-code /
--department-code (default SIU / SIT / CSE).

Usage (from TemplateOS/backend):
    python scripts/import_eklink_users.py --eklink-env ../../EkLink/.env          # dry run
    python scripts/import_eklink_users.py --eklink-env ../../EkLink/.env --apply  # write

Prints counts only, never names, emails or IDs.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
import app.models  # noqa: E402,F401  (register every model)
from app.models.user import User  # noqa: E402
from app.services import eklink, org_directory  # noqa: E402

# EkLink legacy role -> platform role, used when a profile has no platform_role.
PLATFORM_ROLE = {
    "student": "student",
    "faculty": "faculty",
    "hod": "faculty",
    "director": "faculty",
    "staff": "staff",
    "finance": "staff",
    "admin": "super_admin",
}


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def fetch_profiles(base: str, key: str) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        request = urllib.request.Request(
            f"{base}/rest/v1/profiles?select=*&order=login_id",
            headers={"apikey": key, "Range": f"{start}-{start + 999}"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            page = json.loads(response.read())
        rows.extend(page)
        if len(page) < 1000:
            return rows
        start += 1000


def fetch_codes(base: str, key: str) -> dict[str, dict[str, str]]:
    """id -> code maps for EkLink's directory tables (empty before its migration 0005)."""
    codes: dict[str, dict[str, str]] = {}
    for table in ("organizations", "institutes", "departments"):
        try:
            request = urllib.request.Request(
                f"{base}/rest/v1/{table}?select=id,code", headers={"apikey": key}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                codes[table] = {row["id"]: row["code"] for row in json.loads(response.read())}
        except Exception:
            codes[table] = {}
    return codes


def claims_for(profile: dict, codes: dict, defaults: argparse.Namespace) -> dict:
    role = str(profile.get("role") or "").lower()
    return {
        "sub": profile.get("id"),
        "login_id": profile.get("login_id"),
        "email": profile.get("college_email"),
        "name": profile.get("name"),
        "role": role,
        "platform_role": profile.get("platform_role") or PLATFORM_ROLE.get(role),
        "org_code": codes["organizations"].get(profile.get("organization_id")) or defaults.org_code,
        "institute_code": codes["institutes"].get(profile.get("institute_id")) or defaults.institute_code,
        "department_code": codes["departments"].get(profile.get("department_id"))
        or defaults.department_code,
        "batch": profile.get("batch"),
        "section": profile.get("section"),
        "semester": profile.get("semester"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--eklink-env", required=True, type=Path, help="Path to EkLink's .env")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    parser.add_argument("--org-code", default="SIU")
    parser.add_argument("--institute-code", default="SIT")
    parser.add_argument("--department-code", default="CSE")
    args = parser.parse_args()

    env = read_env(args.eklink_env)
    base, key = env["NEXT_PUBLIC_SUPABASE_URL"], env["SUPABASE_SECRET_KEY"]
    profiles = fetch_profiles(base, key)
    codes = fetch_codes(base, key)
    print(f"EkLink profiles: {len(profiles)}")

    outcome: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    with SessionLocal() as db:
        before = db.scalar(select(func.count(User.id))) or 0
        # One query for everyone already in TemplateOS (the database may be far away).
        existing = db.execute(select(User.id, User.eklink_sub, User.login_id, User.email)).all()
        by_sub = {row.eklink_sub: row.id for row in existing if row.eklink_sub}
        by_login = {row.login_id: row.id for row in existing if row.login_id}
        by_email = {row.email.lower(): row.id for row in existing if row.email}
        placements: dict[tuple, tuple] = {}
        new_users: list[User] = []

        for profile in profiles:
            if not profile.get("is_active", True):
                outcome["skipped: inactive in EkLink"] += 1
                continue
            claims = claims_for(profile, codes, args)
            email = str(claims["email"] or "").strip().lower()
            match = (
                by_sub.get(claims["sub"])
                or by_login.get(claims["login_id"])
                or by_email.get(email)
            )
            if match is not None:
                # Existing account: exactly the sign-in rules (no role lowering, no duplicates).
                try:
                    with db.begin_nested():
                        user = eklink.sync_user(db, claims)
                except eklink.EklinkError as exc:
                    outcome[f"skipped: {exc.detail}"] += 1
                    continue
                outcome["updated"] += 1
            else:
                role, member_type = eklink.map_role(claims)
                if role is None or not email:
                    outcome["skipped: role or email missing"] += 1
                    continue
                key = (claims["org_code"], claims["institute_code"], claims["department_code"])
                if key not in placements:
                    placements[key] = eklink.resolve_placement(db, claims) or (None, None, None)
                organization, institute, department = placements[key]
                user = User(
                    email=email[:255],
                    full_name=(claims["name"] or email)[:255],
                    role=role,
                    member_type=member_type,
                    hashed_password=None,
                    login_id=claims["login_id"],
                    eklink_sub=claims["sub"],
                    batch=claims["batch"],
                    section=claims["section"],
                    semester=eklink._semester(claims),
                    is_active=True,
                )
                org_directory.set_user_membership(user, organization, department, institute)
                new_users.append(user)
                by_email[email] = -1  # guard against duplicates inside EkLink's data
                outcome["created"] += 1
            roles[user.role] += 1
            if user.department_id is None:
                outcome["warning: not placed in a department"] += 1

        db.add_all(new_users)
        db.flush()
        after = db.scalar(select(func.count(User.id))) or 0
        if args.apply:
            db.commit()
        else:
            db.rollback()

    for name, count in sorted(outcome.items()):
        print(f"  {name}: {count}")
    print("  roles: " + ", ".join(f"{role}={count}" for role, count in sorted(roles.items())))
    print(f"TemplateOS users before: {before}, after: {after if args.apply else f'{after} (dry run, rolled back)'}")
    if not args.apply:
        print("Dry run only. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
