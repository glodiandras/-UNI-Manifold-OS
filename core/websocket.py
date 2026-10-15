"""Szerveroldali WebSocket (RFC 6455), a standard könyvtárral: kézfogás, szövegkeret, ping/pong, close.

Csak amit a core ↔ felület határ kér: a core eseményeket küld, a kliens pingel vagy zár. A bejövő
keret legfeljebb `MAX_BE` bájt, maszkolt (a kliensé kötelezően az); töredezett üzenetet nem fogadunk.
"""
from __future__ import annotations

import base64
import hashlib
import json
import socket
import struct
import threading

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_BE = 64 * 1024
OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x1, 0x2, 0x8, 0x9, 0xA


class ProtocolError(Exception):
    """Szabálytalan keret — a kapcsolat 1002-vel zárul."""


def accept_key(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()


def frame(opcode: int, payload: bytes) -> bytes:
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack("!H", n)
    else:
        head += bytes([127]) + struct.pack("!Q", n)
    return head + payload


def _pontosan(rfile, n: int) -> bytes:
    b = rfile.read(n)
    if b is None or len(b) < n:
        raise ConnectionError("a kliens bontotta a kapcsolatot")
    return b


def read_frame(rfile) -> tuple[int, bytes]:
    b0, b1 = _pontosan(rfile, 2)
    fin, opcode, masked, n = b0 & 0x80, b0 & 0x0F, b1 & 0x80, b1 & 0x7F
    if b0 & 0x70:
        raise ProtocolError("foglalt bitek")
    if not masked:
        raise ProtocolError("a kliens kerete maszk nélkül jött")
    if n == 126:
        n = struct.unpack("!H", _pontosan(rfile, 2))[0]
    elif n == 127:
        n = struct.unpack("!Q", _pontosan(rfile, 8))[0]
    if opcode >= 0x8 and (n > 125 or not fin):
        raise ProtocolError("szabálytalan vezérlőkeret")
    if not fin or opcode == 0x0:
        raise ProtocolError("töredezett üzenet nem támogatott")
    if n > MAX_BE:
        raise ProtocolError("túl nagy keret")
    mask = _pontosan(rfile, 4)
    data = bytearray(_pontosan(rfile, n))
    for i in range(n):
        data[i] ^= mask[i & 3]
    return opcode, bytes(data)


class Connection:
    """Egy felépült WS-kapcsolat. A küldés szálbiztos (az eseményszál és az olvasószál is írhat)."""

    def __init__(self, sock: socket.socket, rfile, wfile):
        self.sock, self.rfile, self.wfile = sock, rfile, wfile
        self._wlock = threading.Lock()
        self.closed = False

    def _write(self, data: bytes) -> None:
        with self._wlock:
            if self.closed:
                raise ConnectionError("a kapcsolat zárva")
            self.wfile.write(data)
            self.wfile.flush()

    def send_json(self, obj) -> None:
        self._write(frame(OP_TEXT, json.dumps(obj, ensure_ascii=False).encode("utf-8")))

    def close(self, code: int = 1000) -> None:
        """A kapcsolat lezárása (T003): a zárókeret legfeljebb ~1,5 s-ig próbál kimenni (egy nem olvasó kliens miatt a
        küldés nem blokkolhat korlát nélkül, és az író szál `_wlock`-ját sem várjuk), a végén **mindig** `shutdown`
        (SHUT_RDWR): ez oldja fel a blokkoló olvasót és a blokkoló írót is, így a kezelőszálak véget érnek."""
        megvan = self._wlock.acquire(timeout=0.5)
        try:
            if megvan and not self.closed:
                try:
                    self.sock.settimeout(1.0)
                    self.wfile.write(frame(OP_CLOSE, struct.pack("!H", code)))
                    self.wfile.flush()
                except (OSError, ConnectionError, ValueError):
                    pass
        finally:
            self.closed = True
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            if megvan:
                self._wlock.release()

    def serve_incoming(self, on_text=lambda s: None) -> None:
        """Az olvasóhurok: ping → pong, close → close, szöveg → `on_text`. A kapcsolat végéig fut."""
        try:
            while not self.closed:
                op, data = read_frame(self.rfile)
                if op == OP_PING:
                    self._write(frame(OP_PONG, data))
                elif op == OP_CLOSE:
                    code = struct.unpack("!H", data[:2])[0] if len(data) >= 2 else 1000
                    self.close(code if code in (1000, 1001) else 1000)
                elif op == OP_TEXT:
                    on_text(data.decode("utf-8", errors="replace"))
                elif op == OP_PONG:
                    pass
                else:
                    raise ProtocolError("nem támogatott opkód")
        except ProtocolError:
            self.close(1002)
        except (OSError, ConnectionError, ValueError):
            self.closed = True
