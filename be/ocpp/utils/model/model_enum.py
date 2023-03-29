from enum import Enum


class ModelEnum(Enum):
    @classmethod
    def choices(cls):
        return [(i.value, i.value) for i in cls]

    def __str__(self):
        return str(self.value)

    def __int__(self):
        return int(self.value)
