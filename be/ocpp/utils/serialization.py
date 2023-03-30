import dataclasses
import json
from enum import Enum

from django.core.serializers.json import DjangoJSONEncoder


def json_encode(o):
    return json.dumps(o, cls=JSONEncoder)


def json_decode(o):
    return json.loads(o)


class JSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        return super().default(obj)
