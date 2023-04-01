from ocpp.services.ocpp.base import OCPPMiddleware, OCPPResponse, OCPPRequest


class DiagnosticsStatusNotificationMiddleware(OCPPMiddleware):
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        return self.next.handle(req)
