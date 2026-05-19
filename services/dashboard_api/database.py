"""
asyncpg connection pool for the Dashboard API.

Why asyncpg and not psycopg2?
FastAPI is async (Starlette under the hood). psycopg2 is synchronous —
calling it inside an async route blocks the entire event loop, killing
concurrency. asyncpg is a pure-Python async Postgres driver with a
connection pool that plays nicely with asyncio.

Pool settings:
  min_size=2  — keep 2 connections warm; avoids cold-start latency on
                the first dashboard load after idle.
  max_size=10 — cap at 10 to avoid exhausting Postgres max_connections
                (default 100; we share the DB with MCP server + agents).
"""
import os
import asyncpg
from fastapi import Request


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://scai:scai_password@localhost:5432/supply_chain"
)


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )


# ── Dependency injection helper ────────────────────────────────────────────────
# FastAPI routes declare `db: asyncpg.Pool = Depends(get_db)`.
# This pulls the pool that was attached to app.state during startup.

async def get_db(request: Request) -> asyncpg.Pool:
    return request.app.state.db
