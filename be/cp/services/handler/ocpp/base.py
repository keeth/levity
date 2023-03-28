import abc

from cp.models.message import Message


class OCPPMessageHandler(abc.ABC):
    @abc.abstractmethod
    def handle(self, message: Message):
        pass
