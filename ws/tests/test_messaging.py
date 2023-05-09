import asyncio
import json
import logging

import aio_pika
import pytest
from aio_pika import Message
from async_asgi_testclient import TestClient

from levity_ws.config import AMQP_URL
from levity_ws.global_context import set_global_context
from levity_ws.rpc import rpc_recv_queue_consumer
from levity_ws.server import app

logging.basicConfig(
    level=logging.DEBUG, format="[%(levelname)s %(asctime)s %(name)s] %(message)s"
)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_handle_message_from_charge_point(caplog):
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
            await asyncio.sleep(0.1)
            message = await rpc_send_queue.get()
            async with message.process():
                data = json.loads(message.body.decode())
            assert data["type"] == "disconnect"
            assert data["id"] == "1234"
        logger.info("EXIT amqp_connection")
    logger.info("PRE SHUTDOWN")
    shutdown_event.set()
    logger.info("POST SHUTDOWN")


@pytest.mark.asyncio
async def test_send_message_to_charge_point(caplog):
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
        consumer_task = asyncio.create_task(rpc_recv_queue_consumer())
        async with TestClient(app) as client:
            async with client.websocket_connect("/ws/1234") as websocket:
                ws_message = await rpc_send_queue.get()
                async with ws_message.process():
                    data = json.loads(ws_message.body.decode())
                assert data["type"] == "connect"
                assert data["id"] == "1234"
                cmd_message = [2, "1", "RemoteStartTransaction", {"idTag": "anonymous"}]
                await amqp_channel.default_exchange.publish(
                    Message(
                        json.dumps(
                            dict(
                                id="1234",
                                message=cmd_message,
                            )
                        ).encode()
                    ),
                    routing_key=rpc_recv_queue.name,
                )
                logger.info("TestClient sleep")
                await asyncio.sleep(2)
                logger.info("TestClient wake")
                ws_message = await websocket.receive_json()
                assert ws_message == cmd_message
                reply_msg = [3, "1", {"status": "Accepted"}]
                await websocket.send_json(reply_msg)
                ws_message = await rpc_send_queue.get()
                async with ws_message.process():
                    data = json.loads(ws_message.body.decode())
                assert data["type"] == "receive"
                assert data["message"] == reply_msg
            await asyncio.sleep(0.1)
            ws_message = await rpc_send_queue.get()
            async with ws_message.process():
                data = json.loads(ws_message.body.decode())
            assert data["type"] == "disconnect"
        logger.info("PRE SHUTDOWN")
        shutdown_event.set()
        logger.info("POST SHUTDOWN")
        await consumer_task
        logger.info("TEST EXIT")
