import asyncio
import json
import logging
from typing import Optional

from aio_pika import Message
from aio_pika.abc import AbstractRobustExchange
from starlette.websockets import WebSocket

from .global_context import ctx
from .types import MessageType
from .cancellable_iterator import cancellable_iterator

logger = logging.getLogger(__name__)

CHARGE_POINT_EXCHANGE = "charge-point"

CHARGER_REPLY_TIMEOUT_SECONDS = 30

CHARGER_COMMAND_DELAY_MS = 1000


class ChargePointClient:
    def __init__(self, charge_point_id: str, websocket: WebSocket):
        self._charge_point_id = charge_point_id
        self.websocket = websocket
        self._command_queue = "cp_{}".format(charge_point_id)
        self._awaiting_replies = {}
        self._disconnect_event = asyncio.Event()
        self._exchange: Optional[AbstractRobustExchange] = None
        self._consume_task = asyncio.create_task(self.consume_command_queue())

    async def disconnect(self):
        self._disconnect_event.set()
        await self._consume_task
        self._consume_task = None

    async def handle_message_from_charge_point(self, message: dict):
        charge_point_reply = message["message"]
        message_type = MessageType(charge_point_reply[0])
        if message_type in (MessageType.call_result, MessageType.call_error):
            reply_id = charge_point_reply[1]
            if reply_id not in self._awaiting_replies:
                logger.warning(
                    "Unexpected reply ID %s (charge point %s)",
                    reply_id,
                    self._charge_point_id,
                )
                return
            logger.info(
                "IN: CP %s",
                dict(
                    cp=self._charge_point_id, mtype=charge_point_reply[0], mid=reply_id
                ),
            )
            self._awaiting_replies[reply_id].set()
            del self._awaiting_replies[reply_id]

    async def send_message_to_charge_point(self, message: dict):
        charge_point_message = message["message"]
        message_type = MessageType(charge_point_message[0])
        # for replies from server, send immediately
        if message_type in (MessageType.call_result, MessageType.call_error):
            logger.info(
                "OUT: CP %s",
                dict(
                    cp=self._charge_point_id,
                    mtype=charge_point_message[0],
                    mid=charge_point_message[1],
                ),
            )
            await self.websocket.send_json(charge_point_message)
        # for commands from server, enqueue and send serially, waiting for a reply after each
        else:
            command_message = Message(
                json.dumps(charge_point_message).encode(),
                headers={"x-delay": CHARGER_COMMAND_DELAY_MS},
            )
            ack = await self._exchange.publish(command_message, self._command_queue)
            logger.info(
                "OUTQ: CP %s",
                dict(
                    cp=self._charge_point_id,
                    mtype=charge_point_message[0],
                    mid=charge_point_message[1],
                    qid=ack.delivery_tag if ack else 0,
                ),
            )

    async def consume_command_queue(self):
        logger.debug("START: CP consumer %s", self._charge_point_id)
        command_queue = await ctx.amqp_channel.declare_queue(self._command_queue)
        self._exchange = await ctx.amqp_channel.declare_exchange(
            CHARGE_POINT_EXCHANGE,
            "x-delayed-message",
            arguments={"x-delayed-type": "direct"},
        )
        await command_queue.bind(self._exchange)
        while not any([ctx.shutdown_event.is_set(), self._disconnect_event.is_set()]):
            async with command_queue.iterator() as queue_iter:
                logger.info("START: CP iterator %s", self._charge_point_id)
                async for message in cancellable_iterator(
                    queue_iter, ctx.shutdown_event, self._disconnect_event
                ):
                    async with message.process():
                        # ACK the message right away
                        body = message.body.decode()
                    try:
                        charge_point_command = json.loads(body)
                        logger.info(
                            "INQ: CP %s",
                            dict(
                                cp=self._charge_point_id,
                                qid=message.delivery_tag,
                                rd=message.redelivered,
                            ),
                        )
                        if self._charge_point_id not in ctx.clients:
                            logger.warning(
                                "SEND ERR (disconnected): %s", self._charge_point_id
                            )
                            continue
                        logger.info(
                            "OUT CP: %s",
                            dict(
                                cp=self._charge_point_id,
                                type=charge_point_command[0],
                                id=charge_point_command[1],
                            ),
                        )
                        command_id = charge_point_command[1]
                        wait_for_reply = asyncio.Event()
                        self._awaiting_replies[command_id] = wait_for_reply
                        await self.websocket.send_json(charge_point_command)
                    except Exception:
                        logger.exception("ERR: CP %s", dict(cp=self._charge_point_id))
                        raise

                    try:
                        reply_task = asyncio.create_task(wait_for_reply.wait())
                        cancellation_tasks = [
                            asyncio.create_task(event.wait())
                            for event in [
                                ctx.shutdown_event,
                                self._disconnect_event,
                            ]
                        ]
                        logger.info(
                            "START: CP reply-wait %s",
                            dict(cp=self._charge_point_id, mid=command_id),
                        )
                        done, pending = await asyncio.wait(
                            [*cancellation_tasks, reply_task],
                            timeout=CHARGER_REPLY_TIMEOUT_SECONDS,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for done_task in done:
                            if done_task in cancellation_tasks:
                                logger.info(
                                    "EXIT: CP reply-wait %s",
                                    dict(cp=self._charge_point_id, mid=command_id),
                                )
                                break
                        logger.info(
                            "END: CP reply-wait %s",
                            dict(cp=self._charge_point_id, mid=command_id),
                        )
                    except asyncio.TimeoutError:
                        logger.error(
                            "Timeout awaiting response %s", self._charge_point_id
                        )
                    except Exception:
                        logger.error(
                            "Error awaiting response %s", self._charge_point_id
                        )
                logger.info("EXIT: CP iterator loop %s", dict(cp=self._charge_point_id))
        logger.debug("EXIT: CP consumer %s", dict(cp=self._charge_point_id))
