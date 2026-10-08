"""Two real HTTP clients open at once: both must see a change immediately via the live stream."""
import json
import threading

import httpx


def _listen(base: str, token: str, got: list, ready: threading.Event, stop: threading.Event):
    with httpx.stream("GET", f"{base}/api/stream", params={"access_token": token}, timeout=30) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                event = json.loads(line[5:])
                if event["type"] == "hello":
                    ready.set()
                else:
                    got.append(event)
                    return
            if stop.is_set():
                return


def test_two_clients_both_get_live_update(live_server):
    base = live_server

    def reg(n):
        r = httpx.post(f"{base}/api/auth/register", json={"email": f"live{n}@ex.com", "name": f"L{n}", "password": "secret1"})
        d = r.json()
        return d["user"]["id"], d["token"]

    (a, ta), (b, tb) = reg(1), reg(2)
    ha, hb = {"Authorization": f"Bearer {ta}"}, {"Authorization": f"Bearer {tb}"}
    g = httpx.post(f"{base}/api/groups", json={"name": "L", "currency": "USD"}, headers=ha).json()
    httpx.post(f"{base}/api/join/{g['invite_token']}", headers=hb)

    stop = threading.Event()
    got_a, got_b, ready_a, ready_b = [], [], threading.Event(), threading.Event()
    threads = [
        threading.Thread(target=_listen, args=(base, ta, got_a, ready_a, stop), daemon=True),
        threading.Thread(target=_listen, args=(base, tb, got_b, ready_b, stop), daemon=True),
    ]
    for t in threads:
        t.start()
    assert ready_a.wait(5) and ready_b.wait(5)

    r = httpx.post(
        f"{base}/api/groups/{g['id']}/expenses",
        json={"payer_id": a, "amount_minor": 999, "spent_on": "2026-10-01", "split": {"type": "equal", "participants": [a, b]}},
        headers=ha,
    )
    assert r.status_code == 201
    for t in threads:
        t.join(timeout=5)
    stop.set()
    assert got_a and got_b
    assert got_a[0]["group_id"] == g["id"] == got_b[0]["group_id"] and got_b[0]["kind"] == "expense_added"
