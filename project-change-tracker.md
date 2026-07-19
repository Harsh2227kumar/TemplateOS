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
