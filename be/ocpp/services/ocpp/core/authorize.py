from ocpp.services.ocpp.base import OCPPMiddleware, OCPPResponse, OCPPRequest
from ocpp.types.authorization_status import AuthorizationStatus


class AuthorizeMiddleware(OCPPMiddleware):
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        res = self.next.handle(req)
        # by default, we simply accept every idTag for now
        res.message.data.update(
            dict(
                idTagInfo=dict(status=AuthorizationStatus.Accepted),
            )
        )
        return res
