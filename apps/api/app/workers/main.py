"""Worker de ingesta como proceso independiente: python -m app.workers.main

Solo hace falta si RUN_WORKER_IN_API=false (por ejemplo, para escalar API y worker por separado).
"""

import asyncio
import logging

from app.workers.ingestion import worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


if __name__ == "__main__":
    asyncio.run(worker.run())
