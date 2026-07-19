# Contributing Guide

This repository follows a simple GitHub workflow so `main` stays stable and the team can collaborate safely.

## Core Rule

Never work directly on `main`. Create a branch, push that branch, and merge changes through a pull request.

## Repository Rules

- Keep `main` stable, clean, and runnable.
- Merge only reviewed and tested changes into `main`.
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

## Pull Rules

Before starting new work on an older branch:

```bash
git checkout main
git pull origin main
git checkout feature/your-branch
git merge main
```

Follow these rules:

- Commit or stash local work before pulling.
- Pull the latest `main` before opening a pull request.
- Pull and merge `main` into your branch again if `main` changed before final merge.
- Resolve conflicts locally and test again after resolving them.

## Push Rules

- Push only your working branch, not `main`.
- Push small, meaningful commits instead of one very large commit.
- Use clear commit messages.

Good commit message examples:

- `feat: add JWT login API`
- `fix: handle invalid DOCX upload`
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

- `Add template upload flow`
- `Implement placeholder detection service`
- `Fix generated PDF status handling`

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
- Prefer `Squash and merge` to keep history clean for a small team.
- Delete the branch after merge if the work is complete.

Use `Rebase and merge` only if the team is comfortable with it and intentionally wants that history style.

## Conflict Rules

- The branch owner resolves conflicts.
- After resolving conflicts, run the relevant checks and retest the affected flow.
- Do not guess during conflict resolution. Read both sides carefully.

## Main Branch Protection

If GitHub branch protection is enabled, use these settings:

- Require a pull request before merging
- Require at least 1 approval
- Prevent direct pushes to `main`
- Require branches to be up to date before merging when practical

## AI Assistant Rules

If an AI assistant such as Codex, Claude, GPT, or any other model is helping with the repository, it must follow these rules:

- Do not decide on its own what should be pushed, merged, or published when the user intent is unclear.
- If it is not clear what should be pushed, what should be merged, or who should perform the action, ask the user a direct clarifying question first.
- Do not push directly to `main`.
- Do not merge pull requests without clear user or team direction.
- Prefer asking before any Git action with non-obvious consequences.

## Recommended Team Workflow

1. Pull the latest `main`.
2. Create a branch from `main`.
3. Build one focused feature or fix.
4. Commit with clear messages.
5. Push the branch.
6. Open a pull request.
7. Get review.
8. Merge into `main`.
9. Delete the finished branch.

## TemplateOS-Specific Branch Examples

- `feature/auth-jwt`
- `feature/template-library`
- `feature/docx-upload`
- `feature/placeholder-detection`
- `feature/smart-form-generator`
- `feature/ai-writing-tools`
- `feature/docx-pdf-generation`
