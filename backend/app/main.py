import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import get_session

app = FastAPI(title="Route Planning API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173"],
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


@app.get("/api/plan")
def test_plan() -> JSONResponse:
    return load_json("./app/mock/plan.json")


@app.get("/api/regions")
def test_regions() -> JSONResponse:
    return load_json("./app/mock/regions.json")


@app.get("/api/regions/{regionId}/requests")
def test_requests(regionId: str) -> JSONResponse:
    return load_json("./app/mock/requests.json")


@app.get("/api/regions/{regionId}/engineers")
def test_engineers() -> JSONResponse:
    return load_json("./app/mock/engineers.json")


def load_json(filename: str) -> JSONResponse:
    with open(filename, encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(content=data)
