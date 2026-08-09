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

## Entry Template

Copy this template for each future update and place it below the latest checkpoint.

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

