"""Governance worker CLI: python -m meeting_notes_ai.workers.governance."""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from meeting_notes_ai.config import settings
from meeting_notes_ai.db.engine import create_db_engine, create_session_factory
from meeting_notes_ai.db.models import DeletionJob
from meeting_notes_ai.services.governance.jobs import run_deletion_job


async def run_once() -> int:
    engine = create_db_engine(settings.database_url)
    factory = create_session_factory(engine)
    count = 0
    async with factory() as db:
        jobs = (
            (
                await db.execute(
                    select(DeletionJob)
                    .where(DeletionJob.status.in_(["pending", "completed_partial"]))
                    .order_by(DeletionJob.created_at)
                    .limit(25)
                )
            )
            .scalars()
            .all()
        )
        for job in jobs:
            await run_deletion_job(db, job.id)
            count += 1
        await db.commit()
    await engine.dispose()
    return count


async def loop(interval: float) -> None:
    while True:
        await run_once()
        await asyncio.sleep(interval)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    p.add_argument("--interval", type=float, default=5.0)
    a = p.parse_args()
    asyncio.run(run_once() if a.once else loop(a.interval))


if __name__ == "__main__":
    main()
