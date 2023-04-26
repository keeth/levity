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

CHARGER_REPLY_TIMEOUT_SECONDS = 10

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
        logger.debug("disconnect_event.set %s", self._charge_point_id)
        self._disconnect_event.set()
        logger.debug("await consume_task %s", self._charge_point_id)
        await self._consume_task
        logger.debug("disconnected %s", self._charge_point_id)
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
            self._awaiting_replies[reply_id].set()
            del self._awaiting_replies[reply_id]

    async def send_message_to_charge_point(self, message: dict):
        charge_point_message = message["message"]
        message_type = MessageType(charge_point_message[0])
        # for replies from server, send immediately
        if message_type in (MessageType.call_result, MessageType.call_error):
            logger.info("CMD SEND (direct) %s", message)
            await self.websocket.send_json(charge_point_message)
        # for commands from server, enqueue and send serially, waiting for a reply after each
        else:
            command_message = Message(
                json.dumps(charge_point_message).encode(),
                headers={"x-delay": CHARGER_COMMAND_DELAY_MS},
            )
            logger.info("CMD QUEUE-SEND %s", message)
            await self._exchange.publish(command_message, self._command_queue)

    async def consume_command_queue(self):
        logger.debug("CMD CONSUMER START %s", self._charge_point_id)
        command_queue = await ctx.amqp_channel.declare_queue(self._command_queue)
        self._exchange = await ctx.amqp_channel.declare_exchange(
            CHARGE_POINT_EXCHANGE,
            "x-delayed-message",
            arguments={"x-delayed-type": "direct"},
        )
        await command_queue.bind(self._exchange)
        while not any([ctx.shutdown_event.is_set(), self._disconnect_event.is_set()]):
            async with command_queue.iterator() as queue_iter:
                async for message in cancellable_iterator(
                    queue_iter, ctx.shutdown_event, self._disconnect_event
                ):
                    async with message.process():
                        # ACK the message right away
                        body = message.body.decode()
                        logger.info(
                            "CMD QUEUE-RECV %s %s redelivered=%s",
                            self._charge_point_id,
                            body,
                            message.redelivered,
                        )
                    try:
                        charge_point_command = json.loads(body)
                        if self._charge_point_id not in ctx.clients:
                            logger.warning(
                                "SEND ERR (disconnected): %s", self._charge_point_id
                            )
                            continue
                        logger.info(
                            "CMD SEND %s %s",
                            self._charge_point_id,
                            charge_point_command,
                        )
                        command_id = charge_point_command[1]
                        wait_for_reply = asyncio.Event()
                        self._awaiting_replies[command_id] = wait_for_reply
                        await self.websocket.send_json(charge_point_command)
                    except Exception:
                        logger.exception("CMD ERR %s", self._charge_point_id)
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
                            "CMD REPL WAIT %s %s",
                            self._charge_point_id,
                            command_id,
                        )
                        done, pending = await asyncio.wait(
                            [*cancellation_tasks, reply_task],
                            timeout=CHARGER_REPLY_TIMEOUT_SECONDS,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for done_task in done:
                            if done_task in cancellation_tasks:
                                logger.info(
                                    "CMD REPLY CANCEL %s %s",
                                    self._charge_point_id,
                                    command_id,
                                )
                                break
                        logger.info(
                            "CMD REPL RECV %s %s", self._charge_point_id, command_id
                        )
                    except asyncio.TimeoutError:
                        logger.error(
                            "Timeout awaiting response %s", self._charge_point_id
                        )
                    except Exception:
                        logger.error(
                            "Error awaiting response %s", self._charge_point_id
                        )
        logger.debug("CMD CONSUMER EXIT %s", self._charge_point_id)
