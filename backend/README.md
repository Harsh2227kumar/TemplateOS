# Backend Foundation

## Run locally

Full per-OS setup (Windows, macOS, Ubuntu) and the one-shot setup scripts
in `scripts/` are in the [root README](../README.md#setup). Backend only:

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

Set a long, random `JWT_SECRET_KEY` in the repository root `.env` outside local
throwaway development.

### EkLink single sign-on

With `EKLINK_URL`, `EKLINK_CLIENT_ID`, `EKLINK_CLIENT_SECRET` and
`EKLINK_REDIRECT_URI` set, the login page shows "Sign in with EkLink", and
opening TemplateOS from the EkLink dashboard signs in automatically
(`app/services/eklink.py`). The redirect URI is the SPA page
`http://localhost:5173/auth/callback` and must match the callback registered
in EkLink. Users are matched by email; a first-time user is created with a
role mapped from the EkLink role (student→student, faculty/hod→faculty,
director→approver, admin→org_admin, staff/finance→normal_user) and joins
`EKLINK_ORGANIZATION` (and the department with the EkLink department's name)
when that is set. Existing users keep the role and membership set in
TemplateOS.


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

The protected profile schema exposes these User attributes: `id`, `email`,
`full_name` and `role` are always set; `department`, `organization`,
`job_title`, `phone`, `avatar_url`, `signature_path` and `preferences` may be
null. Demo preferences use the keys default_document_format (set to docx)
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

## AI (AWS Bedrock)

AI is optional. With `AWS_REGION` unset the AI endpoints return 503 and the
rest of the app works normally. Only the backend talks to Bedrock; never put
AWS credentials in the frontend.

- `POST /api/v1/templates/{id}/suggest-fields`: field suggestions while
  setting up a template (Claude via `BEDROCK_MODEL_SUGGESTIONS`).
- `POST /api/v1/ai/improve-text`: rewrites one AI-enabled field in a style
  (`grammar` with Nova Micro; `tone`, `concise`, `formal`, `expand` with Nova
  Lite). List fields send `original_items` and are rewritten item by item.
- AI fill assistant (V1.7 Phase 2.2), see below (Claude via
  `BEDROCK_MODEL_FILL`, else `BEDROCK_MODEL_SUGGESTIONS`).

Settings (repository-root `.env`, restart the backend after a change):

| Setting | Meaning |
|---|---|
| `AWS_REGION` | e.g. `ap-south-1`. Unset = AI off |
| `AWS_BEARER_TOKEN_BEDROCK` | Bedrock API key (preferred), or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` |
| `BEDROCK_MODEL_SUGGESTIONS` | Inference-profile id for field suggestions |
| `BEDROCK_MODEL_NOVA_MICRO`, `BEDROCK_MODEL_NOVA_LITE` | Inference-profile ids for the text styles, e.g. `apac.amazon.nova-micro-v1:0` |
| `AI_MAX_OUTPUT_TOKENS` | Reply length cap (default `1024`) |
| `BEDROCK_MODEL_FILL` | Optional model for the AI fill assistant (default: the suggestions model) |

Check the setup from `backend/` with `python scripts/verify_bedrock.py`
(`--live` also makes one tiny real call per model).

Troubleshooting:

- `AccessDeniedException ... Authentication failed: Please make sure your API
  Key is valid` (503 in the app): the Bedrock API key is wrong or expired.
  Short-term keys last at most 12 hours. Create a long-term key in the
  Bedrock console for the same region as `AWS_REGION`, paste it on one line
  without quotes, and restart the backend.
- `You don't have access to the model`: enable the model under Bedrock
  -> Model access in that region.

### AI fill assistant

A user fills a draft's form by chatting: the reply holds **proposals**
(never saved by the server; the browser puts them in the form and the user
saves through `PUT /documents/{id}/values` with `ai_action: "ai_fill"`) and
up to three questions.

- `GET /api/v1/documents/{id}/ai-fill`: the chat, its open questions and
  each field's length budget.
- `POST /api/v1/documents/{id}/ai-fill/messages`: one turn (`message`,
  `answers`, `skipped`, `form_state`). 503 when AI is off or fails (nothing
  is stored), 409 `turn_limit` after `AI_FILL_MAX_TURNS`.
- `DELETE /api/v1/documents/{id}/ai-fill`: clears the chat (values stay).
- `GET /api/v1/system/ai-config`: whether the UI may offer AI features.

The model's reply is checked before it reaches the user: fields the user
wrote, unknown fields and signatures are dropped; a number, email or date
the user never wrote becomes a question; an ambiguous date like `3/4` is
asked with both readings. A field is asked about at most
`AI_FILL_MAX_ASKS_PER_FIELD` times, then left to the user. The chat is
stored with the document (deleted with it) and never in `ai_generations`,
the audit log or the server logs.

| Setting | Default | Meaning |
|---|---|---|
| `AI_FILL_MAX_OUTPUT_TOKENS` | `4096` | Reply length cap per turn |
| `AI_FILL_MAX_MESSAGE_CHARS` | `8000` | Longest user message |
| `AI_FILL_MAX_HISTORY_CHARS` | `24000` | Earlier messages sent to the model |
| `AI_FILL_MAX_TURNS` | `30` | Turns per chat |
| `AI_FILL_MAX_QUESTIONS` | `3` | Questions per turn |
| `AI_FILL_MAX_ASKS_PER_FIELD` | `3` | Questions about one field per chat |

**Fit check:** `POST /documents/{id}/generate` returns `fit` (also
`GET /api/v1/documents/{id}/fit-report?version=n`): the PDF's page count
against the template rendered with example values (computed once per
template version, needs PDF conversion), and fields longer than their
place in the Word file allows. It only warns; it never blocks or cuts.

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
| `GOTENBERG_URL` | unset | e.g. `http://localhost:3005` (host port 3000 is EkLink). Unset: a local LibreOffice is used if found |
| `GOTENBERG_TIMEOUT_SECONDS` | `60` | Total conversion timeout (connect timeout 5 s) |
| `PDF_CONVERTER` | `auto` | `auto` / `gotenberg` / `libreoffice` / `none` (`none` = disabled) |
| `LIBREOFFICE_PATH`, `LIBREOFFICE_TIMEOUT_SECONDS` | unset, `120` | Local LibreOffice fallback |
| `GENERATED_VERSIONS_KEEP_FILES` | `10` | Every Generate is a new version; files of versions older than the newest N are deleted (their values stay viewable and restorable) |

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

## Word file editor (ONLYOFFICE Docs)

Optional. Users edit the real Word file in the browser:

- **Customize for me:** a private copy of a template (fields included).
  Typing a blank such as `Date of meeting: ________` or `{{ field_name }}`
  in the copy, then **Done editing**, leads to a "Field changes" page that
  turns them into fields through the normal clean / detect / fields steps.
- **Edit Word file** on a template (managers; a warning on shared
  originals): every save is a template revision, restorable from the
  template page. A file that no longer renders is kept but not used.
- **Edit Word file** on a generated document: the save is a new version
  marked "Edited manually" (DOCX and PDF); form values do not change.
  Generating again afterwards asks first.

It runs ONLYOFFICE Docs Community Edition (free, AGPL, unmodified, up to
20 people editing at once) as its own container:

```bash
docker compose up -d onlyoffice    # ~3 GB image, first start takes a minute or two
curl http://localhost:8082/healthcheck   # "true" when ready
```

Then, in the repository-root `.env` (the container reads the same secret):

| Setting | Default | Meaning |
|---|---|---|
| `ONLYOFFICE_ENABLED` | `false` | Shows the editor buttons |
| `ONLYOFFICE_PUBLIC_URL` | unset | Where the browser reaches the Document Server, e.g. `http://localhost:8082` |
| `ONLYOFFICE_INTERNAL_URL` | the public URL | Where the backend reaches it, if different |
| `ONLYOFFICE_JWT_SECRET` | unset | 32+ characters; must equal the container's `JWT_SECRET` |
| `BACKEND_URL_FOR_ONLYOFFICE` | `http://host.docker.internal:8000` | How the container reaches this backend |
| `EDITOR_SESSION_TTL_MINUTES` | `240` | How long an editing session (and its lock) lasts |
| `EDITOR_MAX_FILE_MB` | `20` | Largest edited file accepted back |

The container calls the backend back to save, so start uvicorn with
`--host 0.0.0.0` while editing. The compose service allows downloads from
private addresses (`host.docker.internal`); without that the Document Server
refuses to fetch files. One person edits a file at a time; others see
"Being edited by ... since ...".

## Download history and audit log

- Every successful DOCX/PDF download (latest or a specific version) is
  recorded; failed downloads are not. Users see theirs on the **Downloads**
  page (`GET /api/v1/me/downloads`) and per document
  (`GET /api/v1/documents/{id}/downloads`). Rows keep the document name and
  version after the document is deleted.
- Important actions write an append-only audit row: templates (upload,
  access, clean, fields, Word edits, ...), documents (create, save, generate,
  restore, download), the Word editor, AI, admin changes and sign-in. Rows
  hold ids, names and counts, never field values, file contents or
  passwords. If writing an audit row fails, the user's action still succeeds.
- `GET /api/v1/admin/audit-logs` (+ `/actions`, `/export.csv`): super admins
  see everything, organization admins their organization, department admins
  their department; everyone else gets 403. The admin page is
  **Admin > Audit log**.

| Setting | Default | Meaning |
|---|---|---|
| `AUDIT_RETENTION_DAYS` | `365` | Audit rows older than this are removed by the prune script |
| `DOWNLOAD_HISTORY_RETENTION_DAYS` | `730` | Same for download history |
| `TRUSTED_PROXY_IPS` | empty | Behind a reverse proxy: its IP(s), so `X-Forwarded-For` gives the client IP |

Pruning is manual: `python scripts/prune_audit_logs.py` prints what would be
removed; add `--yes` to delete.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Run from `backend/`. The tests use in-memory or temporary SQLite and mock
Bedrock and Gotenberg, so no real database, AWS account or Docker is needed.
Settings still load at import time, so `DATABASE_URL` and `JWT_SECRET_KEY`
must be set (your `.env` is enough); CI runs the same command with
`DATABASE_URL=sqlite://` on every pull request.

## Helper scripts

Run from `backend/` after `alembic upgrade head`:

| Script | Purpose |
|---|---|
| `scripts/seed_user.py` | Create one user with a chosen role |
| `scripts/seed_demo_users.py` | Seed the seven `SIT_*` demo users from `.env` |
| `scripts/seed_demo_template.py` | Demo template with every field type and validation rules |
| `scripts/seed_templates.py` | A few sample templates |
| `scripts/seed_preview_demo.py` | Template and draft covering every preview state |
| `scripts/test_db_connection.py` | Check that `DATABASE_URL` connects |
| `scripts/verify_template_fields.py` | Check stored template fields for bad types and order gaps |
| `scripts/verify_bedrock.py` | Check the AI settings (`--live` for real calls) |
| `scripts/verify_gotenberg.py` | Check Gotenberg (`--live` converts a test DOCX) |
| `scripts/prune_audit_logs.py` | Remove audit / download rows past their retention (dry run unless `--yes`) |
