#!/usr/bin/env python3
"""Tiny local DNS forwarder bridging to DNS-over-HTTPS (stdlib only).

Why: on Fly machines the built-in resolver (fdaa::3) does not return MX
records and public DNS (UDP/TCP 53) is blocked, while HTTPS egress works.
Postfix needs MX lookups to deliver mail, so this bridge answers on
127.0.0.1:53 by querying DoH JSON endpoints (dns.google, Cloudflare fallback)
and re-encoding the answers as plain DNS.
"""

import json
import socket
import struct
import threading
import time
import urllib.request
from typing import TypedDict

# Use the DoH IP literals directly: 8.8.8.8 and 1.1.1.1 serve certificates valid
# for dns.google / cloudflare-dns.com, so the bridge never needs DNS itself
# (its own resolv.conf points at the bridge — resolving the hostname would
# recurse).
UPSTREAMS = (
    "https://8.8.8.8/resolve",
    "https://1.1.1.1/dns-query",
)


class DohAnswer(TypedDict):
    type: int
    TTL: int
    data: str


class DohResponse(TypedDict):
    Status: int
    Answer: list[DohAnswer]


def encode_name(name: str) -> bytes:
    return b"".join(bytes([len(p)]) + p.encode() for p in name.rstrip(".").split(".")) + b"\x00"


def parse_name(msg: bytes, off: int) -> tuple[str, int]:
    labels: list[str] = []
    while True:
        length = msg[off]
        if length == 0:
            return ".".join(labels) + ".", off + 1
        if length & 0xC0 == 0xC0:
            ptr = struct.unpack(">H", msg[off : off + 2])[0] & 0x3FFF
            name, _ = parse_name(msg, ptr)
            return name, off + 2
        labels.append(msg[off + 1 : off + 1 + length].decode())
        off += 1 + length


def rdata_for(qtype: int, data: str) -> bytes:
    if qtype == 1:  # A
        return socket.inet_aton(data)
    if qtype == 28:  # AAAA
        return socket.inet_pton(socket.AF_INET6, data)
    if qtype in (2, 5, 12):  # NS, CNAME, PTR
        return encode_name(data)
    if qtype == 15:  # MX: "10 alt1.gmail-smtp-in.l.google.com."
        preference, exchange = data.split(" ", 1)
        return struct.pack(">H", int(preference)) + encode_name(exchange)
    if qtype == 16:  # TXT: JSON array of quoted strings
        parts = json.loads(data)
        return b"".join(bytes([len(p)]) + p.encode() for p in parts)
    if qtype == 6:  # SOA: mname rname serial refresh retry expire minimum
        mname, rname, *nums = data.split(" ")
        return (
            encode_name(mname)
            + encode_name(rname)
            + b"".join(struct.pack(">I", int(n)) for n in nums)
        )
    return b""


def doh_query(name: str, qtype: int) -> DohResponse:
    for base in UPSTREAMS:
        try:
            request = urllib.request.Request(
                f"{base}?name={name}&type={qtype}",
                headers={"accept": "application/dns-json"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                result: DohResponse = json.load(response)
                return result
        except Exception:
            continue
    return {"Status": 2, "Answer": []}


def handle_query(packet: bytes) -> bytes:
    tid, _flags, _qd = struct.unpack(">HHH", packet[:6])
    off = 12
    qname, off = parse_name(packet, off)
    qtype, _qclass = struct.unpack(">HH", packet[off : off + 4])
    result = doh_query(qname, qtype)
    status = result["Status"]
    answers = result.get("Answer", [])  # DoH omits Answer on NODATA
    rcode = status if status in (0, 3) else 2
    header = struct.pack(">HHHHHH", tid, 0x8180 | rcode, 1, len(answers), 0, 0)
    question = packet[12 : off + 4]
    body = b""
    for answer in answers:
        atype = answer["type"]
        ttl = answer["TTL"]
        rdata = rdata_for(atype, answer["data"])
        body += b"\xc0\x0c" + struct.pack(">HHIH", atype, 1, ttl, len(rdata)) + rdata
    return header + question + body


def udp_respond(sock: socket.socket, packet: bytes, addr: tuple[str, int]) -> None:
    sock.sendto(handle_query(packet), addr)


def udp_loop() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 53))
    while True:
        packet, addr = sock.recvfrom(4096)
        threading.Thread(target=udp_respond, args=(sock, packet, addr), daemon=True).start()


def tcp_client(conn: socket.socket) -> None:
    try:
        header = conn.recv(2)
        if len(header) < 2:
            return
        length = struct.unpack(">H", header)[0]
        packet = b""
        while len(packet) < length:
            packet += conn.recv(length - len(packet))
        response = handle_query(packet)
        conn.sendall(struct.pack(">H", len(response)) + response)
    except OSError:
        pass
    finally:
        conn.close()


def tcp_loop() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 53))
    sock.listen(16)
    while True:
        conn, _addr = sock.accept()
        threading.Thread(target=tcp_client, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    threading.Thread(target=udp_loop, daemon=True).start()
    threading.Thread(target=tcp_loop, daemon=True).start()
    while True:
        time.sleep(3600)
