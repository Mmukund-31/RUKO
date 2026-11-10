"""In-memory session and generated-audio stores with TTL.

Nothing is written to disk: no raw user audio and no conversation logs are
persisted. Restarting the backend clears everything.
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass

from .conversation import Session

SESSION_TTL_S = 30 * 60
AUDIO_TTL_S = 10 * 60
AUDIO_MAX = 200


class SessionStore:
    def __init__(self) -> None:
        self._items: dict[str, Session] = {}

    def _sweep(self) -> None:
        now = time.time()
        for sid in [k for k, s in self._items.items() if now - s.touched > SESSION_TTL_S]:
            del self._items[sid]

    def create(self) -> Session:
        self._sweep()
        s = Session()
        self._items[s.id] = s
        return s

    def get(self, sid: str) -> Session | None:
        self._sweep()
        return self._items.get(sid)

    def delete(self, sid: str) -> bool:
        return self._items.pop(sid, None) is not None


@dataclass
class Clip:
    data: bytes
    content_type: str
    created: float


class AudioCache:
    def __init__(self) -> None:
        self._items: OrderedDict[str, Clip] = OrderedDict()

    def put(self, data: bytes, content_type: str) -> str:
        now = time.time()
        while self._items:
            k, v = next(iter(self._items.items()))
            if now - v.created > AUDIO_TTL_S or len(self._items) >= AUDIO_MAX:
                self._items.popitem(last=False)
            else:
                break
        cid = uuid.uuid4().hex
        self._items[cid] = Clip(data, content_type, now)
        return cid

    def get(self, cid: str) -> Clip | None:
        return self._items.get(cid)
