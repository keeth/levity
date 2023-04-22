import dataclasses
from asyncio import Event
from typing import Optional, Dict

from aio_pika.abc import (
    AbstractRobustChannel,
    AbstractRobustQueue,
)


@dataclasses.dataclass
class GlobalContext:
    clients: Dict[str, any]
    amqp_channel: Optional[AbstractRobustChannel] = None
    rpc_recv_queue: Optional[AbstractRobustQueue] = None
    rpc_send_queue: Optional[AbstractRobustQueue] = None
    shutdown_event: Optional[Event] = None


ctx = GlobalContext({})


def set_global_context(amqp_channel, rpc_recv_queue, rpc_send_queue, shutdown_event):
    global ctx
    ctx.amqp_channel = amqp_channel
    ctx.rpc_recv_queue = rpc_recv_queue
    ctx.rpc_send_queue = rpc_send_queue
    ctx.shutdown_event = shutdown_event
