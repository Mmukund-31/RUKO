"""WebRTC signalling: a tiny two-peer relay over WebSocket.

The server only relays SDP offers/answers and ICE candidates between the
`user` (RUKO side, offerer) and the `caller`. Media never touches the server.
"""

from __future__ import annotations

import json
import secrets
import socket
import time
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect

ROLES = ("user", "caller")
RELAY_TYPES = {"offer", "answer", "ice", "bye", "hello"}
MAX_MSG = 64 * 1024
ROOM_TTL_S = 3 * 3600
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


@dataclass
class Room:
    id: str
    created: float = field(default_factory=time.time)
    peers: dict[str, WebSocket] = field(default_factory=dict)


class Rooms:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}

    def create(self) -> Room:
        now = time.time()
        for rid in [k for k, r in self._rooms.items() if now - r.created > ROOM_TTL_S and not r.peers]:
            del self._rooms[rid]
        rid = "".join(secrets.choice(ALPHABET) for _ in range(6))
        room = self._rooms[rid] = Room(rid)
        return room

    def get(self, rid: str) -> Room | None:
        return self._rooms.get(rid.upper())


async def _send(ws: WebSocket, msg: dict) -> None:
    try:
        await ws.send_text(json.dumps(msg))
    except Exception:
        pass


async def signal_socket(ws: WebSocket, rooms: Rooms, rid: str, role: str) -> None:
    room = rooms.get(rid)
    await ws.accept()
    if room is None or role not in ROLES:
        await ws.close(code=4404, reason="unknown room or role")
        return
    old = room.peers.get(role)
    if old is not None:  # same role reconnecting: replace the stale socket
        try:
            await old.close(code=4409, reason="replaced")
        except Exception:
            pass
    room.peers[role] = ws
    other_role = "caller" if role == "user" else "user"
    other = room.peers.get(other_role)
    await _send(ws, {"type": "joined", "room": room.id, "role": role, "peer": other is not None})
    if other is not None:
        await _send(other, {"type": "peer-joined", "role": role})
        await _send(ws, {"type": "peer-joined", "role": other_role})
    try:
        while True:
            raw = await ws.receive_text()
            if len(raw) > MAX_MSG:
                continue
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("type") not in RELAY_TYPES:
                continue
            other = room.peers.get(other_role)
            if other is not None:
                await _send(other, {**msg, "from": role})
    except WebSocketDisconnect:
        pass
    finally:
        if room.peers.get(role) is ws:
            del room.peers[role]
            other = room.peers.get(other_role)
            if other is not None:
                await _send(other, {"type": "peer-left", "role": role})


def lan_ip() -> str:
    """Best-effort LAN address for join links (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
