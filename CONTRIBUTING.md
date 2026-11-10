# Contributing to TemplateOS

This repository follows a simple GitHub workflow so `main` stays stable and the team can collaborate safely.

## Core Rule

Never work directly on `main`. Create a branch, push that branch, and merge changes through a pull request.

Never commit or push directly to any permanent branch. All changes must go through a reviewed pull request (PR).

## Branch Architecture

TemplateOS uses four permanent branches:

| Branch | Purpose | Accepts PRs from | Merges into |
| --- | --- | --- | --- |
| `main` | Production-ready, deployed code | `dev` and urgent `hotfix/*` branches | Deployment |
| `dev` | Fully integrated, working project for the next release | `frontend`, `backend`, and cross-stack task branches | `main` |
| `frontend` | Integration branch for frontend-only changes | Short-lived frontend branches | `dev` |
| `backend` | Integration branch for backend-only changes | Short-lived backend branches | `dev` |

Git branches are snapshots of the entire repository. Therefore, `frontend` and `backend` retain the complete project; their names describe the changes allowed into them. Do not delete `backend/` from `frontend` or `frontend/` from `backend`.

```text
frontend task --PR--> frontend --PR--\
                                      +--> dev --release PR--> main --> deploy
backend task  --PR--> backend  --PR--/

cross-stack task --------PR----------> dev
```

### Permanent branch responsibilities

- **`main`:** Must always be production-ready. It receives reviewed releases from `dev` and urgent production fixes. Tag successful releases, for example `v1.2.0`.
- **`dev`:** Contains the working integrated frontend and backend. It receives domain integrations and cross-stack work, and is the release source.
- **`frontend`:** Receives work limited to `frontend/` plus directly related documentation or configuration. It must not receive backend implementation changes.
- **`backend`:** Receives work limited to `backend/` plus directly related documentation or configuration. It must not receive frontend implementation changes.

## Choosing the Correct Base Branch

| Change scope | Create the branch from | Open the PR into |
| --- | --- | --- |
| Frontend only | `frontend` | `frontend` |
| Backend only | `backend` | `backend` |
| Frontend and backend | `dev` | `dev` |
| Repository-wide docs, CI, or shared tooling | `dev` | `dev` |
| Urgent production fix | `main` | `main` |

If a frontend or backend task becomes cross-stack, do not quietly add the extra scope. Split the work and create the cross-stack portion from the latest `dev`.

## Branch Size and Lifetime

Keep task branches short-lived—ideally hours or a few days. There is no strict line limit, but a PR near 400 changed lines or touching unrelated files should usually be split. Generated files and lockfiles are exceptions.

Do not create merge branches by default. Use a temporary `integration/<topic>` branch only when dependent branches must be tested together before they can independently merge. Delete it afterward.

## Repository Rules

- Keep `main` stable, clean, and runnable.
- Merge only reviewed and tested changes into permanent branches.
- Do not commit secrets, `.env` files, generated files, or local storage data.
- Keep documentation updated when behavior or setup changes.
- Keep each branch and pull request focused on one feature, fix, or task.

## Branch Rules

Use clear branch names:

- `feature/auth-login`
- `feature/template-upload`
- `fix/pdf-conversion-error`
- `refactor/storage-service`
- `docs/mvp-notes`
- `chore/project-setup`

Preferred branch prefixes:

- `feature/` for new features
- `fix/` for bug fixes
- `refactor/` for code cleanup without intended behavior change
- `docs/` for documentation work
- `chore/` for tooling, config, or maintenance
- `test/` for test-only changes
- `hotfix/` for urgent production fixes
- `release/` for optional release preparation
- `integration/` for rare, temporary multi-branch testing

## Starting and Updating Work

Update the correct base before creating a task branch. For frontend work:

```bash
git switch frontend
git pull --ff-only origin frontend
git switch -c feature/frontend-short-description
```

Use `backend` for backend-only work and `dev` for cross-stack work. The `--ff-only` option prevents accidental merge commits while pulling permanent branches.

Before final review, update from the actual PR base:

```bash
git fetch origin
git switch feature/your-branch
git rebase origin/frontend
```

Replace `frontend` with `backend`, `dev`, or `main` as appropriate. If other people share the task branch, merge the base instead of rebasing shared history. After rebasing an already-pushed task branch, use `git push --force-with-lease`.

- Commit or stash local work before switching or pulling.
- Never force-push a permanent branch.
- Resolve conflicts locally, inspect both sides carefully, and rerun relevant checks.

## Push Rules

- Before every push, inspect the current branch and the complete change scope. Decide explicitly whether the changes belong on the current task branch, belong on another existing task branch, or require a new short-lived branch such as `feature/*`, `fix/*`, `refactor/*`, `docs/*`, `test/*`, or `chore/*`.
- Do not push merely because the changes are already present on the current branch. If the branch purpose and change scope do not match, move the work safely to the correct branch before committing or pushing.
- If the current branch is permanent (`main`, `dev`, `frontend`, or `backend`), create the correct short-lived branch from the appropriate base before committing or pushing the change.
- Before pushing, verify the decision with `git branch --show-current`, `git status`, and `git diff` (or `git diff --staged` for staged changes).
- Push only your working branch; never push directly to `main`, `dev`, `frontend`, or `backend`.
- Push small, meaningful commits instead of one very large commit.
- Use clear commit messages.

Good commit message examples:

- `feat(backend): add JWT login API`
- `fix(backend): handle invalid DOCX upload`
- `refactor: move file logic into storage service`
- `docs: update MVP scope notes`

## Feature Rules

- One branch should represent one focused task or feature.
- Follow the agreed roadmap, especially the V1 scope.
- Do not mix unrelated changes in the same branch.
- If a change affects frontend, backend, and database but belongs to one feature, it may stay in one pull request.
- If the work becomes too large to review safely, split it into smaller pull requests.

For this project, avoid adding V2 or V3 features into V1 work unless the team explicitly agrees.

## Pull Request Rules

Every pull request should include:

- What changed
- Why it changed
- Testing that was done
- Any database, API, storage, or auth impact
- Any known limitation or follow-up work

Good pull request title examples:

- `feat(frontend): add template upload flow`
- `feat(backend): implement placeholder detection service`
- `fix(backend): handle generated PDF status`

Each pull request description should answer:

- What problem does this solve?
- What modules or areas are affected?
- How can teammates test it?
- Are there breaking changes?

## Review Rules

- At least one teammate should review before merge.
- Reviewers should check logic, scope, naming, and regression risk.
- Resolve review comments before merging.
- Do not self-merge immediately unless the team has already agreed that the change is urgent or trivial.

## Merge Rules

- Merge only after review and basic testing are complete.
- Do not merge with unresolved conflicts.
- Use `Squash and merge` for short-lived task PRs.
- Use a regular PR merge commit between permanent branches to preserve ancestry.
- Delete a short-lived branch after merge; never delete a permanent branch.

Do not use `Rebase and merge`. Regular merge commits are reserved for approved permanent-to-permanent integration and release PRs.

## Conflict Rules

- The branch owner resolves conflicts.
- After resolving conflicts, run the relevant checks and retest the affected flow.
- Do not guess during conflict resolution. Read both sides carefully.

## GitHub Branch Protection

Configure rulesets for `main`, `dev`, `frontend`, and `backend`:

- Require a pull request and at least one approval.
- Dismiss stale approvals when new commits are pushed.
- Require conversation resolution and relevant passing checks.
- Block force pushes and branch deletion.
- Restrict direct pushes, including for administrators when practical.

For `main`, also require release or deployment checks and accept PRs by team policy only from `dev` or urgent `hotfix/*` branches.

Recommended repository settings:

- Enable automatic deletion of merged short-lived branches.
- Enable squash merging; allow merge commits only for permanent-to-permanent PRs.
- Add a `CODEOWNERS` file when module ownership is established.
- Add a pull request template matching this guide.

## Integration and Release Flow

### Frontend and backend integration

1. Open a PR from `frontend` or `backend` into `dev`.
2. Test the complete application, not only that domain.
3. Merge the approved PR with a merge commit so Git preserves permanent-branch ancestry.
4. When shared or cross-stack changes affect domain work, sync the latest `dev` back into `frontend` and/or `backend` through a PR.

Integrate frequently. Long-lived domain branches that drift far from `dev` create difficult conflicts.

### Production release

1. Confirm `dev` is stable and planned work is integrated.
2. Open a release PR from `dev` into `main`.
3. Run the complete CI suite and final acceptance tests.
4. Obtain approval and merge with a merge commit so `dev` remains an ancestor of `main`.
5. Deploy `main` and verify production.
6. Create a version tag or GitHub release when appropriate.
7. Synchronize permanent branches if release-only changes were made.

Do not add unrelated features while a release PR is under review.

## Hotfix Flow

Use `hotfix/*` only for an urgent production problem:

1. Create `hotfix/short-description` from the latest `main`.
2. Make the smallest safe fix and add a regression test when practical.
3. Open a PR into `main`; complete expedited review and checks.
4. Deploy and verify.
5. Immediately open a PR from `main` into `dev` so the fix is retained.
6. Sync from `dev` into `frontend` and/or `backend` if affected.

Never implement the same production fix independently on several permanent branches.

## AI Assistant Rules

If an AI assistant such as Codex, Claude, GPT, or any other model is helping with the repository, it must follow these rules:

- Do not decide on its own what should be pushed, merged, or published when the user intent is unclear.
- Before every push, analyze the current branch, the intended purpose of that branch, and all changed files. Decide whether to use the current branch, switch to another suitable task branch, or create a correctly named short-lived branch.
- Never assume that the current branch is the correct destination merely because the changes were made there. Explain the branch decision to the user before pushing.
- If it is not clear what should be pushed, what should be merged, or who should perform the action, ask the user a direct clarifying question first.
- Do not push directly to `main`, `dev`, `frontend`, or `backend`.
- Do not merge pull requests without clear user or team direction.
- Prefer asking before any Git action with non-obvious consequences.

## Recommended Team Workflow

1. Choose the base from the change-scope table.
2. Pull that permanent branch with `--ff-only`.
3. Create one focused, short-lived branch.
4. Make small Conventional Commits and run relevant checks.
5. Push the task branch and open a PR into its correct base.
6. Obtain review, resolve comments, and pass required checks.
7. Squash-merge and delete the task branch.
8. Integrate `frontend` and `backend` into `dev` frequently.
9. Release `dev` into `main` only through an approved release PR.

## TemplateOS-Specific Branch Examples

- `feature/auth-jwt`
- `feature/template-library`
- `feature/docx-upload`
- `feature/placeholder-detection`
- `feature/smart-form-generator`
- `feature/ai-writing-tools`
- `feature/docx-pdf-generation`
