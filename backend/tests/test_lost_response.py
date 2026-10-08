"""The nastiest failure: the server committed the expense, then the connection died before the client heard about it.

A tiny TCP proxy sits between the client and a real server and, on demand, swallows the response (closes the client's
connection after the server has answered). The client sees an error, although the expense exists. Without a key a retry
makes a second expense; with the Idempotency-Key the retry returns the original.
"""
from __future__ import annotations

import socket
import threading
import uuid

import httpx
from sqlalchemy import func, select

from app.models import Expense


class DroppingProxy:
    def __init__(self, upstream_port: int):
        self.upstream_port = upstream_port
        self.drop_next_response = False
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                client, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(client,), daemon=True).start()

    def _serve(self, client: socket.socket):
        upstream = socket.create_connection(("127.0.0.1", self.upstream_port))
        try:
            request = client.recv(1 << 20)
            while request and b"\r\n\r\n" not in request:
                request += client.recv(1 << 20)
            head, _, rest = request.partition(b"\r\n\r\n")
            length = next((int(h.split(b":")[1]) for h in head.split(b"\r\n") if h.lower().startswith(b"content-length")), 0)
            while len(rest) < length:
                rest += client.recv(1 << 20)
            # Ask the server to close the connection after answering, so "the whole response" is simply "everything until EOF".
            # (A single recv() can return just the headers when the network is slow: that is what broke this on CI.)
            lines = [h for h in head.split(b"\r\n") if not h.lower().startswith(b"connection:")]
            upstream.sendall(b"\r\n".join(lines) + b"\r\nConnection: close\r\n\r\n" + rest)
            response = b""
            while chunk := upstream.recv(1 << 16):
                response += chunk
            # the server has now handled (and committed) the request and finished answering
            if self.drop_next_response:
                self.drop_next_response = False
                return  # close both sockets without telling the client anything
            client.sendall(response)
        finally:
            upstream.close()
            client.close()

    def close(self):
        self.sock.close()


def _body(a, b):
    return {"payer_id": a["id"], "amount_minor": 1000, "title": "x", "category": "food", "spent_on": "2026-10-01",
            "split": {"type": "equal", "participants": [a["id"], b["id"]]}}


def _setup(base):
    def reg(tag):
        r = httpx.post(f"{base}/api/auth/register", json={"email": f"{tag}{uuid.uuid4().hex[:8]}@example.com", "name": tag, "password": "secret1"}).json()
        return {"id": r["user"]["id"], "h": {"Authorization": f"Bearer {r['token']}"}}

    a, b = reg("lost-a"), reg("lost-b")
    g = httpx.post(f"{base}/api/groups", json={"name": "L", "currency": "USD"}, headers=a["h"]).json()
    httpx.post(f"{base}/api/join/{g['invite_token']}", headers=b["h"])
    return a, b, g


def _count(db, gid):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Expense).where(Expense.group_id == gid))


def test_lost_response_with_a_key_the_retry_returns_the_original(live_server, db):
    proxy = DroppingProxy(int(live_server.rsplit(":", 1)[1]))
    try:
        a, b, g = _setup(live_server)
        url = f"http://127.0.0.1:{proxy.port}/api/groups/{g['id']}/expenses"
        key = {"Idempotency-Key": uuid.uuid4().hex}
        proxy.drop_next_response = True
        try:
            httpx.post(url, json=_body(a, b), headers={**a["h"], **key}, timeout=10)
            raise AssertionError("the client should have seen a broken connection")
        except httpx.TransportError:
            pass
        assert _count(db, g["id"]) == 1  # ...although the server DID save it
        retry = httpx.post(url, json=_body(a, b), headers={**a["h"], **key}, timeout=10)
        assert retry.status_code == 201
        assert _count(db, g["id"]) == 1  # the retry did not make a second one
        view = httpx.get(f"{live_server}/api/groups/{g['id']}", headers=a["h"]).json()
        assert {m["id"]: m["balance_minor"] for m in view["members"]} == {a["id"]: 500, b["id"]: -500}
    finally:
        proxy.close()


def test_the_same_lost_response_without_a_key_does_duplicate_which_is_why_the_client_sends_one(live_server, db):
    proxy = DroppingProxy(int(live_server.rsplit(":", 1)[1]))
    try:
        a, b, g = _setup(live_server)
        url = f"http://127.0.0.1:{proxy.port}/api/groups/{g['id']}/expenses"
        proxy.drop_next_response = True
        try:
            httpx.post(url, json=_body(a, b), headers=a["h"], timeout=10)
        except httpx.TransportError:
            pass
        httpx.post(url, json=_body(a, b), headers=a["h"], timeout=10)
        assert _count(db, g["id"]) == 2  # documents the problem the key solves
    finally:
        proxy.close()
