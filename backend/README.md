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
