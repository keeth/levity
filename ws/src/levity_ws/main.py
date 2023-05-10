import asyncio
import logging
from asyncio import Event

import aio_pika
from uvicorn import Config, Server

from .config import AMQP_URL, HOST, PORT, RPC_SEND_QUEUE
from .global_context import set_global_context
from .rpc import rpc_recv_queue_consumer
from .server import app

logger = logging.getLogger(__name__)


class GracefulShutdownServer(Server):
    def __init__(self, config: Config, shutdown_event: Event) -> None:
        super().__init__(config)
        self._shutdown_event = shutdown_event

    def handle_exit(self, sig, frame):
        super().handle_exit(sig, frame)
        logger.info("SERVER SHUTDOWN")
        self._shutdown_event.set()


async def main_async():
    amqp_connection = await aio_pika.connect_robust(
        AMQP_URL,
    )
    async with amqp_connection:
        amqp_channel = await amqp_connection.channel()
        await amqp_channel.set_qos(prefetch_count=1)
        rpc_send_queue = await amqp_channel.declare_queue(RPC_SEND_QUEUE)
        rpc_recv_queue = await amqp_channel.declare_queue("", exclusive=True)
        shutdown_event = Event()
        set_global_context(amqp_channel, rpc_recv_queue, rpc_send_queue, shutdown_event)
        config = Config(
            app,
            host=HOST,
            port=PORT,
            loop="asyncio",
            ws_ping_interval=None,  # Grizzl-e doesn't handle pings well
        )
        server = GracefulShutdownServer(config, shutdown_event)
        await asyncio.gather(rpc_recv_queue_consumer(), server.serve())
        logger.info("EXIT: SERVER")
