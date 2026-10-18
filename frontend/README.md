# TemplateOS Frontend

React 18 + TypeScript + Vite single-page app for TemplateOS: template upload
and field setup, draft forms, document generation and preview, and admin
pages. Server state is handled by TanStack Query, forms by react-hook-form +
zod, and UI components are Tailwind CSS + Radix (shadcn/ui style).

## Run locally

Dependencies are installed once from the **repository root** (npm workspace):

```bash
npm install
npm run dev:frontend        # http://localhost:5173
```

The backend must be running on `http://localhost:8000` (see the
[backend README](../backend/README.md)).

## Configuration

Vite reads environment files from the **repository root** (`envDir: ".."` in
`vite.config.ts`), so the frontend shares the root `.env` with the backend.
Only variables prefixed with `VITE_` reach the browser:

| Variable | Default | Meaning |
| --- | --- | --- |
| `VITE_API_BASE_URL` | dev: `http://localhost:8000/api/v1`, build: `/api/v1` | Base URL of the backend API. Set it for production builds. |

Use `localhost`, not `127.0.0.1`, for the API in development. The session
lives in httpOnly cookies, and the browser only sends them when the app
(`localhost:5173`) and the API are on the same site. With `127.0.0.1` you will
log in and then appear logged out.

## Scripts

Run these from `frontend/`, or from the root with `-w frontend`
(for example `npm run test -w frontend`):

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server with hot reload on port 5173 |
| `npm run build` | Type-check (`tsc -b`) and build into `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm test` | Unit tests in `tests/*.test.ts` |

## Tests

The unit tests use Node's built-in test runner (`node --test`) with no extra
framework. Node runs the TypeScript files directly, so **Node.js 22.18 or
newer** is required. Tests cover pure logic only: validation rules, dates,
query keys, the session refresh flow, the AI style state machine, list
fields, audience and admin permissions. CI runs the type-check, the tests and
the build on every pull request.

## Folder structure

```text
src/
  main.tsx, App.tsx    entry point and routes
  pages/               one component per route (dashboard, drafts, admin, ...)
  features/            larger flows split out of pages: documents, field-setup,
                       template-cleaning, placeholder-review, document-preview, admin
  components/          shared UI: ui/ (base components), forms/ (dynamic draft
                       fields), fields/ (AI toolbar, field helpers), templates/, upload/
  hooks/queries/       TanStack Query hooks per resource
  lib/api/             typed API client, one module per resource, cookie session refresh
  lib/                 validation, dates, audience and permission helpers
  context/             auth context (current user, login, logout)
  layouts/             dashboard layout with the sidebar
tests/                 node --test unit tests
```

Imports use the `@/` alias for `src/` (set in `vite.config.ts` and `tsconfig.app.json`).
