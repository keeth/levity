#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import signal
from asyncio import Event
from typing import Optional

import aio_pika
from aio_pika import Message
from aio_pika.abc import (
    AbstractRobustConnection,
    AbstractRobustChannel,
    AbstractRobustQueue,
)
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.endpoints import WebSocketEndpoint
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from uvicorn import Config, Server

from util import cancellable_iterator

logging.basicConfig(
    level=logging.INFO, format="[%(levelname)s %(asctime)s %(name)s] %(message)s"
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

load_dotenv()

PORT = int(os.getenv("PORT", "3000"))
HOST = os.getenv("HOST", "0.0.0.0")
AMQP_URL = os.getenv("AMQP_URL", "amqp://127.0.0.1/")
RPC_QUEUE = "rpc"
CHARGE_POINT_ID = "charge_point_id"

clients = {}


async def health(request):
    return JSONResponse({"ok": True})


cancellation_event: Optional[Event] = None
amqp_channel: Optional[AbstractRobustChannel] = None


class MainWebsocket(WebSocketEndpoint):
    encoding = "json"

    async def _rpc_send(self, msg):
        rpc_message = Message(
            json.dumps(dict(type="message", message=msg)).encode(),
        )
        await amqp_channel.default_exchange.publish(rpc_message, RPC_QUEUE)

    async def on_receive(self, websocket, ws_message):
        charge_point_id = websocket.path_params[CHARGE_POINT_ID]
        logger.debug("WS receive %s %s %s", id(websocket), charge_point_id, ws_message)
        await self._rpc_send(
            dict(type="receive", id=charge_point_id, message=ws_message)
        )

    async def on_connect(self, websocket):
        charge_point_id = websocket.path_params[CHARGE_POINT_ID]
        logger.info("WS connect %s %s", id(websocket), charge_point_id)
        await websocket.accept(
            subprotocol=websocket.headers.get("sec-websocket-protocol")
        )
        clients[id(websocket)] = {"ws": websocket, "id": charge_point_id}
        await self._rpc_send(dict(type="connect", id=charge_point_id))

    async def on_disconnect(self, websocket, close_code):
        charge_point_id = websocket.path_params[CHARGE_POINT_ID]
        del clients[id(websocket)]
        logger.info("WS disconnect %s %s", id(websocket), charge_point_id)
        await self._rpc_send(dict(type="disconnect", id=charge_point_id))


async def setup_amqp():
    global amqp_channel

    amqp_connection = await aio_pika.connect_robust(
        AMQP_URL,
    )

    async with amqp_connection:
        logger.info("Enter AMQP loop")
        amqp_channel = await amqp_connection.channel()
        await amqp_channel.set_qos(prefetch_count=1)
        await amqp_channel.declare_queue(RPC_QUEUE)
        reply_queue = await amqp_channel.declare_queue("", exclusive=True)

        async with reply_queue.iterator() as queue_iter:
            async for message in cancellable_iterator(queue_iter, cancellation_event):
                async with message.process():
                    logger.info("AMQP receive %s", message.body)

    logger.info("Exit AMQP loop")


class GracefulShutdownServer(Server):
    def handle_exit(self, sig, frame):
        super().handle_exit(sig, frame)
        logger.info("Server shutdown")
        cancellation_event.set()


routes = [
    Route("/health", endpoint=health),
    WebSocketRoute("/ws/{charge_point_id}", endpoint=MainWebsocket),
]

app = Starlette(debug=True, routes=routes)
config = Config(app, host=HOST, port=PORT, loop="asyncio")

ws_server = GracefulShutdownServer(config=config)


async def main_async():
    global cancellation_event
    cancellation_event = Event()
    await asyncio.gather(setup_amqp(), ws_server.serve())
    logger.info("Exit main loop")


if __name__ == "__main__":
    asyncio.run(main_async())
