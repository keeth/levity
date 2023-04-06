import asyncio
import json
import logging
import os
from asyncio import Event
from typing import Optional, Dict

import aio_pika
from aio_pika import Message
from aio_pika.abc import (
    AbstractRobustChannel,
    AbstractRobustQueue,
)
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.endpoints import WebSocketEndpoint
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket
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

clients: Dict[str, WebSocket] = {}


async def health(request):
    return JSONResponse({"ok": True})


cancellation_event: Optional[Event] = None
amqp_channel: Optional[AbstractRobustChannel] = None
reply_queue: Optional[AbstractRobustQueue] = None


class MainWebsocket(WebSocketEndpoint):
    encoding = "json"

    async def _rpc_send(self, msg):
        rpc_message = Message(
            json.dumps(msg).encode(),
        )
        await amqp_channel.default_exchange.publish(rpc_message, RPC_QUEUE)

    async def on_receive(self, websocket: WebSocket, ws_message):
        charge_point_id = websocket.path_params[CHARGE_POINT_ID]
        logger.debug(
            "WS RECEIVE %s MSG: %s",
            dict(charge_point=charge_point_id, client=id(websocket)),
            ws_message,
        )
        await self._rpc_send(
            dict(
                type="receive",
                id=charge_point_id,
                message=ws_message,
                queue=reply_queue.name,
            )
        )

    async def on_connect(self, websocket: WebSocket):
        charge_point_id = websocket.path_params[CHARGE_POINT_ID]

        logger.info(
            "WS CONNECT %s",
            dict(
                charge_point=charge_point_id,
                client=id(websocket),
                host=websocket.client.host,
            ),
        )
        await websocket.accept(
            subprotocol=websocket.headers.get("sec-websocket-protocol")
        )
        if charge_point_id in clients:
            logger.warning(
                "Charge point %s already connected from %s",
                charge_point_id,
                clients[charge_point_id].client.host,
            )
        clients[charge_point_id] = websocket
        await self._rpc_send(
            dict(type="connect", id=charge_point_id, queue=reply_queue.name)
        )

    async def on_disconnect(self, websocket: WebSocket, close_code):
        charge_point_id = websocket.path_params[CHARGE_POINT_ID]
        client = clients.pop(charge_point_id, None)
        if not client:
            logger.warning(
                "Charge point %s on_disconnect: connection not found",
                charge_point_id,
            )
        logger.info(
            "WS DISCONNECT %s", dict(charge_point=charge_point_id, client=id(websocket))
        )
        await self._rpc_send(
            dict(type="disconnect", id=charge_point_id, queue=reply_queue.name)
        )


async def setup_amqp():
    global amqp_channel
    global reply_queue

    amqp_connection = await aio_pika.connect_robust(
        AMQP_URL,
    )

    async with amqp_connection:
        logger.info("AMQP START")
        amqp_channel = await amqp_connection.channel()
        await amqp_channel.set_qos(prefetch_count=1)
        await amqp_channel.declare_queue(RPC_QUEUE)
        reply_queue = await amqp_channel.declare_queue("", exclusive=True)

        async with reply_queue.iterator() as queue_iter:
            async for message in cancellable_iterator(queue_iter, cancellation_event):
                async with message.process():
                    body = message.body.decode()
                    logger.info("AMQP RECV %s", body)
                    decoded = json.loads(body)
                    charge_point_id = decoded["id"]
                    charge_point_message = decoded["message"]
                    if charge_point_id not in clients:
                        logger.warning("SEND ERR (disconnected): %s", charge_point_id)
                        continue
                    await clients[charge_point_id].send_json(charge_point_message)

    logger.info("AMQP STOP")


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
config = Config(
    app,
    host=HOST,
    port=PORT,
    loop="asyncio",
    ws_ping_interval=None,  # Grizzl-e doesn't handle pings well
)

ws_server = GracefulShutdownServer(config=config)


async def main_async():
    global cancellation_event
    cancellation_event = Event()
    await asyncio.gather(setup_amqp(), ws_server.serve())
    logger.info("Exit main loop")


if __name__ == "__main__":
    asyncio.run(main_async())
