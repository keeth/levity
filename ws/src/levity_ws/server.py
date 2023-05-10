import json
import logging

from aio_pika import Message
from starlette.applications import Starlette
from starlette.endpoints import WebSocketEndpoint
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

from .charge_point_client import ChargePointClient
from .config import CHARGE_POINT_ID
from .global_context import ctx

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


async def health(request):
    return JSONResponse({"ok": True})


class MainWebsocket(WebSocketEndpoint):
    encoding = "json"

    async def _rpc_send(self, msg: dict):
        msg["queue"] = ctx.rpc_recv_queue.name
        rpc_message = Message(
            json.dumps(msg).encode(),
        )
        await ctx.amqp_channel.default_exchange.publish(
            rpc_message, ctx.rpc_send_queue.name
        )

    async def on_receive(self, websocket: WebSocket, ws_message):
        charge_point_id = websocket.path_params[CHARGE_POINT_ID]
        logger.info(
            "IN: WS %s: %s",
            dict(cp=charge_point_id, ws=id(websocket)),
            ws_message,
        )
        if charge_point_id not in ctx.clients:
            logger.warning(
                "ERR: WS %s: missing from clients (fixed)",
                dict(cp=charge_point_id),
            )
            ctx.clients[charge_point_id] = ChargePointClient(charge_point_id, websocket)
            await self._rpc_send(dict(type="connect", id=charge_point_id))
        wrapped_message = dict(
            type="receive",
            id=charge_point_id,
            message=ws_message,
        )
        await ctx.clients[charge_point_id].handle_message_from_charge_point(
            wrapped_message
        )
        await self._rpc_send(wrapped_message)

    async def on_connect(self, websocket: WebSocket):
        charge_point_id = websocket.path_params[CHARGE_POINT_ID]

        logger.info(
            "CONN: WS %s",
            dict(
                cp=charge_point_id,
                ws=id(websocket),
                host=websocket.client.host if websocket.client else None,
            ),
        )
        await websocket.accept(
            subprotocol=websocket.headers.get("sec-websocket-protocol")
        )
        if charge_point_id in ctx.clients:
            logger.warning(
                "ERR: WS: already connected %s",
                dict(
                    cp=charge_point_id,
                    ws=id(ctx.clients[charge_point_id].websocket),
                    host=ctx.clients[charge_point_id].websocket.client.host,
                ),
            )
            await ctx.clients[charge_point_id].disconnect()
        ctx.clients[charge_point_id] = ChargePointClient(charge_point_id, websocket)
        await self._rpc_send(dict(type="connect", id=charge_point_id))

    async def on_disconnect(self, websocket: WebSocket, close_code):
        charge_point_id = websocket.path_params[CHARGE_POINT_ID]
        client = ctx.clients.pop(charge_point_id, None)
        if not client:
            logger.warning(
                "Charge point %s on_disconnect: connection not found",
                charge_point_id,
            )
        await client.disconnect()
        logger.info("DISC: WS %s", dict(cp=charge_point_id, ws=id(websocket)))
        await self._rpc_send(dict(type="disconnect", id=charge_point_id))


routes = [
    Route("/health", endpoint=health),
    WebSocketRoute("/ws/{charge_point_id}", endpoint=MainWebsocket),
]

app = Starlette(debug=True, routes=routes)
