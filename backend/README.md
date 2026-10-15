# Backend Foundation

## Run locally

1. Copy `.env.example` to `.env` in the repository root.
2. Set a valid `DATABASE_URL` for Neon PostgreSQL.
3. Use `backend/alembic.ini` as provided, or recreate it from `backend/alembic.ini.example`.
4. Alembic reads the database URL from the repository root `.env` through `backend/alembic/env.py`.
5. Install backend dependencies from `backend/requirements.txt`.
6. Run the API:

```bash
uvicorn app.main:app --reload
```

Run the command from the `backend/` directory.

## Authentication setup

Apply migrations before starting the API:

```bash
alembic upgrade head
```

Public signups always receive the `normal_user` role. To create a local test or
administrator account, run this from `backend/` after migrating:

```bash
python scripts/seed_user.py --email admin@example.com --password "change-this-password" --full-name "TemplateOS Admin" --role super_admin
```


Install development dependencies and run the isolated auth tests with:

```bash
pip install -r requirements-dev.txt
pytest -q
```
Set a long, random `JWT_SECRET_KEY` in the repository root `.env` outside local
throwaway development.


## Development/demo profiles

The repository root `.env.example` declares seven temporary development users,
one for each supported role. Copy those `SIT_*_EMAIL` and `SIT_*_PASSWORD`
variables into your local `.env`, apply migrations, and seed their profile data
from the `backend/` directory:

```bash
python scripts/seed_demo_users.py
```

The command is explicit (it is never run during application startup), reads
credentials at runtime, hashes passwords with the normal authentication helper,
and can be re-run without creating duplicate users. These accounts are for local
development only and must not be seeded in production.


### Persisted profile contract

Member 2 can expose these User attributes directly through the protected profile
schema: id, email, full_name, and role remain required; department,
organization, job_title, phone, avatar_url, signature_path, and preferences are
nullable. Demo preferences use the keys default_document_format (set to docx)
and email_notifications (set to false).

`GET /auth/me` also returns `organization_id` / `department_id`; `organization`
and `department` are the names of the linked rows. `PATCH /auth/me` accepts
`full_name`, `phone` and `job_title` only (anything else is a 422).

### Organizations, departments and user management

Organizations and departments are rows (`organizations`, `departments`,
migration `c7a1d3e5f9b2`). Users and template audiences point at them by id
(`users.organization_id/department_id`,
`templates.scope_organization_id/scope_department_id`), and every access rule
in `app/services/template_access.py` compares ids.

- Backfill: the migration builds the tables from the old free-text values
  (trimmed, whitespace collapsed, case-insensitive; the most common spelling
  names the row). A department string with no organization stays unlinked
  (`department_id` NULL) and must be assigned by an admin.
- Legacy columns: `users.organization/department` and
  `templates.scope_organization/scope_department` are kept as copies of the
  linked names (written with the ids, rewritten on rename) so a rollback loses
  nothing. Nothing reads them for access decisions.
- Deleting an organization or department that any user or template still
  uses returns 409; an unused organization is deleted with its unused
  departments.
- `/api/v1/admin/users` (super_admin, org_admin, department_admin) lists and
  edits role / organization / department; the rules live in
  `app/services/user_admin.py`.
- `/api/v1/admin/organizations` and `/api/v1/admin/departments` manage the
  directory (writes: super_admin; departments also org_admin in their own
  organization).

## PDF conversion (Gotenberg)

Generating a document (`POST /api/v1/documents/{id}/generate`) renders the
DOCX and then converts it to PDF inside the same request. A PDF failure never
fails generation: the DOCX is delivered and the document's `generated` info
says `pdf_status: "failed"` with a readable `pdf_error`; the user can then
click **Retry PDF** (`POST /api/v1/documents/{id}/generate-pdf`).

Start Gotenberg (Docker) from the repository root:

```bash
docker compose up -d gotenberg              # repo-root docker-compose.yml, port 3000
python backend/scripts/verify_gotenberg.py --live
docker compose logs -f gotenberg
```

If a Gotenberg container is already running on port 3000 (for example one
started with `docker run -d -p 3000:3000 gotenberg/gotenberg:8`), reuse it:
do not start the compose service as well, the ports would clash.

Settings (repository-root `.env`, restart the backend after a change):

| Setting | Default | Meaning |
|---|---|---|
| `PDF_CONVERSION_ENABLED` | `true` | Kill switch. `false` skips conversion and records "PDF conversion is disabled on this server" |
| `GOTENBERG_URL` | unset | e.g. `http://localhost:3000`. Unset: a local LibreOffice is used if found |
| `GOTENBERG_TIMEOUT_SECONDS` | `60` | Total conversion timeout (connect timeout 5 s) |
| `PDF_CONVERTER` | `auto` | `auto` / `gotenberg` / `libreoffice` / `none` (`none` = disabled) |
| `LIBREOFFICE_PATH`, `LIBREOFFICE_TIMEOUT_SECONDS` | unset, `120` | Local LibreOffice fallback |

Checks:

- `python scripts/verify_gotenberg.py` (from `backend/`): `GET /health`;
  `--live` also converts a tiny DOCX and prints the PDF size and latency.
  The URL comes from `--url`, `GOTENBERG_URL` in the environment, the
  repo `.env` (only that key is read), then `http://localhost:3000`.
  Exit code 0 = OK, 1 = failed.
- `GET /api/v1/system/pdf-check`: which converter the running backend uses
  and whether it answers.

PDF state on `generated` (detail, list and generate responses): `pdf_status`
(`pending` | `converted` | `failed`), `pdf_error`, `pdf_filename`,
`pdf_converted_at`, `pdf_attempts`, `has_pdf`, `pdf_url`. Download the PDF
with `GET /api/v1/documents/{id}/download/pdf` (or `download?format=pdf`):
404 not generated, 409 no PDF, 410 the file is missing on disk.

Troubleshooting:

- Port 3000 busy: change the left side of the compose port mapping
  (`"3001:3000"`) and set `GOTENBERG_URL=http://localhost:3001`.
- The first conversion after the container starts is slower (LibreOffice
  warm-up).
- Fonts that are not installed in the container fall back to similar fonts
  (known V1 limitation).
- Tests never call a real Gotenberg (it is mocked with `httpx.MockTransport`).
  The one live test runs only with `GOTENBERG_LIVE_URL=http://localhost:3000`.
