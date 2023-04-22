import json
import logging

from levity_ws.cancellable_iterator import cancellable_iterator
from levity_ws.global_context import ctx

logger = logging.getLogger(__name__)


async def rpc_recv_queue_consumer():
    async with ctx.rpc_recv_queue.iterator() as queue_iter:
        async for message in cancellable_iterator(queue_iter, ctx.shutdown_event):
            async with message.process():
                body = message.body.decode()
                logger.info("BE RECV %s", body)
                decoded = json.loads(body)
                charge_point_id = decoded["id"]
                if charge_point_id not in ctx.clients:
                    logger.warning("SEND ERR (disconnected): %s", charge_point_id)
                    continue
                await ctx.clients[charge_point_id].send_message_to_charge_point(decoded)
    logger.info("BE CONSUMER SHUTDOWN")
