from ocpp.services.ocpp.base import OCPPMiddleware, OCPPResponse, OCPPRequest
from ocpp.types.data_transfer_status import DataTransferStatus


class DataTransferMiddleware(OCPPMiddleware):
    def handle(self, req: OCPPRequest) -> OCPPResponse:
        res = self.next.handle(req)
        # reject all data transfer requests by default
        res.message.data.update(
            dict(
                status=DataTransferStatus.Rejected,
            )
        )
        return res
