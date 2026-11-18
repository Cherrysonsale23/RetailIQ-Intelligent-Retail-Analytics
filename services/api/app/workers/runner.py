import asyncio
import logging

from app.db.supabase_rest import SupabaseAdmin
from app.workers.pipeline import process_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def run() -> None:
    admin = SupabaseAdmin()
    logger.info("Meridian CSV worker started")
    while True:
        try:
            jobs = await admin.request("POST", "rpc/claim_next_processing_job", json={})
            if jobs:
                await process_job(jobs[0], admin)
            else:
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Worker polling failed")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run())
