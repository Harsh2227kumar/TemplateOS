"""
EkLink single sign-on (authorization-code flow, see EkLink md/integration-guide.md).

1. GET  /auth/eklink/login     -> state cookie + redirect to {EKLINK_URL}/authorize
2. EkLink redirects the browser to EKLINK_REDIRECT_URI (the SPA's /auth/callback)
3. POST /auth/eklink/callback  -> state check, code exchange at {EKLINK_URL}/token
   (server side, with the client secret), ES256 JWT verified against EkLink's
   JWKS (iss, aud, exp), user matched and synced (see sync_user), normal
   TemplateOS session cookies set.

EkLink is the source of identity (who the person is, where they belong);
admin roles given inside TemplateOS are never lowered by a sign-in.
"""

from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import logging

from app.core.config import settings
from app.models.organization import Department, Institute, Organization
from app.models.user import ADMIN_ROLES, MEMBER_TYPES, USER_ROLES, User
from app.services import org_directory

logger = logging.getLogger(__name__)
ROLE_RANK_ORDER = USER_ROLES

STATE_COOKIE_NAME = "templateos_eklink_state"
STATE_MAX_AGE_SECONDS = 600
HTTP_TIMEOUT_SECONDS = 10

# EkLink legacy role -> TemplateOS role (used when the token carries no
# platform_role) and -> member type.
ROLE_MAP = {
    "student": "student",
    "faculty": "faculty",
    "hod": "faculty",
    "director": "faculty",
    "admin": "org_admin",
    "staff": "staff",
    "finance": "staff",
}
MEMBER_MAP = {
    "student": "student",
    "faculty": "faculty",
    "hod": "faculty",
    "director": "faculty",
    "staff": "staff",
    "finance": "staff",
}

_jwks_client: jwt.PyJWKClient | None = None


class EklinkError(Exception):
    """Sign-in failed; `detail` is safe to show the user."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def authorize_url(state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.eklink_client_id,
            "redirect_uri": settings.eklink_redirect_uri,
            "state": state,
        }
    )
    return f"{settings.eklink_url}/authorize?{query}"


def exchange_code(code: str) -> str:
    """Trade the one-time code for EkLink's access JWT (server to server)."""
    try:
        response = httpx.post(
            f"{settings.eklink_url}/token",
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.eklink_redirect_uri,
                "client_id": settings.eklink_client_id,
                "client_secret": settings.eklink_client_secret,
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise EklinkError(502, "EkLink is not reachable") from exc
    if response.status_code == 401:
        raise EklinkError(502, "EkLink rejected TemplateOS's client credentials")
    if response.status_code != 200:
        raise EklinkError(401, "The EkLink sign-in code is invalid or expired")
    token = response.json().get("access_token")
    if not isinstance(token, str) or not token:
        raise EklinkError(502, "EkLink returned no access token")
    return token


def _jwks() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(
            f"{settings.eklink_url}/.well-known/jwks.json",
            timeout=HTTP_TIMEOUT_SECONDS,
        )
    return _jwks_client


def verify_token(token: str) -> dict:
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=["ES256"],
            audience=settings.eklink_client_id,
            issuer=settings.eklink_issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWKClientError as exc:
        raise EklinkError(502, "Could not load EkLink's signing keys") from exc
    except jwt.InvalidTokenError as exc:
        raise EklinkError(401, "The EkLink token is invalid") from exc


def _text(claims: dict, key: str, limit: int) -> str | None:
    value = claims.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _semester(claims: dict) -> int | None:
    value = claims.get("semester")
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= 12 else None


def map_role(claims: dict) -> tuple[str | None, str | None]:
    """(TemplateOS role, member_type) for these EkLink claims; role None = no access."""
    platform_role = str(claims.get("platform_role") or "").strip().lower()
    legacy_role = str(claims.get("role") or "").strip().lower()
    role = platform_role if platform_role in USER_ROLES else ROLE_MAP.get(legacy_role)
    member_type = MEMBER_MAP.get(legacy_role)
    if role in MEMBER_TYPES:
        member_type = role
    return role, member_type


def resolve_placement(
    db: Session, claims: dict
) -> tuple[Organization | None, Institute | None, Department | None] | None:
    """
    Placement from EkLink's organization / institute / department codes,
    matched as deep as they go. None when EkLink sent no organization code
    (older tokens): the caller then falls back to EKLINK_ORGANIZATION.
    """
    org_code = _text(claims, "org_code", 32)
    if not org_code:
        return None
    organization = org_directory.find_by_code(db, Organization, org_code)
    if organization is None:
        logger.warning("EkLink organization code %r is unknown in TemplateOS", org_code)
        return None
    institute = org_directory.find_by_code(
        db, Institute, _text(claims, "institute_code", 32), organization_id=organization.id
    )
    department = None
    if institute is not None:
        department = org_directory.find_by_code(
            db, Department, _text(claims, "department_code", 32), institute_id=institute.id
        )
    return organization, institute, department


def _fallback_placement(
    db: Session, claims: dict
) -> tuple[Organization | None, Institute | None, Department | None] | None:
    """Pre-directory behaviour: EKLINK_ORGANIZATION by name + department by name."""
    organization = org_directory.find_organization_by_name(db, settings.eklink_organization)
    if organization is None:
        return None
    department = org_directory.find_department_by_name(
        db, organization.id, claims.get("department")
    )
    return organization, (department.institute if department else None), department


def _find_existing(db: Session, sub: str | None, login_id: str | None, email: str) -> User | None:
    if sub:
        user = db.scalar(select(User).where(User.eklink_sub == sub))
        if user is not None:
            return user
    if login_id:
        user = db.scalar(select(User).where(User.login_id == login_id))
        if user is not None:
            return user
    return db.scalar(select(User).where(func.lower(User.email) == email))


def apply_role(user: User, role: str | None) -> None:
    """EkLink role rule for an existing user: an EkLink admin role is applied
    when it is higher, a member role only replaces a member (or legacy) role;
    an admin role given inside TemplateOS is never lowered."""
    if role in ADMIN_ROLES:
        if ROLE_RANK_ORDER.index(role) < ROLE_RANK_ORDER.index(
            user.role if user.role in ROLE_RANK_ORDER else "student"
        ):
            user.role = role
    elif role in MEMBER_TYPES and user.role not in ADMIN_ROLES:
        user.role = role


def apply_identity(
    db: Session,
    user: User,
    claims: dict,
    *,
    email: str,
    member_type: str | None,
    email_taken=None,
    login_id_taken=None,
) -> None:
    """
    Copy name, email, eklink_sub, login_id, member_type, batch, section and
    semester from EkLink claims (or a sync event) onto `user`. An email or
    login_id that another user already holds is left alone. The optional
    `*_taken(value, user_id)` callbacks replace the database lookups (the
    sync service answers them from its in-memory index).
    """
    if email_taken is None:
        def email_taken(value: str, user_id: int | None) -> bool:
            return db.scalar(
                select(User.id).where(func.lower(User.email) == value, User.id != user_id)
            ) is not None
    if login_id_taken is None:
        def login_id_taken(value: str, user_id: int | None) -> bool:
            return db.scalar(
                select(User.id).where(User.login_id == value, User.id != user_id)
            ) is not None

    sub = _text(claims, "sub", 64)
    login_id = _text(claims, "login_id", 128)
    name = _text(claims, "name", 255)
    if name:
        user.full_name = name
    if email != (user.email or "").lower() and not email_taken(email, user.id):
        user.email = email
    if sub and not user.eklink_sub:
        user.eklink_sub = sub
    if login_id and user.login_id != login_id and not login_id_taken(login_id, user.id):
        user.login_id = login_id
    if member_type:
        user.member_type = member_type
    for key, limit in (("batch", 20), ("section", 10)):
        value = _text(claims, key, limit)
        if value is not None:
            setattr(user, key, value)
    semester = _semester(claims)
    if semester is not None:
        user.semester = semester


def sync_user(db: Session, claims: dict) -> User:
    """
    Find (or create) the TemplateOS user for verified EkLink claims and bring
    their identity up to date. Does not commit.

    - Match: eklink_sub, then login_id, then email (an email match links the
      account to EkLink by storing login_id / eklink_sub).
    - Every sign-in refreshes name, email, login_id, member_type, batch,
      section, semester and (when EkLink sends codes TemplateOS knows) the
      organization / institute / department.
    - Role: a first-time user gets EkLink's platform role. For an existing
      user an EkLink admin role is applied, a member role only replaces a
      member (or legacy) role: an admin role given inside TemplateOS is never
      lowered by a sign-in.
    - Deactivated users are refused.
    """
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise EklinkError(403, "Your EkLink account has no email address")
    email = email.strip().lower()[:255]
    sub = _text(claims, "sub", 64)
    login_id = _text(claims, "login_id", 128)

    role, member_type = map_role(claims)
    user = _find_existing(db, sub, login_id, email)

    if user is not None:
        if not user.is_active:
            raise EklinkError(403, "Your TemplateOS account has been deactivated")
        if user.eklink_sub and sub and user.eklink_sub != sub:
            raise EklinkError(
                409, "This TemplateOS account is linked to a different EkLink account"
            )
    elif role is None:
        raise EklinkError(403, "Your EkLink role has no access to TemplateOS")

    if user is None:
        user = User(email=email, full_name=email, role=role, hashed_password=None)
        db.add(user)
    else:
        apply_role(user, role)
    apply_identity(db, user, claims, email=email, member_type=member_type)

    placement = resolve_placement(db, claims)
    if placement is None and user.organization_id is None:
        placement = _fallback_placement(db, claims)
    if placement is not None:
        organization, institute, department = placement
        org_directory.set_user_membership(user, organization, department, institute)

    db.flush()
    return user


# Kept for callers written before the sync existed.
get_or_create_user = sync_user
