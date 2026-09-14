from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.db import get_session

app = FastAPI(title="Route Planning API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health/db")
async def database_health() -> dict[str, str]:
    async for session in get_session():
        await session.execute(text("SELECT 1"))
        return {"status": "ok"}
    raise RuntimeError("database session was not created")
