import asyncio
import logging

from levity_ws.main import main_async

logging.basicConfig(
    level=logging.INFO, format="[%(levelname)s %(asctime)s %(name)s] %(message)s"
)


asyncio.run(main_async())
