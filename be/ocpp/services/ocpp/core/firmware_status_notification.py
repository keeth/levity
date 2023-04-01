from ocpp.services.ocpp.base import OCPPMiddleware, OCPPResponse, OCPPRequest


class FirmwareStatusNotificationMiddleware(OCPPMiddleware):
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        return self.next.handle(req)
