import asyncio
import json
import logging

import aio_pika
import pytest
from async_asgi_testclient import TestClient

from levity_ws.config import AMQP_URL
from levity_ws.global_context import set_global_context
from levity_ws.server import app

logging.basicConfig(
    level=logging.DEBUG, format="[%(levelname)s %(asctime)s %(name)s] %(message)s"
)


@pytest.mark.asyncio
async def test_app(caplog):
    caplog.set_level(logging.INFO)
    amqp_connection = await aio_pika.connect_robust(
        AMQP_URL,
    )
    async with amqp_connection:
        amqp_channel = await amqp_connection.channel()
        rpc_send_queue = await amqp_channel.declare_queue("", exclusive=True)
        rpc_recv_queue = await amqp_channel.declare_queue("", exclusive=True)
        shutdown_event = asyncio.Event()
        set_global_context(amqp_channel, rpc_recv_queue, rpc_send_queue, shutdown_event)
        async with TestClient(app) as client:
            async with client.websocket_connect("/ws/1234") as websocket:
                message = await rpc_send_queue.get()
                async with message.process():
                    data = json.loads(message.body.decode())
                assert data["type"] == "connect"
                assert data["id"] == "1234"
                send_msg = [2, "1", "BootNotification", {}]
                await websocket.send_json(send_msg)
                message = await rpc_send_queue.get()
                async with message.process():
                    data = json.loads(message.body.decode())
                assert data["type"] == "receive"
                assert data["id"] == "1234"
                assert data["message"] == send_msg
            message = await rpc_send_queue.get()
            async with message.process():
                data = json.loads(message.body.decode())
            assert data["type"] == "disconnect"
            assert data["id"] == "1234"

    shutdown_event.set()
