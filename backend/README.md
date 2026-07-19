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
