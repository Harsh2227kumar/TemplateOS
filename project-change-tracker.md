# Project Change Tracker

## Purpose

This file is the shared source of truth for tracking project work before every GitHub push.

It must be updated by any team member or AI assistant whenever changes are made in the project.

This tracker records:

- tasks completed
- code changes
- features added
- features updated
- features removed
- bug fixes
- documentation changes
- setup or configuration changes
- anything important that changes project behavior, structure, or workflow

---

## Instructions For AI And Team Members

Read this section before updating the file.

### What this file is

This is a cumulative project history log for the whole team.

It is not a personal worklog.
It is not only for one branch or one member.
It is a shared project-level tracker that should help any teammate or AI quickly understand:

- what has already been done
- what changed since the last push
- who made the change
- why the change matters

### When to update this file

Update this file:

- before every GitHub push
- after completing any meaningful task
- when adding, changing, or removing a feature
- when changing backend, frontend, database, docs, config, or project structure
- when fixing bugs
- when renaming, moving, or deleting important files/modules

### How to update this file

1. Do not rewrite old entries unless they are incorrect.
2. Do not duplicate previously logged changes.
3. Add new updates only for work done after the latest recorded push checkpoint.
4. Keep entries short, factual, and easy to scan.
5. Mention affected areas such as `frontend`, `backend`, `database`, `docs`, `config`, or `project-wide`.
6. Mention files or modules when useful.
7. If a change removes something, explicitly mark it as removed.
8. If there was no meaningful change in one category, leave it blank or write `None`.

### Rule to prevent duplicate entries

For the first setup of this file:

- the baseline must cover project work from project start until the date this tracker was created

For every future update:

- only add changes that happened after the most recent push checkpoint already written in this file
- do not re-add older work

### Entry format rules

Each update should include:

- date
- member name
- branch name if known
- summary
- completed tasks
- code changes
- features added/updated/removed
- issues fixed
- notes for next push if needed

---

## Recommended Update Workflow

Before pushing code:

1. Review your current changes.
2. Open this file.
3. Add one new checkpoint entry under `Push Checkpoints`.
4. Update only the new work since the previous checkpoint.
5. Keep the baseline section unchanged unless correcting historical mistakes.

---

## Project Baseline

This section captures the known project state from the beginning of the repository up to the creation of this tracker.

### Baseline Date

- Created on: 2026-07-19
- Baseline source: repository files and current git history
- Git history available at creation time: `1 commit`

### Baseline Summary

- Project name set as `TemplateOS`
- Planning and product documentation created under `MD/`
- Monorepo-style root workspace created with a frontend workspace
- Frontend foundation created with React, Vite, TypeScript, Tailwind CSS, and shadcn/ui
- Backend foundation created with FastAPI, SQLAlchemy, and Alembic structure
- Neon PostgreSQL environment setup prepared through `.env` and backend config files
- Initial frontend pages and dashboard shell created
- Initial backend API health and system endpoints created
- Initial database user model and migration scaffold added

### Baseline Completed Work

- Defined product direction for AI-powered DOCX template automation
- Added product planning docs such as features, flows, MVP scope, versions, and version planning
- Added root `package.json` with frontend workspace scripts
- Added frontend app shell with routes for dashboard, login, signup, and profile
- Added dashboard layout and placeholder dashboard cards
- Added reusable UI components and utility helpers in frontend
- Added backend app factory, CORS setup, API router, and health endpoint
- Added system endpoints including ping and database connection check
- Added backend database session/base/config structure
- Added initial user model
- Added Alembic environment and initial users table migration example/history
- Added sample env files and backend database connection test script
- Added contribution and setup documentation

### Baseline Current Feature State

#### Added

- frontend authentication-related pages: `login`, `signup`
- frontend dashboard shell
- frontend profile page route
- backend health endpoint
- backend system ping endpoint
- backend database connectivity check endpoint
- initial user database model
- project planning documentation set

#### In Progress / Placeholder

- dashboard content is currently placeholder/starter content
- template workflows are planned but not yet wired
- authentication flow is planned in docs but not fully implemented
- AI document generation flow is planned in docs but not yet implemented

#### Removed

- None recorded in available history

### Baseline Affected Areas

- `frontend`
- `backend`
- `database`
- `docs`
- `config`
- `project-wide`

---

## Push Checkpoints

Add all future updates below this section.

---

### Checkpoint 0001

- Date: 2026-07-19
- Member: Initial baseline setup by AI
- Branch: `chore/project-setup`
- Push status: pre-existing repository baseline captured
- Range covered: project start -> 2026-07-19

#### Summary

- Created the shared project change tracker and documented the repository baseline so future entries only need to capture new work after this checkpoint.

#### Completed Tasks

- Created a shared markdown tracker for all 3 team members
- Added AI instructions for maintaining the tracker
- Added duplicate-prevention guidance for future updates
- Logged the initial repository baseline from project start till now

#### Code Changes

- Added `MD/project-change-tracker.md`

#### Features Added / Updated / Removed

- Added shared change-tracking documentation for the team workflow

#### Issues Fixed

- None

#### Notes For Next Push

- Next entries should only include changes made after this checkpoint.

---

### Checkpoint 0002

- Date: 2026-07-19
- Member: Harsh
- Branch: `chore/project-setup`
- Push status: before push
- Range covered: after Checkpoint 0001 -> 2026-07-19

#### Summary

- Implemented the first working authentication layer across backend and frontend, including signup, login, current-user fetching, protected routing, supporting config, dependency, and test updates.

#### Completed Tasks

- Added backend auth endpoints for signup, login, and current-user profile access
- Added password hashing and JWT access-token utilities
- Added API dependency helpers for authenticated user and database session access
- Added auth-related request and response schemas
- Updated the user model and database migration flow to support stored passwords
- Added frontend auth context for token persistence, session restore, and logout
- Added protected-route and public-only-route guards
- Connected login and signup pages to the backend API
- Updated app routing so dashboard and profile routes require authentication
- Added backend auth tests and auth-related setup support

#### Code Changes

- `backend/app/api/v1/endpoints/auth.py` for signup, login, and `/me`
- `backend/app/api/deps.py` for auth and session dependencies
- `backend/app/core/security.py` for password hashing and JWT handling
- `backend/app/schemas/` for auth and user schemas
- `backend/app/models/user.py` and `backend/alembic/versions/20260719_02_add_user_password.py` for password persistence
- `backend/app/api/v1/api.py`, `backend/app/core/config.py`, `backend/app/db/session.py`, `backend/alembic/env.py`, `.env.example`, `backend/requirements.txt`, and `backend/requirements-dev.txt` for auth/config/dependency wiring
- `frontend/src/context/auth-context.tsx` for auth state management
- `frontend/src/components/protected-route.tsx` for route protection
- `frontend/src/lib/api.ts` for frontend auth API calls
- `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/src/pages/login-page.tsx`, `frontend/src/pages/signup-page.tsx`, `frontend/src/pages/profile-page.tsx`, and `frontend/src/layouts/dashboard-layout.tsx` for auth-connected UI flow
- `backend/tests/test_auth.py` and `backend/scripts/seed_user.py` for testing and setup support

#### Features Added / Updated / Removed

- Added: user signup flow
- Added: user login flow
- Added: JWT-based authenticated session flow
- Added: protected frontend routes for private pages
- Added: current-user profile fetch flow
- Updated: login, signup, profile, and dashboard shell behavior to respect auth state
- Updated: backend configuration and environment examples for auth support
- Removed: None

#### Issues Fixed

- Added duplicate-email protection during signup
- Added invalid-credential handling for login
- Added unauthorized-access handling for protected frontend pages and invalid tokens

#### Notes For Next Push

- Review whether generated `__pycache__` files should stay untracked or be ignored if they appear in local working folders.
- Future tracker entries should log only changes after this authentication checkpoint.

---


### Checkpoint 0003

- Date: 2026-07-20
- Member: Yash Khadgi
- Branch: `dev`
- Push status: before push
- Range covered: after Checkpoint 0002 -> 2026-07-20

#### Summary

- Extended the protected current-user profile API response for V1.1 Phase 3 and added tests for the safe profile contract.

#### Completed Tasks

- Added a dedicated profile response schema with nullable Phase 3 profile fields
- Updated `GET /api/v1/auth/me` to return the richer profile contract
- Added backend tests for safe profile fields, missing optional values, invalid tokens, expired tokens, and nonexistent token users

#### Code Changes

- `backend/app/schemas/user.py` for `UserProfileRead` and profile preferences schema
- `backend/app/api/v1/endpoints/auth.py` for the `/auth/me` response model
- `backend/tests/test_auth.py` for profile API contract and authorization tests

#### Features Added / Updated / Removed

- Added: explicit authenticated profile API contract for dashboard/profile usage
- Updated: `/api/v1/auth/me` response shape
- Removed: None

#### Issues Fixed

- Added coverage to ensure profile responses do not expose `hashed_password`
- Added coverage for tokens whose user no longer exists

#### Notes For Next Push

- Member 3 still needs to persist Phase 3 profile fields through the user model and migration.
- Full `pytest` currently collects `backend/scripts/test_db_connection.py` and requires `DATABASE_URL` plus `JWT_SECRET_KEY`; use `pytest tests` for the backend test suite unless that script is excluded or configured.

---

### Checkpoint 0004

- Date: 2026-07-21
- Member: Yash Khadgi
- Branch: `dev`
- Push status: before push
- Range covered: after Checkpoint 0003 -> 2026-07-21

#### Summary

- Implemented the V1.2 Phase 1 local storage service foundation and an authenticated original-template upload API.

#### Completed Tasks

- Added local storage folder mapping for original templates, processed templates, generated DOCX/PDF, signatures, and temp files
- Added safe save/read/delete/exists helpers with path traversal protection
- Added unique sanitized filename generation while preserving file extensions
- Added authenticated DOCX upload endpoint for saving original templates into local storage
- Added backend tests for storage service behavior and upload API validation

#### Code Changes

- `backend/app/services/storage_service.py` for local storage helpers and path safety
- `backend/app/api/v1/endpoints/storage.py` for the storage upload API
- `backend/app/api/v1/api.py` for storage router registration
- `backend/app/schemas/storage.py` for stored-file response schema
- `backend/tests/test_storage_service.py` and `backend/tests/test_storage_api.py` for storage coverage
- `backend/requirements.txt` for `python-multipart` upload support
- `.gitignore` for local SQLite database files used during manual backend checks

#### Features Added / Updated / Removed

- Added: local storage service abstraction for V1 file storage
- Added: `POST /api/v1/storage/templates/original` authenticated DOCX upload endpoint
- Updated: backend requirements for multipart upload handling
- Removed: None

#### Issues Fixed

- Added protections against absolute paths and `../` traversal in storage helpers
- Added validation for non-DOCX and empty uploads

#### Notes For Next Push

- Full template metadata persistence still belongs to the upcoming template table/API work.
- Local `backend/storage/` remains ignored by git, as planned for V1 local file storage.

---

### Checkpoint 0005

- Date: 2026-07-20
- Member: Member 3
- Branch: `feature/backend-user-profile-data`
- Push status: prepared for push
- Range covered: after Checkpoint 0004 -> 2026-07-20

#### Summary

- Added Phase 3 user profile persistence, a reversible migration, environment-driven demo profiles, and database-focused verification.

#### Completed Tasks

- Extended users with nullable department, organization, job title, phone, avatar path/URL, signature path, and JSON preferences fields
- Centralized and validated the documented seven-role vocabulary while preserving normal_user as the default
- Added an explicit idempotent seed command for all seven temporary accounts already declared in .env.example
- Verified seeded credentials through the existing login flow
- Added persistence, nullability, uniqueness, role, seed, password-hash, and migration tests
- Documented the seed command and persistence contract for Members 1 and 2

#### Code Changes

- backend/app/models/user.py for profile columns and shared role vocabulary
- backend/alembic/versions/20260720_03_add_user_profile_fields.py for the forward migration and downgrade
- backend/app/db/demo_seed.py and backend/scripts/seed_demo_users.py for demo profile seeding
- backend/scripts/seed_user.py for reuse of the shared role vocabulary
- backend/tests/test_user_profile_data.py for database and migration coverage
- backend/README.md for seed usage and API-contract handoff

#### Features Added / Updated / Removed

- Added: nullable Phase 3 profile persistence and JSON preferences
- Added: explicit environment-gated demo profile seed flow
- Updated: role validation and single-user seed role choices
- Removed: None

#### Issues Fixed

- Prevented duplicate demo users on repeated seed runs
- Prevented plaintext demo passwords from being stored
- Kept all new columns nullable so existing users remain migration-safe

#### Notes For Next Push

- Member 2 should extend the existing UserRead schema and GET /api/v1/auth/me response with the documented nullable profile fields.
- Member 1 can consume that single response contract; no duplicate profile endpoint is required.
- Backend verification result: 9 tests passed, including Alembic upgrade and downgrade on a temporary database.

---


### Checkpoint 0006

- Date: 2026-07-20
- Member: Member 3
- Branch: `feature/backend-user-profile-data`
- Push status: prepared for push
- Range covered: after Checkpoint 0005 -> 2026-07-20

#### Summary

- Renamed the demo credential namespace to SIT_* and added contract checks to prevent seed/config drift.

#### Completed Tasks

- Renamed all seven demo seed environment prefixes to SIT_*
- Renamed the matching email and password variables in .env.example
- Updated backend seed documentation
- Added tests that require SIT_ prefixes and exact agreement between seed definitions and .env.example
- Confirmed no legacy demo credential prefixes remain in repository source or configuration

#### Code Changes

- .env.example for SIT credential variable names
- backend/app/db/demo_seed.py for SIT seed definitions
- backend/README.md for SIT setup documentation
- backend/tests/test_user_profile_data.py for namespace and environment-contract regression coverage

#### Features Added / Updated / Removed

- Updated: demo credential environment namespace
- Added: automated seed/environment name alignment verification
- Removed: legacy demo credential names

#### Issues Fixed

- Prevented demo seeding failures caused by environment-variable naming mismatches

#### Notes For Next Push

- Local .env contained no legacy demo credential keys and required no migration.
- Backend verification result: 10 tests passed.

---


### Checkpoint 0007

- Date: 2026-07-20
- Member: Member 3
- Branch: `feature/backend-user-profile-data`
- Push status: prepared for push
- Range covered: after Checkpoint 0006 -> 2026-07-20

#### Summary

- Resolved SQLAlchemy/Alembic index drift and cleaned database test formatting.

#### Completed Tasks

- Removed the redundant index declaration from the users primary key
- Normalized spacing between profile-data test functions
- Verified the complete backend suite
- Verified the live PostgreSQL schema matches SQLAlchemy metadata

#### Code Changes

- backend/app/models/user.py
- backend/tests/test_user_profile_data.py

#### Issues Fixed

- Alembic check no longer proposes an unnecessary ix_users_id index

#### Notes For Next Push

- Backend verification result: 10 tests passed.
- Alembic verification result: no new upgrade operations detected.

---

### Checkpoint 0008

- Date: 2026-08-03
- Member: Member 1 (AI)
- Branch: `feature/frontend-dashboard`
- Push status: before push
- Range covered: after Checkpoint 0007 -> 2026-08-03

#### Summary

- Implemented V1.1 Phase 3 frontend dashboard shell, including responsive layout, sidebar, navbar, empty states, and an enriched read-only profile page consuming the backend profile contract.

#### Completed Tasks

- Extended frontend `User` TypeScript interface with nullable Phase 3 profile fields and `UserPreferences`.
- Created reusable formatting utilities for roles and avatar initials.
- Created reusable `AvatarFallback` and `EmptyState` UI components.
- Extracted and built `SidebarNav` with active states and "Coming soon" placeholders.
- Reworked `DashboardLayout` for a responsive desktop-sidebar and mobile-drawer layout.
- Replaced dashboard placeholders with a personalized welcome hero and proper empty states for documents/templates.
- Rebuilt the profile page to render all authenticated Phase 3 profile fields gracefully with null-fallbacks.
- Verified zero TypeScript/build errors via `npm run build`.

#### Code Changes

- `frontend/src/lib/api.ts` for expanded `User` and `UserPreferences` interfaces.
- `frontend/src/lib/format.ts` for formatting functions.
- `frontend/src/components/ui/avatar-fallback.tsx` and `frontend/src/components/empty-state.tsx` for new UI primitives.
- `frontend/src/components/sidebar-nav.tsx` and `frontend/src/layouts/dashboard-layout.tsx` for the app shell and navigation.
- `frontend/src/pages/dashboard-page.tsx` and `frontend/src/pages/profile-page.tsx` for the main view content.

#### Features Added / Updated / Removed

- Added: Responsive sidebar and mobile drawer navigation.
- Added: Proper document and template empty states on the dashboard.
- Added: Full read-only profile rendering.
- Updated: `User` interface to match Member 2/3 backend contract.
- Removed: Legacy placeholder cards on the dashboard.

#### Issues Fixed

- None

#### Notes For Next Push

- Member 1 frontend Phase 3 is complete and ready for integration testing.

---

### Checkpoint 0009

- Date: 2026-08-03
- Member: Member 1 (AI)
- Branch: `dev`
- Push status: before push
- Range covered: after Checkpoint 0008 -> 2026-08-03

#### Summary

- Fixed an Alembic configuration bug that crashed migrations when the Neon database connection string contained `%` characters (such as `%3D` in `options=endpoint%3D...`).

#### Completed Tasks

- Updated `alembic/env.py` to correctly escape `%` characters by replacing them with `%%` before passing the `DATABASE_URL` to `configparser`.

#### Code Changes

- `backend/alembic/env.py`

#### Features Added / Updated / Removed

- Added: None
- Updated: None
- Removed: None

#### Issues Fixed

- Fixed `ValueError: invalid interpolation syntax` during `alembic upgrade head`.

#### Notes For Next Push

- Ready for push.

---

### Checkpoint 0010

- Date: 2026-08-03
- Member: Member 3 (AI)
- Branch: `feature/backend-template-model`
- Push status: before push
- Range covered: after Checkpoint 0009 -> 2026-08-03

#### Summary

- Implemented V1.2 Phase 1 Database / Integration Developer tasks: Added the `Template` database model, Pydantic schemas, CRUD operations, and generated Alembic migration for template uploads.

#### Completed Tasks

- Created SQLAlchemy `Template` model with appropriate columns and validation for categories, visibility, and status.
- Added a backref `templates` relationship to the `User` model.
- Generated and successfully tested Alembic migration `20260803_04_create_templates_table.py` for Neon PostgreSQL.
- Created Pydantic v2 schemas `TemplateCreate`, `TemplateResponse`, and `TemplateListItem`.
- Created basic AsyncSession CRUD operations (`create_template`, `get_template_by_id`, `get_templates_by_user`).
- Added an offline integration smoke test for the Template model defaults.

#### Code Changes

- `backend/app/models/template.py` and `backend/app/models/__init__.py` for the database model definition.
- `backend/app/models/user.py` for relationship mapping.
- `backend/alembic/versions/20260803_04_create_templates_table.py` for the database migration.
- `backend/app/schemas/template.py` for Pydantic definitions.
- `backend/app/crud/template_crud.py` and `backend/app/crud/__init__.py` for CRUD functions.
- `backend/tests/test_template_model.py` for the model tests.

#### Features Added / Updated / Removed

- Added: `Template` database model and corresponding table migration.
- Added: Pydantic schemas and CRUD utilities for Template API operations.
- Updated: `User` model to link uploaded templates.
- Removed: None

#### Issues Fixed

- None

#### Notes For Next Push

- Member 2 can now import `TemplateCreate`, `TemplateResponse`, and `create_template` to wire up the document upload route.

### Checkpoint 0011

- Date: 2026-08-09
- Member: Member 2 (AI)
- Branch: `feature/backend-template-model`
- Push status: before push
- Range covered: after Checkpoint 0010 -> 2026-08-09

#### Summary

- Implemented V1.2 Phase 1 Backend/Service Developer tasks: Created the original template file upload endpoint with validation, storage saving, and database record insertion.

#### Completed Tasks

- Created `POST /upload` endpoint for `.docx` files under the `/templates` router.
- Implemented file validation (extension, size, empty file) and metadata validation (name length, category, visibility constraints).
- Integrated with `storage_service` to persist the original `.docx` locally.
- Handled database insertion with `create_template` and implemented cleanup of the local file if DB insertion fails.
- Registered `templates.router` in `api.py`.
- Refactored `template_crud.py` to correctly use the synchronous `Session` as dictated by the project configuration.

#### Code Changes

- `backend/app/api/v1/endpoints/templates.py` for upload endpoint.
- `backend/app/api/v1/api.py` for routing setup.
- `backend/app/crud/template_crud.py` for synchronous session refactor.

#### Features Added / Updated / Removed

- Added: `POST /api/v1/templates/upload` authenticated endpoint for templates.
- Updated: DB CRUD `create_template` to execute synchronously.
- Removed: None

#### Issues Fixed

- Fixed an asynchronous `AsyncSession` mismatch bug in `template_crud.py` by converting it to match the rest of the synchronous DB architecture.

#### Notes For Next Push

- Member 1 can now build the frontend upload form and submit requests to this new API endpoint.

### Checkpoint 0012

- Date: 2026-08-09
- Member: Member 1 (AI)
- Branch: `feature/frontend-template-upload`
- Push status: before push
- Range covered: after Checkpoint 0011 -> 2026-08-09

#### Summary

- Implemented V1.2 Phase 1 Frontend Developer tasks: Created the original template file upload UI with drag-and-drop, client-side validation, and mock API integration.

#### Completed Tasks

- Built `UploadZone` drag-and-drop component rejecting non-.docx or >10MB files.
- Built `UploadTemplateForm` with plain React state and full client-side validation matching the login page pattern.
- Added `TemplateResponse` schema and `templatesApi.upload` fetch call with FormData.
- Created `upload-template-page.tsx` and wired it into the dashboard route.
- Added "Upload Template" link to sidebar.
- Wired dashboard empty state to navigate to the new page.

#### Code Changes

- `frontend/src/components/upload/UploadZone.tsx` (new)
- `frontend/src/components/upload/UploadTemplateForm.tsx` (new)
- `frontend/src/pages/upload-template-page.tsx` (new)
- `frontend/src/lib/api.ts`
- `frontend/src/components/sidebar-nav.tsx`
- `frontend/src/App.tsx`
- `frontend/src/layouts/dashboard-layout.tsx`
- `frontend/src/pages/dashboard-page.tsx`
- `frontend/src/components/empty-state.tsx`

#### Features Added / Updated / Removed

- Added: Template upload form with drag-and-drop and validation.
- Added: Client-side API fetch setup for multipart file upload.
- Updated: Dashboard navigation to include upload page.
- Removed: None

#### Issues Fixed

- None

#### Notes For Next Push

- The API call currently uses a 2-second mock. Once Member 2 completes the backend integration and pushes to `dev`, this mock can be removed and replaced with the actual fetch call logic (already written and commented out).

---

### Checkpoint 0013

- Date: 2026-08-09
- Member: Member 1 (AI)
- Branch: `fix/v12-phase1-audit-issues`
- Push status: before push
- Range covered: after Checkpoint 0012 -> 2026-08-09

#### Summary

- Addressed V1.2 Phase 1 audit findings by completing the frontend form validation migration, fixing backend storage path loading, adding app lifecycle storage initialization, and ensuring asynchronous thread pooling for file I/O operations.

#### Completed Tasks

- Rewrote `UploadTemplateForm` to use `react-hook-form` and `zod` for per-field validation.
- Installed and integrated `shadcn/ui` form components (`Form`, `Input`, `Textarea`, `Select`, `Label`).
- Added `storage_base_path` configuration to `config.py` and removed hardcoded path in `storage_service.py`.
- Added a `lifespan` event hook to `main.py` that calls `ensure_storage_tree()` on startup.
- Introduced `asyncio.to_thread` for the synchronous `save_bytes` and `delete_file` storage methods inside the async upload endpoint.
- Added extensive `logging` integration to `storage_service.py` and `templates.py`.

#### Code Changes

- `frontend/src/components/upload/UploadTemplateForm.tsx`
- `frontend/src/components/ui/` (added form, input, label, select, textarea)
- `backend/app/core/config.py`
- `backend/app/services/storage_service.py`
- `backend/app/main.py`
- `backend/app/api/v1/endpoints/templates.py`

#### Features Added / Updated / Removed

- Added: Per-field validation feedback UI and upload spinner.
- Updated: Storage directory is now auto-created at app startup.
- Updated: Storage saving operations are non-blocking via thread pooling.
- Removed: None

#### Issues Fixed

- Fixed all 8 issues (4 critical, 4 moderate) raised during the V1.2 Phase 1 audit.

#### Notes For Next Push

- Changes cover cross-stack bugfixes for the V1.2 Phase 1 implementation. The branch is ready for review and merge into `dev`.

---

### Checkpoint 0014

- Date: 2026-08-09
- Member: Member 3 (AI)
- Branch: `dev`
- Push status: before push
- Range covered: after Checkpoint 0013 -> 2026-08-09

#### Summary

- Completed V1.2 Phase 2 Database/Integration Developer tasks. Added comprehensive integration tests for template upload, expanded model tests, added Phase 3 CRUD stubs, and patched the Alembic migration for cross-dialect SQLite test compatibility.

#### Completed Tasks

- Verified and patched `create_templates_table` migration to use `CURRENT_TIMESTAMP` instead of `now()` to fix SQLite syntax errors during testing.
- Created `test_template_upload.py` with 9 integration tests for the template upload endpoint, and scoped dependency overrides to avoid global pollution affecting other test suites.
- Expanded `test_template_model.py` with 5 new unit tests for `@validates`.
- Added `__init__` constructor to the `Template` model for immediate default values on instantiation.
- Appended Phase 3 CRUD stubs (`get_public_templates`, `get_templates_by_category`) to `template_crud.py`.

#### Code Changes

- `backend/alembic/versions/20260803_04_create_templates_table.py`
- `backend/tests/test_template_upload.py`
- `backend/tests/test_template_model.py`
- `backend/app/models/template.py`
- `backend/app/crud/template_crud.py`

#### Features Added / Updated / Removed

- Added: 9 integration tests for template uploads and 5 model unit tests.
- Added: Phase 3 CRUD stubs for fetching public templates and templates by category.
- Updated: `Template` model to set python-side defaults instantly.
- Removed: None

#### Issues Fixed

- Fixed cross-dialect Alembic bug causing SQLite `SyntaxError` on `server_default=sa.text('now()')`.
- Fixed global test runner pollution by scoping `TestClient` dependency overrides to individual fixtures.

#### Notes For Next Push

- Tests are passing successfully (`pytest tests/ -v`). Ready for push. Manual validation on the Neon database via SQL is recommended post-deployment to definitively check `original_file_path`.

---

### Checkpoint 0015

- Date: 2026-08-09
- Member: Member 2 (AI)
- Branch: feature/template-upload-integration
- Push status: before push
- Range covered: after Checkpoint 0014 -> 2026-08-09

#### Summary

- Completed V1.2 Phase 2 Backend Developer tasks. Audited the template upload endpoint, added new GET routes for template list and detail, and verified CORS and router configuration.

#### Completed Tasks

- Added audit comment to `POST /upload` confirming correct file type validation, DB rollback, and async I/O.
- Implemented `GET /api/v1/templates/` to return the current user's templates.
- Implemented `GET /api/v1/templates/{template_id}` to retrieve a single template with authorization checks (403/404).
- Verified router registration in `api.py` and CORS configuration in `main.py`.

#### Code Changes

- `backend/app/api/v1/endpoints/templates.py`

#### Features Added / Updated / Removed

- Added: `GET /api/v1/templates/` and `GET /api/v1/templates/{template_id}` endpoints.
- Updated: None
- Removed: None

#### Issues Fixed

- None

#### Notes For Next Push

- All integration tests pass successfully. The backend is fully ready for the frontend integration.

---

### Checkpoint 0016

- Date: 2026-08-09
- Member: Member 1 (AI)
- Branch: current
- Push status: before push
- Range covered: after Checkpoint 0015 -> 2026-08-09

#### Summary

- Completed V1.2 Phase 2 Frontend Developer tasks. Replaced the mock upload API with a real fetch call, added a 3-step upload status strip, polished the success state, and mapped specific API errors to user-friendly messages.

#### Completed Tasks

- Replaced the mock API upload function with a real `fetch` using `FormData`.
- Added a responsive 3-step status strip ("Fill Details", "Uploading File", "Done") to the upload template page.
- Enhanced the success state in `UploadTemplateForm.tsx` to display the file size and a shadcn `<Badge>` for the category.
- Created a `mapApiError` utility to display specific user-friendly error messages for known API errors (e.g. invalid file type, file too large, session expired).

#### Code Changes

- `frontend/src/lib/api.ts`
- `frontend/src/pages/upload-template-page.tsx`
- `frontend/src/components/upload/UploadTemplateForm.tsx`
- `frontend/src/components/ui/badge.tsx` (new)

#### Features Added / Updated / Removed

- Added: 3-step visual status strip for template uploads.
- Added: shadcn `<Badge>` component to the frontend.
- Updated: Template upload now integrates with the real backend API.
- Updated: Enhanced success and error states on template upload.
- Removed: Mock `setTimeout` upload implementation in `api.ts`.

#### Issues Fixed

- None

#### Notes For Next Push

- V1.2 Phase 2 frontend tasks are completely implemented and ready to test end-to-end with the backend.

---

### Checkpoint 0017

- Date: 2026-08-21
- Member: Member 3 (AI)
- Branch: feature/frontend-template-upload-integration
- Push status: before push
- Range covered: after Checkpoint 0016 -> 2026-08-21

#### Summary

- Completed V1.2 Phase 3 Database / Integration tasks. Added backend CRUD operations, models, endpoints, tests, and a seed script to support the new Template Library feature.

#### Completed Tasks

- Implemented `get_library_templates` CRUD function with search, category, visibility filtering, and pagination support.
- Added `get_template_count_by_user` and `search_templates` CRUD utility functions.
- Added `TemplateLibraryResponse` Pydantic schema for paginated responses.
- Added `GET /api/v1/templates/library` endpoint for browsing templates.
- Updated `GET /api/v1/templates/{id}` endpoint to securely allow public template access by non-owners.
- Created `test_template_library.py` with 12 rigorous integration tests covering filters, search, visibility constraints, and pagination.
- Created `seed_templates.py` script to insert 12 sample templates into the database for demo/testing purposes.

#### Code Changes

- `backend/app/crud/template_crud.py`
- `backend/app/schemas/template.py`
- `backend/app/api/v1/endpoints/templates.py`
- `backend/tests/test_template_library.py` (new)
- `backend/scripts/seed_templates.py` (new)

#### Features Added / Updated / Removed

- Added: Backend data layer, API endpoint, schemas, and tests for the Template Library.
- Added: Demo seed script for templates.
- Updated: Template detail endpoint to respect public visibility.
- Removed: None

#### Issues Fixed

- None

#### Notes For Next Push

- All 52 backend integration tests pass. The API is fully prepared for Member 1 to consume and build the frontend Template Library UI.

---

### Checkpoint 0018

- Date: 2026-08-21
- Member: Member 1 (AI)
- Branch: feature/frontend-template-library-phase3
- Push status: before push
- Range covered: after Checkpoint 0017 -> 2026-08-21

#### Summary

- Completed V1.2 Phase 3 Frontend Developer tasks. Built the Template Library and Template Detail pages, including UI components for cards, search, filters, and a responsive grid layout.

#### Completed Tasks

- Added `TemplateListItem` and `TemplateLibraryResponse` interfaces to `api.ts`.
- Implemented `getLibrary`, `getTemplateDetail`, and `getMyTemplates` API methods.
- Built `TemplateCard`, `TemplateSearchBar`, `TemplateFilters`, and `TemplateGrid` components.
- Built `TemplateLibraryPage` with search/filter/pagination logic and integrated the components.
- Built `TemplateDetailPage` to display comprehensive template metadata, and handle 404/403 errors correctly.
- Added routes for `/templates` and `/templates/:id` to `App.tsx`.
- Updated `sidebar-nav.tsx` to include "Template Library" link and icon.
- Added `skeleton` UI component from shadcn/ui.

#### Code Changes

- `frontend/src/lib/api.ts`
- `frontend/src/components/templates/TemplateCard.tsx` (new)
- `frontend/src/components/templates/TemplateSearchBar.tsx` (new)
- `frontend/src/components/templates/TemplateFilters.tsx` (new)
- `frontend/src/components/templates/TemplateGrid.tsx` (new)
- `frontend/src/pages/template-library-page.tsx` (new)
- `frontend/src/pages/template-detail-page.tsx` (new)
- `frontend/src/components/ui/skeleton.tsx` (new)
- `frontend/src/App.tsx`
- `frontend/src/components/sidebar-nav.tsx`

#### Features Added / Updated / Removed

- Added: Template Library page to browse all accessible templates.
- Added: Template Detail page for inspecting a template's metadata.
- Added: Search, filter, and pagination capabilities on the frontend.
- Updated: Sidebar navigation to point directly to the new Template Library.
- Removed: "coming soon" badge from the templates navigation link.

#### Issues Fixed

- Fixed shadcn/ui adding `skeleton.tsx` to the wrong directory (moved from `@/components/ui/` to `src/components/ui/`).

#### Notes For Next Push

- V1.2 Phase 3 Frontend tasks are complete and pass `npm run build` with no typescript errors. Ready for push and integration review.

---

### Checkpoint 0019

- Date: 2026-08-23
- Member: Member 1, 2, 3 (AI)
- Branch: `dev`
- Push status: before push
- Range covered: after Checkpoint 0018 -> 2026-08-23

#### Summary

- Resolved all outstanding bugs from V1.1 and V1.2 audits (Dashboard integration, backend wildcard search, storage cleanup) and initialized the V1.3 database schema for placeholder detection.

#### Completed Tasks

- Dashboard "My Templates" wired to fetch real templates (`api.ts` -> `dashboard-page.tsx`).
- Replaced dashboard developer copy and dummy buttons with actual user-friendly text and internal links.
- Updated template upload success state to link directly to `/templates/:id`.
- Removed redundant `storage.py` endpoint from the backend.
- Added `_escape_like` to `template_crud.py` to prevent SQL wildcard `%` and `_` matching issues.
- Ignored/deleted local `test.db`.
- Built `TemplateField` database model, Pydantic schemas, and Alembic migration for V1.3 Phase 1.

#### Code Changes

- `frontend/src/pages/dashboard-page.tsx`
- `frontend/src/components/upload/UploadTemplateForm.tsx`
- `backend/app/crud/template_crud.py`
- `backend/app/api/v1/api.py` and `backend/app/api/v1/endpoints/storage.py` (deleted)
- `backend/app/models/template_field.py` (new) and `backend/app/models/template.py` (updated)
- `backend/app/schemas/template_field.py` (new)
- `backend/alembic/versions/fb6604df0637_add_template_fields_table.py` (new)
- `.gitignore` (updated)

#### Features Added / Updated / Removed

- Added: `template_fields` PostgreSQL table for V1.3 placeholder detection.
- Updated: Dashboard UI properly integrated with backend template data.
- Removed: Unused `storage.py` API endpoint and `test.db`.

#### Issues Fixed

- Fixed BUG-003, BUG-007, BUG-008, BUG-009, BUG-010, BUG-013, BUG-014, BUG-015 from the `bugs.md` audit.

#### Notes For Next Push

- V1.1 and V1.2 are officially complete and bug-free. Ready to commence building V1.3 backend logic.

---

### Checkpoint 0020

- Date: 2026-08-28
- Member: AI Assistant
- Branch: feature/backend-template-rbac
- Push status: before push
- Range covered: after Checkpoint 0019 -> 2026-08-28

#### Summary

- Implemented Role-Based Access Control (RBAC) visibility filtering for templates in the backend.

#### Completed Tasks

- Updated `get_template` endpoint to check user's role, department, organization, and group against template visibility settings.
- Updated `get_library_templates` CRUD operation to dynamically filter templates based on the user's role, department, organization, and group.
- Granted `super_admin` role access to all templates regardless of visibility settings.

#### Code Changes

- `backend/app/api/v1/endpoints/templates.py`
- `backend/app/crud/template_crud.py`

#### Features Added / Updated / Removed

- Added: Dynamic RBAC visibility filtering for templates based on user attributes (department, organization, group, role).
- Updated: `get_template` and `get_library_templates` to enforce visibility rules.
- Removed: None

#### Issues Fixed

- None

#### Notes For Next Push

- Needs corresponding frontend tests or updates if UI behavior depends on these new visibility rules.

---

### Checkpoint 0021

- Date: 2026-08-28
- Member: Member 1 (AI)
- Branch: feature/placeholder-detection
- Push status: before push
- Range covered: after Checkpoint 0020 -> 2026-08-28

#### Summary

- Implemented the V1.3 Phase 1 Member 1 frontend slice: the owner-facing Placeholder Detection UI (API client methods, owner-aware detail page actions, Placeholder Review page with warnings, and routing).

#### Completed Tasks

- Added `TemplateField`, `DetectionWarnings`, and `PlaceholderDetectionResponse` types to the frontend API client.
- Added `templatesApi.detectPlaceholders(token, id, force)` (`POST /templates/{id}/detect-placeholders`) and `templatesApi.getFields(token, id)` (`GET /templates/{id}/fields`) to the frontend API client.
- Replaced the disabled "Use This Template" stub on the template detail page with an owner-only, status-aware config action: `uploaded` -> "Detect Placeholders", `placeholder_detected` -> "Review Fields", `field_configured`/`active` -> "Edit Fields".
- Rendered the template status as a colored Badge on the detail page; non-owners keep the read-only view.
- Built the Placeholder Review page (`/templates/:id/placeholders`): detect trigger when no fields exist, ordered detected-fields list (display_order, label with field_name fallback, type Badge, mono `{{key}}`, Required badge), warnings panel (duplicate, invalid-name, parse_error), confirm-guarded Re-detect, Phase 2 empty state, and loading/403/404 error states.
- Added the shadcn `Dialog` component (Radix) and used it to confirm re-detection (replaces fields).
- Created the Field Setup page stub for the Phase 3 route (`/templates/:id/fields`).
- Registered `/templates/:id/placeholders` and `/templates/:id/fields` routes in `App.tsx` inside `ProtectedRoute` + `DashboardLayout`.
- Verified `npm run build` passes with strict TypeScript.

#### Code Changes

- `frontend/src/lib/api.ts` (modified — types + 2 API methods)
- `frontend/src/pages/template-detail-page.tsx` (modified — owner-aware actions + status badge)
- `frontend/src/pages/placeholder-review-page.tsx` (new)
- `frontend/src/pages/field-setup-page.tsx` (new — Phase 3 stub)
- `frontend/src/pages/dashboard-page.tsx` (modified — token bug fix)
- `frontend/src/components/ui/dialog.tsx` (new)
- `frontend/src/App.tsx` (modified — 2 new routes)
- `frontend/package.json`, `package-lock.json` (added `@radix-ui/react-dialog`)

#### Features Added / Updated / Removed

- Added: Placeholder Review page with detection trigger, detected-fields list, and warnings panel; owner-only config actions on the template detail page; `Dialog` UI primitive; detection API client methods and types; Field Setup stub route.
- Updated: Template detail page status Badge and primary action; frontend API client.
- Removed: Disabled "Use This Template" stub button (filling a form from a template is V1.4; replaced with owner config action).

#### Issues Fixed

- Fixed pre-existing build-breaking bug in `dashboard-page.tsx`: destructured `token` from `useAuth()` (not exposed by the auth context); now reads `localStorage.getItem("templateos_access_token")` per project convention.
- Restored `project-change-tracker.md` after the working copy was accidentally wiped to a single line.

#### Notes For Next Push

- Backend endpoints `POST /templates/{id}/detect-placeholders` and `GET /templates/{id}/fields` (Member 2, V1.3 Phase 1) are not yet implemented; the review page is built against the agreed typed shapes and needs end-to-end wiring once available.
- Detection warnings render only for the current detection session (the backend does not persist warnings with the fields).
- The Field Setup page is a stub pending V1.3 Phase 3.

---

### Checkpoint 0022

- Date: 2026-08-28
- Member: Member 3 (AI)
- Branch: feature/template-fields-metadata
- Push status: before push
- Range covered: after Checkpoint 0020 -> 2026-08-28
- Note: Checkpoint 0021 (V1.3 Phase 1 Member 1 frontend) lives on `feature/placeholder-detection` and is not merged yet; numbering skips it on this branch.

#### Summary

- Expanded `template_fields` to the full V1.3 field-metadata contract (model + additive migration + schemas) and added the `template_field_crud` persistence layer Member 2's detection endpoint will call.

#### Completed Tasks

- Expanded `app/models/template_field.py`: `FIELD_TYPES` corrected to the MVP set (`text, textarea, date, number, list, signature` — removed `dropdown`), added `field_label`, `section`, `example_value`, `validation_rule`, `ai_enabled` columns, custom `__init__` defaults, `UniqueConstraint("template_id", "field_name")` and composite `Index(template_id, display_order)`.
- Patched migration `fb6604df0637`: `sa.text('now()')` -> `sa.text('CURRENT_TIMESTAMP')` for `created_at`/`updated_at` (cross-dialect rule; SQLite tests were failing on `DEFAULT now()`).
- New additive migration `7c4e9a1b2d58_expand_template_fields_metadata`: adds the 5 columns (`ai_enabled` NOT NULL with server_default `false`), the unique constraint (via `batch_alter_table` for SQLite compatibility), and the composite index; verified `upgrade head`, `downgrade -1`, and re-upgrade clean on a scratch SQLite DB.
- Expanded `app/schemas/template_field.py`: full `TemplateFieldBase/Create/Update/Read` (label, section, example, validation, ai_enabled) + Phase 1 detection-response schemas (`DuplicateFieldWarning`, `InvalidFieldNameWarning`, `DetectionWarnings`, `DetectionSummary`, `PlaceholderDetectionResponse`).
- Created `app/crud/template_field_crud.py`: `bulk_create_fields`, `get_fields_by_template` (ordered by display_order, id), `delete_fields_by_template`, `field_exists`; registered in `app/crud/__init__.py`.
- New tests: `tests/test_template_field_model.py` (model defaults/validation/unique constraint + full CRUD coverage) and `tests/test_placeholder_detection.py` (persistence-flow tests now; endpoint contract tests auto-skip until Member 2's detect-placeholders / fields routes exist, then activate).
- Full suite: 67 passed, 8 skipped (endpoint tests awaiting Member 2); previously failing `test_profile_migration_upgrade_and_downgrade` now passes.

#### Code Changes

- `backend/app/models/template_field.py` (expanded)
- `backend/alembic/versions/7c4e9a1b2d58_expand_template_fields_metadata.py` (new)
- `backend/alembic/versions/fb6604df0637_add_template_fields_table.py` (timestamp patch)
- `backend/app/schemas/template_field.py` (expanded)
- `backend/app/crud/template_field_crud.py` (new) and `backend/app/crud/__init__.py` (register)
- `backend/tests/test_template_field_model.py`, `backend/tests/test_placeholder_detection.py` (new)

#### Features Added / Updated / Removed

- Added: full field-metadata columns on `template_fields`; `(template_id, field_name)` uniqueness; ordered field reads; detection-response Pydantic schemas; `template_field_crud` helpers.
- Updated: `FIELD_TYPES` vocabulary to the MVP set; migration timestamps to `CURRENT_TIMESTAMP`.
- Removed: `dropdown` from the allowed field types.

#### Issues Fixed

- Fixed pre-existing failure `tests/test_user_profile_data.py::test_profile_migration_upgrade_and_downgrade` — SQLite rejected `DEFAULT now()` emitted by `fb6604df0637`.

#### Notes For Next Push

- Member 2 (V1.3 Phase 1) can now build `docx_parser.py` + the detect-placeholders/fields endpoints on top of this CRUD and the `PlaceholderDetectionResponse` schema; the 8 skipped endpoint tests in `test_placeholder_detection.py` will activate automatically and encode the agreed contract (ordered persistence, duplicate collapse, invalid-name exclusion with suggested keys, idempotency, force re-detect, owner-only 403, split-across-runs parity, no-500 on malformed tokens).
- Run `alembic upgrade head` against Neon when deploying (migration `7c4e9a1b2d58` is additive and safe for existing rows).

---

### Checkpoint 0023

- Date: 2026-08-28
- Member: Member 2 (AI)
- Branch: feature/backend-docx-placeholder-detection
- Push status: before push
- Range covered: after Checkpoint 0022 -> 2026-08-28

#### Summary

- Implemented V1.3 Phase 1 placeholder detection backend: the pure DOCX parsing service (python-docx text extraction + docxtpl authoritative variable detection), the reusable view-access helper, and the owner-only detect-placeholders + view-access fields-read endpoints persisting through Member 3's CRUD.

#### Completed Tasks

- Added `docxtpl==0.20.2` and `python-docx==1.1.2` to `backend/requirements.txt` (docxtpl adopted in V1.3 for detect/generate parity — the same Jinja2 engine that renders in V1.6).
- Created `app/services/docx_parser.py` (pure, no DB): `extract_text_segments` (body in true document order, table cells with nested recursion, section headers/footers — one shared DocxTemplate parse), `get_template_variables` (docxtpl `get_undeclared_template_variables`, catches Jinja `TemplateSyntaxError` and degrades to `(None, message)` — never 500s), `PLACEHOLDER_PATTERN` / `VALID_KEY_PATTERN`, `detect_placeholders` (regex scan for ordering/duplicates/malformed tokens + docxtpl parity intersection with regex-key-valid fallback and `parse_warning`), plus `suggest_key` / `humanize_key` helpers.
- Created `app/services/template_access.py`: extracted the inline `has_access` ladder from `get_template` into `user_can_view_template(user, template)` (identical behavior); reused by `get_template` and the new fields endpoint.
- Added `POST /api/v1/templates/{template_id}/detect-placeholders?force=` — owner-only (403), 404 missing template, 409 no source file / file missing on disk, storage read + CPU-bound parsing via `asyncio.to_thread`, idempotent without force (returns existing fields + fresh warnings, `already_detected=true`), force replaces fields via `delete_fields_by_template` + `bulk_create_fields`, persists `field_name`/humanized `field_label`/`text`/required/first-seen `display_order`, advances status to `placeholder_detected` only from `uploaded`/`placeholder_detected`, returns `PlaceholderDetectionResponse` (fields + warnings + summary), logs start/finish with counts.
- Added `GET /api/v1/templates/{template_id}/fields` — view access via `user_can_view_template`, returns `list[TemplateFieldRead]` ordered by `display_order`.
- Fixed docxtpl lazy initialization: `DocxTemplate.init_docx()` must be called before accessing `.docx`.
- All 8 previously-skipped endpoint contract tests in `tests/test_placeholder_detection.py` activated and pass; full suite 75 passed, 0 skipped.

#### Code Changes

- `backend/requirements.txt` (docxtpl + python-docx)
- `backend/app/services/docx_parser.py` (new)
- `backend/app/services/template_access.py` (new)
- `backend/app/api/v1/endpoints/templates.py` (refactored `get_template` to use the helper; added 2 routes)

#### Features Added / Updated / Removed

- Added: placeholder detection service with detect/generate parity; owner-only detection endpoint with idempotency and force re-detect; ordered fields-read endpoint with RBAC view access; reusable `user_can_view_template` helper.
- Updated: `get_template` now delegates to the shared access helper (behavior unchanged).
- Removed: inline `has_access` ladder duplication in `templates.py`.

#### Issues Fixed

- None (the docxtpl `init_docx()` lazy-init issue was found and fixed within this same change).

#### Notes For Next Push

- The V1.3 Phase 1 backend is feature-complete end to end (parser -> endpoint -> persistence); Member 1's frontend PR #57 (`feature/placeholder-detection`) can now be verified against these real endpoints and amended if any response-shape fixes are needed before merging into `frontend`.
- Deploy note: `pip install -r requirements.txt` (new deps) — no new migration in this slice.
- `extract_text_segments` / `get_template_variables` / `PLACEHOLDER_PATTERN` / `VALID_KEY_PATTERN` are reused by Phase 2 (cleaning) and Phase 4 (AI context excerpt).

---

### Checkpoint 0024

- Date: 2026-08-28
- Member: Member 3 (AI)
- Branch: feature/template-cleaning-data-layer
- Push status: before push
- Range covered: after Checkpoint 0023 -> 2026-08-28

#### Summary

- Implemented the V1.3 Phase 2 Member 3 data layer for manual template cleaning: clean request/response schemas, processed-path/status/append-field CRUD helpers, the additive `template_fields.source` provenance column, and the test suite (cleaner + endpoint tests skip-guarded until Member 2 ships).

#### Completed Tasks

- Created `app/schemas/cleaning.py`: `PlaceholderReplacement` (validated `placeholder_key` via `^[a-z][a-z0-9_]*$`, `field_type` membership in MVP `FIELD_TYPES`, non-empty `sample_text`), `CleanTemplateRequest` (`replacements` min_length 1, `confirm` gate defaulting false, `mark_configured`), `ReplacementResult`, `CleanWarnings`, `CleanTemplateResponse`.
- Added `app/crud/template_crud.py` helpers: `set_processed_path` (records processed path, never touches original), `advance_status` (explicit rank map, forward-only, raises on unknown statuses, never downgrades field_configured/active/archived/locked).
- Added `app/crud/template_field_crud.py` helpers: `next_display_order` (max+1, 0 if none) and `append_field` (idempotent — skips via `field_exists` guard, auto-assigns next display_order); registered all four in `app/crud/__init__.py`.
- Added the recommended additive migration `3f8d2c6a9e41_add_template_fields_source`: `template_fields.source` (`detected`/`cleaned`/`manual`/`ai`), NOT NULL with `server_default 'detected'`, chained off `7c4e9a1b2d58`; verified upgrade/downgrade/re-upgrade clean on scratch SQLite; single head.
- Expanded `TemplateField` model (FIELD_SOURCES + `@validates("source")` + `source` column with defaults) and `TemplateFieldCreate/Update/Read` schemas (`source` field with membership validation, default `detected`) — Phase 2 cleaning sets `source="cleaned"`, Phase 4 sets `source="ai"`.
- New `tests/test_template_cleaning.py`: schema validation (invalid keys/types/replacements/confirm default), CRUD units (path preservation, forward-only status incl. no-downgrade, order sequencing, duplicate skip), and skip-guarded cleaner units (`apply_replacements` — placeholder produced, original unchanged, split-run rewrite, unmatched reporting) + endpoint tests (happy path with `example_value` = sample text + `source="cleaned"`, confirm 400, non-owner 403, empty 400/422, invalid key 422, idempotent re-clean, `mark_configured`, no status downgrade).
- Full suite: 88 passed, 11 skipped (3 cleaner + 8 endpoint tests awaiting Member 2, skip reasons explicit).

#### Code Changes

- `backend/app/schemas/cleaning.py` (new)
- `backend/app/crud/template_crud.py`, `backend/app/crud/template_field_crud.py`, `backend/app/crud/__init__.py` (new helpers + registration)
- `backend/app/models/template_field.py`, `backend/app/schemas/template_field.py` (`source` column/field)
- `backend/alembic/versions/3f8d2c6a9e41_add_template_fields_source.py` (new)
- `backend/tests/test_template_cleaning.py` (new)

#### Features Added / Updated / Removed

- Added: cleaning data contracts (`CleanTemplateRequest/Response` etc.), processed-path/status/append-field CRUD, `template_fields.source` provenance column, forward-only status guard.
- Updated: `TemplateField` model + schemas now carry `source`.
- Removed: none.

#### Issues Fixed

- None.

#### Notes For Next Push

- Member 2 (V1.3 Phase 2) builds `app/services/docx_cleaner.py` (`apply_replacements` returning processed bytes; `ReplacementSpec(sample_text, placeholder_key)`; optional `return_unmatched=True` mode) and the `GET /{id}/content` + `POST /{id}/clean` endpoints using these schemas/CRUD; the 3+8 skipped tests in `test_template_cleaning.py` then activate and encode the agreed contract (split-run rewrite, `{{ key }}` spacing, occurrences count, idempotency, confirm/owner guards, `mark_configured`).
- Deploy note: `alembic upgrade head` on Neon applies `3f8d2c6a9e41` (additive, safe — existing rows backfill to `detected`).
- The `source` values feed the Phase 4 AI-generation audit and the UI badge.

---

### Checkpoint 0025

- Date: 2026-08-28
- Member: Member 2 (AI)
- Branch: feature/backend-template-cleaning
- Push status: before push
- Range covered: after Checkpoint 0024 -> 2026-08-28

#### Summary

- Implemented V1.3 Phase 2 manual template cleaning: the pure DOCX replacement engine (`docx_cleaner.py`, run-split aware), the `GET /{id}/content` selection endpoint and the owner-only confirmed `POST /{id}/clean` endpoint persisting through Member 3's schemas/CRUD, plus the `get_renderable_path` generation-source contract.

#### Completed Tasks

- Created `app/services/docx_cleaner.py` (pure, no DB): `ReplacementSpec`/`ReplacementResult` dataclasses, `apply_replacements(bytes, replacements, return_unmatched=False)` (typed overloads; bytes or `(bytes, unmatched)`), `apply_replacements_with_results` for the endpoint's per-replacement outcomes, and `get_renderable_path(template)` (processed-else-original contract for V1.6). Paragraph-level rewrite handles Word's run-splitting (first run keeps formatting, rest blanked — accepted MVP tradeoff); walks body paragraphs, table cells (recursive), section headers/footers; works on a copy (caller's bytes never mutated); invalid keys (failing Phase 1's `VALID_KEY_PATTERN`) are skipped with `reason="invalid_key"` and never injected; accepts ReplacementSpec, Pydantic models, or raw dicts.
- Added `GET /api/v1/templates/{template_id}/content`: view-access via `user_can_view_template`, returns `{template_id, segments, has_processed}` using Phase 1's `extract_text_segments` (run in `asyncio.to_thread`), 404/403/409 guards.
- Added `POST /api/v1/templates/{template_id}/clean` (body = Member 3's `CleanTemplateRequest`): owner-only 403, `confirm=true` required (400) + at-least-one-replacement (400), ALWAYS regenerates from the ORIGINAL bytes (re-clean never stacks), saves via `save_bytes("templates_processed", ...)`, `set_processed_path`, appends one field per MATCHED replacement via `append_field` (no dupes; `example_value` = sample text, `source="cleaned"`, humanized label fallback), `advance_status` to `field_configured` when `mark_configured` else `placeholder_detected` (never downgrades), returns `CleanTemplateResponse` with per-replacement results + `warnings{unmatched, invalid_keys}`; start/finish logging with counts.
- Added `processed_file_path` to `TemplateResponse` (schema contract addition — detail responses now expose the processed path; the Phase 2 UI needs it).
- Fixed the merged M3 test assertions that searched raw zip bytes for placeholders (DOCX entries are DEFLATE-compressed): now reads `word/document.xml` via `zipfile` — contract intent unchanged.
- All 11 previously-skipped tests activated and pass; full suite 99 passed, 0 skipped. Manual smoke test on an isolated server: content segments, confirm-gate 400, clean with occurrences/unmatched warnings, idempotent re-clean, original XML verified unchanged with sample text intact, processed XML verified to contain `{{ meeting_title }}`/`{{ meeting_date }}` and no leftover sample text.

#### Code Changes

- `backend/app/services/docx_cleaner.py` (new)
- `backend/app/api/v1/endpoints/templates.py` (2 new routes)
- `backend/app/schemas/template.py` (`processed_file_path` in TemplateResponse)
- `backend/tests/test_template_cleaning.py` (zip-aware placeholder assertions)

#### Features Added / Updated / Removed

- Added: DOCX cleaning engine with run-split handling; content (selection UI) endpoint; confirmed owner-only clean endpoint producing a processed DOCX; `get_renderable_path` renderable-source contract.
- Updated: `TemplateResponse` exposes `processed_file_path`.
- Removed: none.

#### Issues Fixed

- `apply_replacements` initially crashed on Pydantic replacement models (`PlaceholderReplacement` is not subscriptable) — `_normalize_specs` now accepts models, dicts, and ReplacementSpec.
- M3's raw-bytes placeholder assertions always failed on compressed zips — replaced with `word/document.xml` extraction.

#### Notes For Next Push

- Member 1 (V1.3 Phase 2) can now build the cleaning UI against `GET /{id}/content` (segments) + `POST /{id}/clean` (results + warnings); `TemplateResponse.processed_file_path` should be added to the frontend `TemplateResponse` type.
- No new migration in this slice; deploy note from 0024 still applies (`alembic upgrade head` for `3f8d2c6a9e41` on Neon).
- V1.6 generation must source files via `get_renderable_path(template)` (processed-else-original).

---

### Checkpoint 0026

- Date: 2026-08-28
- Member: Member 1 (AI)
- Branch: feature/frontend-template-cleaning
- Push status: before push
- Range covered: after Checkpoint 0023 (frontend branch) -> 2026-08-28
- Note: Checkpoints 0024 (P2 M3) and 0025 (P2 M2) live on the `backend` branch and are not merged here yet; numbering continues from the global sequence.

#### Summary

- Implemented the V1.3 Phase 2 Member 1 frontend slice: the owner-facing Template Cleaning UI — render document text segments, select sample values, stage replacements with before→after preview, and apply the cleaning behind a confirmation.

#### Completed Tasks

- Extended `frontend/src/lib/api.ts`: `DocSegment`, `TemplateContent`, `PlaceholderReplacement`, `ReplacementResult`, `CleanResponse`, `CleanTemplatePayload` types + `templatesApi.getContent(token, id)` and `templatesApi.cleanTemplate(token, id, payload)` methods; added optional `processed_file_path` to `TemplateResponse` (backend contract addition from checkpoint 0025).
- Created `frontend/src/pages/template-cleaning-page.tsx` (route `/templates/:id/clean`): owner-only (access notice + back link for non-owners); loads template + content in parallel (Skeleton, 403/404 error pattern); two-column responsive layout — LEFT renders text segments grouped by location (Body/Table/Header/Footer badges, mono text, whitespace-pre-wrap) with mouse/touch selection capture; RIGHT lists staged replacements (sample → `{{key}}` mono preview, type badge, label, remove) with an empty-state prompt; Convert dialog (RHF + Zod) with `placeholder_key` validated to the backend snake_case rule (mirrored error text), optional label/section, field-type Select over the MVP set, and a normalized key suggestion pre-filled from the selected text (mirrors backend `suggest_key`); duplicate staged keys rejected in-form; Apply bar with confirm dialog summarizing N conversions + original-preserved messaging (plus processed-copy-replacement note when one exists); result view with success banner (created-field count), created-fields list (label, `{{key}}`, type, "was: example_value"), unmatched/invalid-key warnings, and Continue to Field Setup / Back to Template actions; ApiError surfaces via red banner with the staged list kept for retry.
- Added the `/templates/:id/clean` route in `App.tsx` inside ProtectedRoute + DashboardLayout.
- Entry points: owner-only "Clean Template" action on the template detail page (secondary outline button next to the config action) and on the Placeholder Review page footer; the review page's no-placeholder empty state now navigates owners to cleaning (was a disabled "coming in Phase 2" stub) and the invalid-name/parse-error copy no longer references Phase 2 as future.
- Verified `npm run build` (strict TS + Vite) passes on the feature branch and on a combined backend+frontend integration tree.

#### Code Changes

- `frontend/src/lib/api.ts` (types + 2 methods + TemplateResponse field)
- `frontend/src/pages/template-cleaning-page.tsx` (new)
- `frontend/src/App.tsx` (route)
- `frontend/src/pages/template-detail-page.tsx` (owner entry)
- `frontend/src/pages/placeholder-review-page.tsx` (owner entry + live cleaning empty state + copy updates)

#### Features Added / Updated / Removed

- Added: Template Cleaning page (selection → staged replacements → confirmed apply → result), `getContent`/`cleanTemplate` API client methods and Phase 2 types, cleaning route.
- Updated: detail + review pages expose the owner-only Clean Template entry; review empty state and warning copy now reference the shipped cleaning feature; `TemplateResponse` carries `processed_file_path`.
- Removed: disabled "Template Cleaning (Coming soon)" stub on the review empty state.

#### Issues Fixed

- None (e2e setup initially used a stale local `backend` missing PR #64; refreshed before verification — no product code affected).

#### Notes For Next Push

- Verified live against the merged P2 backend (temp integration branch, deleted after): `GET /{id}/content` and `POST /{id}/clean` response keys match the TS types field-for-field (including `reason: null` on matched results), `TemplateResponse.processed_file_path` exposed, non-owner 403 on both endpoints, unconfirmed clean returns 400 "Cleaning must be confirmed", 99 backend tests pass on the combined tree.
- Integration reminder: merging `backend` (with 0024/0025) into `dev` and then syncing `frontend` will union the tracker checkpoints 0024–0026 in order.
- Phase 3 (Field Setup) will replace the `/templates/:id/fields` stub and can reuse the staged-replacement list patterns from this page.

---

### Checkpoint 0027

- Date: 2026-08-28
- Member: Member 2 (AI)
- Branch: feature/super-admin-template-delete
- Push status: before push
- Range covered: after Checkpoint 0025 -> 2026-08-28

#### Summary

- Added super-admin template deletion: `DELETE /api/v1/templates/{id}` permanently removes the template record (fields cascade) and every stored file (original + processed). Everyone else — including the template owner — gets 403.

#### Completed Tasks

- Added `DELETE /api/v1/templates/{template_id}` (204 No Content) in `templates.py`: super-admin-only guard (403 otherwise), 404 for missing templates; deletes the DB row first (ORM cascades `template_fields` via the relationship's `delete-orphan`), then removes `original_file_path` + `processed_file_path` from storage best-effort (`asyncio.to_thread`, `StorageError` logged as a warning so a storage hiccup never leaves a template row pointing at deleted files); structured logging of the deletion.
- New `tests/test_template_delete.py`: super-admin happy path (204, empty body, record gone, fields cascaded, original file gone from disk, subsequent GET 404), processed copy also removed (created via the clean endpoint), owner 403, other-user 403, missing 404, unauthenticated 401, double-delete second call 404.
- Full suite: 106 passed (99 prior + 7 new).

#### Code Changes

- `backend/app/api/v1/endpoints/templates.py` (DELETE route)
- `backend/tests/test_template_delete.py` (new)

#### Features Added / Updated / Removed

- Added: irreversible super-admin template deletion covering both the database record (with cascading fields) and stored DOCX files.

#### Issues Fixed

- None.

#### Notes For Next Push

- Frontend follow-up (separate PR into `frontend`): super-admin-only Delete button on the template detail page behind a type-"confirm" dialog; `templatesApi.deleteTemplate` must handle the 204 empty body.
- Deletion order is deliberate: DB first, files second — orphan files are harmless, a row pointing at deleted files is not.


---

### Checkpoint 0029

- Date: 2026-09-06
- Member: Member 3 (AI)
- Branch: `feature/field-editor-data-layer`
- Push status: before push
- Range covered: after Checkpoint 0027 -> 2026-09-06
- Note: Checkpoint 0028 (frontend deletion UI) lives on the `frontend` branch and is not merged into `backend` yet; numbering follows the global sequence.

#### Summary

- Implemented the V1.3 Phase 3 field-editor data layer: upsert/reorder/sync schemas, single-field CRUD with reindexing, a transactional bulk full-sync, and the optional `field_type` DB CHECK constraint, plus comprehensive tests proving the integrity invariants.

#### Completed Tasks

- Added `TemplateFieldUpsert` (id present -> update, absent -> create), `FieldReorderRequest` (min 1 id), and `FieldSyncRequest` (full-sync list + `mark_configured` default true) schemas, with `field_name` regex (`^[a-z][a-z0-9_]*$`), `field_type`/`source` membership validators importing from the model for one source of truth.
- Hardened `TemplateFieldUpdate` with the same `field_name`/`field_type`/`source` validators so PATCH payloads are rejected at the schema layer before reaching the ORM.
- Added CRUD: `get_field_by_id`, `create_field` (auto `next_display_order`, duplicate pre-check), `update_field` (partial via `exclude_unset`, rename-collision pre-check, reindex when `display_order` is touched), `delete_field` (delete + flush + `_reindex` to contiguous 0..n-1), `reorder_fields` (permutation guard raising `ValueError`), and `sync_fields` (single-commit/rollback: deletes absent fields first + flush so a create can reuse a freed key, updates kept fields in payload order, creates new fields, `display_order` = array index with client values ignored, created fields default `source="manual"`).
- Added `_reindex` helper (renumber by current `(display_order, id)`; callers own the commit) and registered all new functions in `app/crud/__init__.py`.
- Added additive migration `b9e5d2c8a740_add_field_type_check`: `ck_template_field_type` CHECK via `op.batch_alter_table` (cross-dialect; same pattern as `7c4e9a1b2d58`), chained off `3f8d2c6a9e41`; verified single head and clean upgrade/downgrade/re-upgrade cycles on a scratch SQLite DB.
- Created `tests/test_field_editor.py` (25 tests): schema validation, CRUD units (create/duplicate/partial-update/rename/delete-reindex/reorder-permutation), sync (mixed payload with index-based ordering and ignored client `display_order`, empty-clears, duplicate-in-payload `ValueError`, foreign-template-id `ValueError`, cross-item rename collision `IntegrityError` with full rollback and no partial writes), ORM type rejection, CHECK enforcement + reversibility via the alembic subprocess pattern, and an API round-trip asserting `GET /templates/{id}/fields` reflects CRUD edits in order.
- Full suite: 131 passed (106 prior + 25 new).

#### Code Changes

- `backend/app/schemas/template_field.py` (Phase 3 upsert/reorder/sync schemas + `TemplateFieldUpdate` validators)
- `backend/app/crud/template_field_crud.py` (create/update/delete/reorder/sync/get_by_id + `_reindex`)
- `backend/app/crud/__init__.py` (registration)
- `backend/alembic/versions/b9e5d2c8a740_add_field_type_check.py` (new)
- `backend/tests/test_field_editor.py` (new)

#### Features Added / Updated / Removed

- Added: field-editor CRUD with strict unique-key / valid-type / contiguous-display_order invariants after every operation.
- Added: transactional full-sync (`sync_fields`) with all-or-nothing semantics and array-index ordering.
- Added: `ck_template_field_type` DB CHECK constraint (defense in depth below the ORM `@validates`).
- Updated: `TemplateFieldUpdate` now validates key/type/source at the schema layer.
- Removed: none.

#### Issues Fixed

- Found during testing: SQLite reuses a freed rowid for newly created rows, so "deleted field id no longer resolves" is not a valid assertion; tests assert deletion by field_name instead (no product-code change needed).

#### Notes For Next Push

- Member 2 (V1.3 Phase 3) can now wire the endpoints: `create_field` (POST), `update_field` (PATCH), `delete_field` (DELETE), `reorder_fields` (PUT/PATCH with `FieldReorderRequest`), `sync_fields` (PUT with `FieldSyncRequest`); map `ValueError` -> 422 and rename-collision `IntegrityError` -> 409/422.
- Confirmed full-sync delete semantics: fields absent from the sync payload ARE deleted; `sync_fields` itself reindexes (array index), and `delete_field` reindexes internally after a single delete — the endpoint layer never reindexes.
- `FieldSyncRequest.mark_configured` is the endpoint's concern: call `advance_status(db, template, "field_configured")` after a successful sync (never downgrades).
- Fields created through the editor default to `source="manual"` for the Phase 4 audit trail; updates only change `source` when explicitly sent.
- Deploy note: `alembic upgrade head` on Neon applies `b9e5d2c8a740` (additive CHECK; safe — all existing rows pass the ORM validator).

---

### Checkpoint 0030

- Date: 2026-09-09
- Member: Member 2 (AI)
- Branch: `feature/field-editor-endpoints` (created from `backend`; Member 3's data layer landed there via PR #75)
- Push status: before push
- Range covered: after Checkpoint 0029 -> 2026-09-09

#### Summary

- Implemented the V1.3 Phase 3 Member 2 slice: the field-editor endpoints. Five owner-only write routes over Member 3's CRUD with lock enforcement, integrity error mapping (409/422), contiguous `display_order` after every operation, and the transactional bulk full-sync that advances the template to `field_configured` — plus 27 API tests proving the contract.

#### Completed Tasks

- Added `_require_owner_editable(db, template_id, current_user)` guard shared by every field-write route: 404 missing template, 403 non-owner, 403 locked (`Template is locked and cannot be edited`).
- `POST /{template_id}/fields` — create one field (201). 409 duplicate `field_name` (pre-check + `IntegrityError` backstop); 422 invalid `field_type` (CRUD/`@validates` `ValueError` mapped cleanly); `display_order` defaults to append position, explicit values honored then the set renumbered contiguous 0..n-1.
- `PUT /{template_id}/fields/reorder` — validates `ordered_ids` is a permutation of the template's current field ids (else 422); returns the fresh ordered set. Route declared BEFORE the parameterized `/{template_id}/fields/{field_id}` so "reorder" is never captured as a field id; `/library` stays first.
- `PATCH /{template_id}/fields/{field_id}` — partial update (`exclude_unset` semantics via `TemplateFieldUpdate`); 404 missing field or field belonging to another template; 409 rename collision; 422 invalid type.
- `DELETE /{template_id}/fields/{field_id}` — 204; reindex-after-delete lives inside Member 3's `delete_field` (as agreed in Checkpoint 0029).
- `PUT /{template_id}/fields` — BULK SYNC (full-save): duplicate `field_name` in payload -> 422; id from another template -> 422; existing fields ABSENT from the payload are DELETED (full-sync semantics, documented in the route docstring/OpenAPI); `display_order` = array position; all-or-nothing via `sync_fields` rollback; cross-item rename collision `IntegrityError` -> 409 with nothing written; `mark_configured` (default true) with >=1 field -> `advance_status(db, template, "field_configured")` (forward-only — `active` is never downgraded); returns the fresh ordered `list[TemplateFieldRead]`.
- Logging with counts on create/update/delete/reorder/sync.
- Created `tests/test_field_editor_api.py` (27 tests): ordering + contiguity after every op, 404/403/409/422 mapping per route, locked-template rejection on all five writes, mixed full-sync payload (create/update/delete-by-omission), empty-payload clears without status advance, `mark_configured=false` keeps status, `active` never downgraded, stranger reads public template fields but cannot write them.
- Full suite: 158 passed (131 prior + 27 new).
- Repo hygiene: removed stray Windows `nul` artifact at repo root and added it to `.gitignore`.

#### Code Changes

- `backend/app/api/v1/endpoints/templates.py` (+282 lines: 5 field-write routes + `_require_owner_editable`, `_field_value_error`, `_ensure_contiguous_order` helpers; imports for Member 3 CRUD/schemas)
- `backend/tests/test_field_editor_api.py` (new, 27 tests)
- `.gitignore` (+ Windows `nul` artifact guard; verified all other backend/frontend artifacts — storage, `*.db`, `.venv`, caches, node_modules, dist, tsbuildinfo — already covered)
- `project-change-tracker.md` (this checkpoint)

#### Features Added / Updated / Removed

- Added: owner-only field CRUD endpoints — `POST /{id}/fields`, `PATCH /{id}/fields/{field_id}`, `DELETE /{id}/fields/{field_id}`.
- Added: explicit reorder — `PUT /{id}/fields/reorder`.
- Added: bulk full-sync save — `PUT /{id}/fields` with full-delete semantics and status advance to `field_configured`.
- Added: template lock enforcement (403) on every field write.
- Updated: `.gitignore` (Windows `nul` guard).
- Removed: none.

#### Issues Fixed

- Removed stray `nul` file at repo root (Windows `2>nul` redirect artifact) so it cannot be committed; gitignored to prevent recurrence.

#### Notes For Next Push

- Member 1 (frontend) can now build the field editor UI against these endpoints. Full-sync semantics: `PUT /fields` must send the COMPLETE field list — fields absent from the payload are deleted; the response is the fresh ordered set; the template status becomes `field_configured` on save (when >=1 field and `mark_configured` not disabled).
- PR target for `feature/field-editor-endpoints` is `backend` (backend-only change + directly related docs/config).
- Route ordering matters if routes are ever reordered: `/{template_id}/fields/reorder` must stay declared before `/{template_id}/fields/{field_id}`, and `/library` before `/{template_id}`.
- Phase 4 (AI field suggestions) must NOT be added to these routes (spec DO NOT); keep writes owner-only and never store DOCX bytes in the DB.

---

### Checkpoint 0031

- Date: 2026-09-10
- Member: Member 1 (AI)
- Branch: `feature/field-editor-ui` (created from `frontend`, which carries the Phase 3 backend via PR #79)
- Push status: before push
- Range covered: after Checkpoint 0030 -> 2026-09-10

#### Summary

- Implemented the V1.3 Phase 3 Member 1 slice: the Field Metadata Editor UI. Replaced the `/templates/:id/fields` placeholder stub with a full owner-only editor — RHF `useFieldArray` + Zod validation mirroring the backend rules, add/delete/reorder per field card, and "Save all" through the bulk sync endpoint (`PUT /{id}/fields`) which reseeds the form and reflects the `field_configured` status.

#### Completed Tasks

- Extended `src/lib/api.ts`: `TemplateFieldUpsert` and `FieldSyncPayload` types plus five methods on `templatesApi` — `createField`, `updateField`, `deleteField`, `reorderFields` (`ordered_ids`), `saveFields` (bulk sync). All follow the existing `request<T>` + explicit-token conventions; the editor page uses `getFields` + `saveFields`.
- Added `src/components/ui/switch.tsx` (shadcn Switch over `@radix-ui/react-switch@^1.3.7`, installed through the npm workspace so the root `package-lock.json` is the one updated — matching repo convention).
- Rebuilt `src/pages/field-setup-page.tsx` from the Phase 3 stub into the full editor:
  - Zod per-field schema: `field_name` regex `^[a-z][a-z0-9_]*$` with the spec's message, type enum over the MVP set, label/section/example/validation max lengths (150/100/255/255), and an array-level `superRefine` that rejects duplicate keys with per-row inline errors.
  - Field cards (slate, responsive, stack on mobile): mono key Input with live `{{key}}` preview, label, type Select, section, example, validation Input with helper examples (`email`, `min:1`), help-text Textarea, Required and AI-enabled Switches (AI hint: "Enable AI for descriptive fields (agenda, summary); disable for facts (date, amount)."), up/down move buttons, and delete behind a confirm Dialog.
  - Toolbar: "Add field" appends a blank row (`is_required=true`, `ai_enabled=false`, type `text`); "Save all" submits `saveFields(id, { fields, mark_configured: true })`, reseeds the form from the response, and shows "Fields saved. Template configured." with the status badge advancing to `field_configured` locally (never downgrading `active`/`field_configured`).
  - Full-sync semantics surfaced: "Saving replaces the field set — removed rows are deleted."
  - Array position IS the submitted order (server `display_order` never rendered as an input); the DB id rides as `rowId` because `useFieldArray` injects its own `id`.
  - States: Skeleton loading, 404/403-aware error view with Retry, non-owner notice + back link, locked-template read-only field list with amber notice, red error banner mapping `ApiError` 403/409/422/401.
  - Reserved the Phase 4 mount point: `<section id="ai-suggestions">` placeholder card.
- Updated `template-detail-page.tsx`: for status `placeholder_detected`, the owner action "Review Fields" now targets `/templates/:id/fields` (was `/placeholders`); `field_configured`/`active` already targeted the editor, and the Phase 1/2 "Continue to Field Setup" buttons already pointed here.
- Verified `npm run build` (`tsc -b && vite build`, strict TS) passes.
- Verified `.gitignore` needs no changes: `frontend/*.tsbuildinfo`, `frontend/dist/`, `frontend/node_modules/` all covered; `vite.config.js`/`.d.ts` are already tracked by team convention.

#### Code Changes

- `frontend/src/lib/api.ts` (+78: 2 types + 5 methods)
- `frontend/src/pages/field-setup-page.tsx` (stub replaced, ~860 lines)
- `frontend/src/components/ui/switch.tsx` (new)
- `frontend/src/pages/template-detail-page.tsx` (1-line route target change)
- `frontend/package.json` + root `package-lock.json` (`@radix-ui/react-switch`)
- `project-change-tracker.md` (this checkpoint)

#### Features Added / Updated / Removed

- Added: Field Setup editor page — owner-only field metadata editing with add/delete(confirm)/reorder(up-down) and bulk "Save all" that advances status to `field_configured`.
- Added: `Switch` UI primitive (reusable for Phase 4).
- Added: `TemplateFieldUpsert`/`FieldSyncPayload` client types + the five field-write API methods.
- Added: Phase 4 AI-suggestions mount point (`<section id="ai-suggestions">`).
- Updated: template detail "Review Fields" action now routes to the field editor.
- Removed: the "Field Setup is coming in Phase 3" placeholder stub.

#### Issues Fixed

- Status badge did not refresh after "Save all" — now advances locally to `field_configured` after a successful sync (forward-only; `active` never downgraded).
- Strict-TS mismatch between zod's inferred literal union for `field_type` and the seeded server strings — fixed with a `FieldTypeValue` type derived from the options const plus an `isFieldType` guard when seeding.

#### Notes For Next Push

- PR target: `feature/field-editor-ui` -> `frontend` (frontend-only change + directly related dependency/lockfile). After review/merge, integrate `frontend` -> `dev` via a merge-commit PR so Phase 3 is complete on the integrated branch.
- Phase 4 can slot the AI suggestions panel into `<section id="ai-suggestions">` without touching the editor; the `Switch` primitive and the `TemplateFieldUpsert` type are the reuse points for accept-suggestion.
- Client validation intentionally mirrors the backend contract (key regex, MVP type set, unique keys, max lengths); server 409/422 remain the backstop and surface through `ApiError.message`.
- The editor intentionally uses only the bulk sync for persistence (spec: "Save all" is the primary write path); `createField`/`updateField`/`deleteField`/`reorderFields` are shipped in the API client for Phase 4+ consumers.

---

### Checkpoint 0032

- Date: 2026-09-12
- Member: Member 3 (AI)
- Branch: `feature/ai-generations-data-layer` (created from `backend`)
- Push status: before push
- Range covered: after Checkpoint 0030 -> 2026-09-12
- Note: Checkpoint 0031 (V1.3 Phase 3 Member 1 field-editor UI) lives on `feature/field-editor-ui` and is not merged into `backend` yet; numbering follows the global sequence.

#### Summary

- Implemented the V1.3 Phase 4 Member 3 data layer: the generic `ai_generations` audit table (model + additive migration), the logging CRUD, the field-suggestion schemas, and the test suite (endpoint tests skip-guarded with the AI provider mocked until Member 2 ships the service/route).

#### Completed Tasks

- Created `app/models/ai_generation.py` (`AiGeneration`): lean audit columns — `action_type`, `model`, `template_id` (FK `templates.id` ON DELETE SET NULL, indexed), `document_id` (plain nullable Integer RESERVED for V1.4 — no FK to a non-existent table), `field_key`, `created_by` (FK `users.id` ON DELETE CASCADE, indexed), `status` (default `"success"`), `suggestions_count`, `detail` (tiny optional note — never prompt/output dumps), `created_at`; custom `__init__` defaults `status` pre-flush (mirrors the `Template` pattern) and `@validates` rejects unknown statuses; registered in `app/models/__init__.py`.
- Added migration `e5f2a8c6d4b7_add_ai_generations_table` chained off `b9e5d2c8a740` (single head): `CURRENT_TIMESTAMP` / `'success'` server defaults (cross-dialect rule), both FKs with the chosen ON DELETE behaviors, indexes `ix_ai_generations_template_id` + `ix_ai_generations_created_by`; verified upgrade/downgrade/re-upgrade clean.
- Created `app/schemas/ai.py`: `FieldSuggestion` (`field_name` regex `^[a-z][a-z0-9_]*$` + `field_type` membership validator importing `FIELD_TYPES` from the model — single source of truth), `FieldSuggestionList` (the `instructor` response_model wrapper), `SuggestFieldsResponse` (endpoint envelope — persists nothing), `AiGenerationRead` (`from_attributes`).
- Created `app/crud/ai_generation_crud.py`: `log_ai_generation` (ONE lean insert per AI call — success AND error paths) and `get_ai_generations_by_template` (newest first: `created_at desc, id desc`, limit); registered in `app/crud/__init__.py`.
- Confirmed the `source="ai"` plumbing: `"ai"` is already an accepted `FIELD_SOURCES` value on `template_fields` (added in Phase 2), so suggestions accepted through the Phase 3 create/sync endpoints are tagged `source="ai"` — proven by tests.
- Tests: `tests/test_ai_generations.py` (CRUD units incl. error rows, status validation, newest-first ordering + limit, FK SET NULL / CASCADE behavior with SQLite FKs enforced via PRAGMA, migration up/down/up with DDL + behavioral verification on the scratch DB) and `tests/test_field_suggestions.py` (schema validation incl. invalid key `"Bad Key"` and invalid type `"dropdown"`, accept path via `POST /{id}/fields` and `PUT /{id}/fields` sets `source="ai"`, default stays `detected`; endpoint tests are skip-guarded until Member 2 ships `ai_service` + the suggest-fields route, then activate automatically with the provider monkeypatched).
- Full suite: 176 passed, 2 skipped (the two guarded suggest-endpoint tests).

#### Code Changes

- `backend/app/models/ai_generation.py` (new) + `backend/app/models/__init__.py` (import)
- `backend/alembic/versions/e5f2a8c6d4b7_add_ai_generations_table.py` (new)
- `backend/app/schemas/ai.py` (new)
- `backend/app/crud/ai_generation_crud.py` (new) + `backend/app/crud/__init__.py` (register)
- `backend/tests/test_ai_generations.py`, `backend/tests/test_field_suggestions.py` (new)
- `backend/tests/test_field_editor.py` (downgrade-target fix, test-only)

#### Features Added / Updated / Removed

- Added: generic `ai_generations` audit table (forward-compatible for every future AI feature — grammar, tone, rewrite, MoM — not just suggestions), logging + newest-first read CRUD, `FieldSuggestion`/`FieldSuggestionList`/`SuggestFieldsResponse`/`AiGenerationRead` schemas.
- Updated: `test_field_editor.py` migration test now downgrades to `3f8d2c6a9e41` explicitly (later revisions chain on top of `b9e5d2c8a740`, so `downgrade -1` no longer targets it).
- Removed: none.

#### Issues Fixed

- None (product code); the field-editor migration-test downgrade target was a test-only correction caused by this slice chaining a new revision.

#### Notes For Next Push

- Member 2 (V1.3 Phase 4) builds `app/services/ai_service.py` + `POST /api/v1/templates/{id}/suggest-fields` against the locked contract: `log_ai_generation(db, *, action_type, model, template_id=None, created_by, field_key=None, status="success", suggestions_count=None, detail=None)` plus the schemas in `app/schemas/ai.py` — this matches the member-specific Phase 4 prompts; the older phase-wide prompt's `create_ai_log` naming is superseded, do not code against it.
- The 2 skipped endpoint tests in `test_field_suggestions.py` activate automatically once the route + `ai_service` exist (they monkeypatch the provider — never real Bedrock).
- Backend verification result: `pytest tests` -> 176 passed, 2 skipped.
- Deploy note: `alembic upgrade head` on Neon applies `e5f2a8c6d4b7` (new table; additive and safe).
- PR target for `feature/ai-generations-data-layer` is `backend` (backend-only change + directly related docs).

---

### Checkpoint 0033

- Date: 2026-09-13
- Member: Member 2 (AI)
- Branch: `feature/ai-field-suggestions` (created from `backend` after `feature/ai-generations-data-layer` merged via PR #82)
- Push status: before push
- Range covered: after Checkpoint 0032 -> 2026-09-13

#### Summary

- Implemented the V1.3 Phase 4 Member 2 slice: the first TemplateOS AI feature — validated field suggestions from Claude Sonnet on AWS Bedrock (Anthropic SDK + `instructor`) via the new `ai_service` and the owner-only, non-persisting `POST /templates/{id}/suggest-fields` endpoint, logged to `ai_generations` on every attempt.

#### Completed Tasks

- Added pinned AI-only dependencies to `backend/requirements.txt`: `anthropic[bedrock]==1.5.0` (pulls boto3) + `instructor==1.17.0`, with a comment noting the app boots and all non-AI features work without them (lazy imports).
- Extended `Settings` (`backend/app/core/config.py`): `AWS_REGION` (default `None` -> AI stays off), `BEDROCK_MODEL_SUGGESTIONS` (default `anthropic.claude-3-5-sonnet-20241022-v2:0` — inference-profile id to be confirmed in the team's AWS account), `AI_MAX_OUTPUT_TOKENS` (default 1024), and the `ai_is_configured` property (region set AND credentials resolvable via env vars or the boto3 default chain; network-free, never raises).
- Created `backend/app/services/ai_service.py`: `AiUnavailableError`; `_build_client()` imports `instructor`/`AnthropicBedrock` lazily so importing the module never breaks app boot or non-AI tests, and funnels every failure (missing deps/region/creds, SDK construction) into `AiUnavailableError`; `suggest_fields(document_text, existing_keys)` sends a concise system+user prompt (existing keys listed, document text truncated to 6000 chars) with `response_model=FieldSuggestionList` (instructor-validated — no hand-parsed JSON), then post-filters against Phase 1's `VALID_KEY_PATTERN` and dedupes vs existing keys; any provider error -> `AiUnavailableError`.
- Added `POST /api/v1/templates/{template_id}/suggest-fields` to `backend/app/api/v1/endpoints/templates.py`: owner-only (403 otherwise), 404 missing template, 409 no/missing source file; document text via `docx_parser.extract_text_segments` and existing keys via `template_field_crud.get_fields_by_template`, all blocking work in `asyncio.to_thread`; exactly ONE `log_ai_generation` row per call on success AND error paths (status `error`, `suggestions_count=0`, lean `detail` on failure); `AiUnavailableError` -> 503 with a clear message; persists NOTHING to `template_fields` (manual confirmation — accepted suggestions are written only through the Phase 3 endpoints with `source="ai"`).
- Documented the new AI env vars in `.env.example` (commented-out `AWS_REGION`, `BEDROCK_MODEL_SUGGESTIONS`, `AI_MAX_OUTPUT_TOKENS` + Bedrock credential guidance: env keys or boto3 default chain, never exposed to the frontend).
- Full suite: `pytest tests` -> 178 passed, 0 skipped — the two previously skip-guarded endpoint tests from checkpoint 0032 now run (AI provider monkeypatched; never real Bedrock in CI).

#### Code Changes

- `backend/requirements.txt` (AI deps + comment)
- `backend/app/core/config.py` (AI settings + `ai_is_configured`; cosmetic reflow of two existing field definitions only)
- `backend/app/services/ai_service.py` (new)
- `backend/app/api/v1/endpoints/templates.py` (suggest-fields endpoint + imports)
- `.env.example` (AI section)

#### Features Added / Updated / Removed

- Added: first AI feature — `ai_service.suggest_fields` (Bedrock Claude Sonnet via `instructor`, validated structured output, model routing via `BEDROCK_MODEL_SUGGESTIONS`); owner-only `POST /templates/{id}/suggest-fields` returning `SuggestFieldsResponse` (proposals only); `AiUnavailableError` -> 503 graceful-degradation contract; `ai_is_configured` config check.
- Updated: `.env.example` documents the AI configuration; `requirements.txt` gained the AI-only dependency block.
- Removed: none.

#### Issues Fixed

- None.

#### Notes For Next Push

- Confirm the exact Bedrock model id / cross-region inference profile available in the team's AWS account + region (and enable model access there); override `BEDROCK_MODEL_SUGGESTIONS` / `AWS_REGION` env vars if the default id is not available.
- AI is off by default: no `AWS_REGION` -> suggest-fields returns 503 "not configured"; deploys need no AWS setup unless the feature is enabled. With creds set, a manual smoke test of the endpoint against real Bedrock is still outstanding (tests mock the provider by design).
- Member 1 can now wire the "Suggest fields with AI" UI to `POST /api/v1/templates/{id}/suggest-fields`; accepted suggestions flow through the Phase 3 create/sync endpoints with `source="ai"`.
- No migration needed this slice (`ai_generations` shipped in checkpoint 0032, PR #82).
- PR target for `feature/ai-field-suggestions` is `backend` (backend-only change + directly related docs/config).
- Future AI features (grammar, tone, rewrite, MoM) should reuse the same `ai_service` pattern (lazy imports, `AiUnavailableError`, lean `ai_generations` logging).

---

### Checkpoint 0034

- Date: 2026-09-13
- Member: Member 1 (AI)
- Branch: `feature/ai-suggestions-panel` (created from `frontend`)
- Push status: before push
- Range covered: after Checkpoint 0031 -> 2026-09-13
- Note: Checkpoints 0032 (ai_generations data layer) and 0033 (Bedrock suggest-fields backend) were merged into `backend` via PRs #82/#83 and are not on `frontend` yet; they arrive with the next `dev` sync. Numbering follows the global sequence.

#### Summary

- Implemented the V1.3 Phase 4 Member 1 slice: the AI Suggestions panel inside the Field Setup page. The owner can request AI field suggestions, review each proposal with its reason, and Accept/Dismiss — accepted rows are staged into the Phase 3 editor (tagged) and persisted only by the existing "Save all" bulk sync. A 503 (AI unavailable) shows a calm notice without touching the manual editor.

#### Completed Tasks

- Extended `src/lib/api.ts`: `FieldSuggestion` and `SuggestFieldsResponse` types (matching the backend Phase 4 schemas, incl. `reason`) + `templatesApi.suggestFields(token, id)` calling `POST /templates/{id}/suggest-fields` via the existing `request<T>` helper — the only AI call, never Bedrock from the browser.
- Created `src/components/fields/AiSuggestionsPanel.tsx`:
  - Card with Sparkles header and a primary "Suggest fields with AI" button; indigo/violet accent on the slate palette, responsive.
  - States: idle (button + in-control description), loading (3 Skeleton rows, disabled button, "Thinking…"), success, error; "Suggest again" re-runs the request.
  - Each proposal row: mono `{{key}}`, label, type/section/required badges, muted example value, italic "Why: …" reason, and Accept/Dismiss buttons.
  - Accept calls `onAccept` (parent stages it), marks the key accepted, removes the row; Dismiss removes the row only. Accept is disabled with "Already added" when the key exists in the editor's live field keys or was already accepted — no double accepts.
  - Empty result: "No additional fields suggested — your field set looks complete."
  - Error handling: `ApiError.status === 503` -> calm amber notice "AI suggestions aren't available right now (the AI service isn't configured). You can keep configuring fields manually."; other errors -> red banner with the message. The manual editor is never blocked.
  - All state local to the panel except accepts, which flow up via `onAccept`; token read from `localStorage("templateos_access_token")` per convention.
- Wired the panel into `src/pages/field-setup-page.tsx` at the reserved mount point — new two-column layout (`lg:grid-cols-[minmax(0,1fr)_360px]`): editor left, panel as a sticky `<aside id="ai-suggestions">` right on desktop, stacked below on mobile. Owner-only is inherited from the page's owner gate; the locked read-only view returns before the panel renders.
- `onAccept` stages the suggestion into the `useFieldArray` as a new `TemplateFieldUpsert` (no rowId): key, label, type (guarded by `isFieldType`), required, `ai_enabled: true` (AI-suggested descriptive fields default on; owner can toggle), `description` = the AI reason, example, section. Staged rows get a subtle indigo ring + "AI suggestion" Badge until saved; removing a staged row clears its highlight.
- Live duplicate guard: `existingKeys` derives from `useWatch` over the field array (renames count), not the static `fields` snapshot.
- No second persistence path: staged rows save via the existing "Save all" (`saveFields`); on success the form reseeds and the staged-key highlights clear. Helper text after accepting: "N suggestion(s) accepted — added to the field editor. Click Save all to keep them."
- Verified `npm run build` (`tsc -b && vite build`, strict TS) passes; no new dependencies (reused Card/Badge/Button/Skeleton + lucide icons).

#### Code Changes

- `frontend/src/lib/api.ts` (+31: 2 types + 1 method)
- `frontend/src/components/fields/AiSuggestionsPanel.tsx` (new, ~270 lines)
- `frontend/src/pages/field-setup-page.tsx` (panel wiring, grid layout, accept handler, staged-row highlight; removed the dashed placeholder)
- `project-change-tracker.md` (this checkpoint)

#### Features Added / Updated / Removed

- Added: AI Suggestions panel — owner-triggered `POST /{id}/suggest-fields` with loading/empty/error states, per-proposal Accept/Dismiss, duplicate-accept guard, and the 503 calm-degradation notice.
- Added: `FieldSuggestion`/`SuggestFieldsResponse` client types + `suggestFields` API method.
- Updated: Field Setup page layout — two-column desktop grid with the panel as a sticky aside (mount point `#ai-suggestions` preserved); accepted AI rows highlighted (indigo ring + badge) until saved.
- Removed: the "AI suggestions arrive here in the next phase" dashed placeholder card.

#### Issues Fixed

- None.

#### Notes For Next Push

- PR target: `feature/ai-suggestions-panel` -> `frontend` (frontend-only change). The live endpoint is already merged into `backend` (PR #83) — to test end-to-end, run the backend from `backend` with `AWS_REGION` set (otherwise the panel correctly shows the calm 503 notice).
- After merge, integrate `frontend` -> `dev` (merge-commit PR) so Phase 4 is complete on the integrated branch; `backend` -> `dev` is still pending too (checkpoints 0032/0033).
- The panel is the reuse template for future AI features (grammar/tone/rewrite): local state + `onAccept`-style flow-up, 503 calm notice, no auto-apply.

---

### Checkpoint 0035

- Date: 2026-09-13
- Member: Member 2 (AI)
- Branch: `feature/bedrock-diagnostics` (created from `backend`, which is identical to `dev` after sync PRs #88/#89)
- Push status: before push
- Range covered: after Checkpoint 0034 -> 2026-09-13
- Note: covers work done on the `dev` working tree (config edits + diagnostics) moved onto a backend-scoped task branch. Integrations of checkpoints 0032-0034 into `dev` happened via PRs #85-#89.

#### Summary

- Added Bedrock/AI operational diagnostics: a standalone `scripts/verify_bedrock.py` (config-only + `--live` real-call verification) and WHY/WHERE-classified failure logging inside `ai_service.py`, so any AWS/Bedrock failure reports exactly what broke and how to fix it — in the uvicorn console, the 503 detail, and the `ai_generations` error row. Plus `.env.example` (V1.3 P4 AI section rewrite) and `.gitignore` (graphify output) updates done post-0034.

#### Completed Tasks

- Rewrote the AI section of `.env.example` per V1.3 P4: documents `AWS_REGION` (region + on/off semantics — unset keeps AI off, matching `ai_is_configured`), `BEDROCK_MODEL_SUGGESTIONS` (with the cross-region inference-profile id caveat + console model-access step), `AI_MAX_OUTPUT_TOKENS`, and credentials (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/optional `AWS_SESSION_TOKEN`, or boto3 default chain) with the backend-only rule. Documents the names the shipped code actually reads (the P4 prompt's `BEDROCK_ENABLED`/`BEDROCK_MODEL_SONNET`/etc. were consolidated in checkpoint 0033).
- Added `graphify-out/` to `.gitignore` (generated knowledge-graph output, regenerable via the graphify tool).
- `backend/app/services/ai_service.py` diagnostics upgrade:
  - New `_config_problem()`: returns a human-readable description of the FIRST missing config piece (region unset / no env creds / no profile creds / chain check failed) or None; shared by the 503 path and the verify script.
  - New `_classify_ai_error()`: maps provider/SDK exceptions to WHY text by exception name/HTTP status (no SDK imports — module stays import-safe without AI deps): 400 malformed model id (shows current value + inference-profile format), 401 invalid/expired keys, 403 IAM lacks `bedrock:InvokeModel` or console model access off, 404 model not found/access not enabled, 429 throttled, 5xx AWS-side, timeout/connection network egress hint, `InstructorRetryException` schema-validation, credential-chain errors, generic fallback.
  - `_build_client()` and `suggest_fields()` failures now log `[ai] ... — WHERE: <stage> — WHY: <cause+fix>` at ERROR (visible in the uvicorn console like normal request logs) with the full traceback at DEBUG; the same reason text flows into the `AiUnavailableError` message -> 503 `detail` -> `ai_generations` `detail` column. Previously failures logged a bare exception with no cause classification.
- Created `backend/scripts/verify_bedrock.py` (mirrors `test_db_connection.py`'s standalone-script convention): 4-stage check — settings (prints the actual AI values), dependencies (anthropic/instructor/boto3 versions), credential chain (reports WHICH chain resolved: env vars vs shared profile vs instance role), and `--live` for one tiny REAL Bedrock probe call (the only way to verify IAM permission + console model access end-to-end); prints latency + returned proposals. Exit code 0/1; failures print the same WHY text the API server logs on 503. No database involved.
- Verified: `pytest tests` -> 178 passed (endpoint tests unaffected — they mock at the module boundary); ran the script config-only against the current (unconfigured) state — correctly reports "AI is intentionally OFF" + the one missing piece; demoed the ERROR log line + 503 detail for the unset-region case.

#### Code Changes

- `backend/app/services/ai_service.py` (+~110: `_config_problem`, `_classify_ai_error`, staged logging; `settings.ai_is_configured` call replaced by `_config_problem`)
- `backend/scripts/verify_bedrock.py` (new, ~185 lines)
- `.env.example` (AI section rewrite, ~2x comments)
- `.gitignore` (+2: graphify-out entry)
- `project-change-tracker.md` (this checkpoint)

#### Features Added / Updated / Removed

- Added: `scripts/verify_bedrock.py` — pre-flight Bedrock verification (config-only default; `--live` real-call mode validating IAM + model access).
- Added: WHY/WHERE failure classification — every AI failure names its stage and a fix hint across console log, 503 detail, and audit row.
- Updated: `.env.example` AI section now fully documents the V1.3 P4 contract (toggle semantics, model-id caveat, credential chain).
- Updated: `.gitignore` ignores `graphify-out/`.
- Removed: none.

#### Issues Fixed

- 503 responses and logs previously said only "AI is not configured (missing AWS region or credentials)" / bare exception text — no indication of WHICH piece was missing or WHY a call failed. Now each failure names the exact missing config piece or the classified AWS-side cause with a fix hint.

#### Notes For Next Push

- PR target: `feature/bedrock-diagnostics` -> `backend` (backend change + directly related config/docs). After merge, a routine `backend` -> `dev` integration PR will carry it to `dev`; `frontend` needs no sync for this (no frontend files touched).
- The Bedrock model id default (`anthropic.claude-3-5-sonnet-20241022-v2:0` in code) is still a guess — the team MUST confirm the id in their AWS account (Bedrock console -> Model access) and set `BEDROCK_MODEL_SUGGESTIONS` + `AWS_REGION` in `.env`; then run `python scripts/verify_bedrock.py --live` from `backend/` for the end-to-end smoke test (checkpoint 0033's outstanding item).
- `settings.ai_is_configured` in `config.py` is now only used by tests/`verify` indirectly via `_config_problem` (same logic, richer output); leave it as the public property.
- Live smoke test against real Bedrock remains outstanding until AWS creds exist (by design — tests never hit AWS).
- `.env.example`/`.gitignore` ride along in this branch (repo-root config, backend-scoped change per the change-scope table).

---

## Entry Template

```md
### Checkpoint 000X

- Date: YYYY-MM-DD
- Member: Name
- Branch: branch-name
- Push status: before push
- Range covered: after Checkpoint 000(previous) -> current update date

#### Summary

- Short overall summary of what changed.

#### Completed Tasks

- Task 1
- Task 2

#### Code Changes

- Affected area/files/modules

#### Features Added / Updated / Removed

- Added:
- Updated:
- Removed:

#### Issues Fixed

- Bug fix or `None`

#### Notes For Next Push

- Optional handoff notes or `None`
```

