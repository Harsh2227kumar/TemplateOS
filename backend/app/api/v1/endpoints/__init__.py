"""
API v1 endpoint modules.

Sync vs async rule: the database Session is synchronous (SQLAlchemy 2.0
sync), so endpoints are plain `def`. FastAPI runs them in its threadpool,
which keeps blocking DB, file storage, DOCX parsing and AI calls off the
event loop; call those directly, without `asyncio.to_thread`. Uploads read
`UploadFile.file` synchronously.

Only use `async def` when an endpoint truly has to `await` something. Then
every blocking call inside it, including every DB call, must go through
`asyncio.to_thread` / `run_in_threadpool`.
"""
