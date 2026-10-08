"""Behind a proxy the throttle must key on the real client address, or one stranger can lock anyone out."""
from app import config


def _bad(client, email, ip=None):
    headers = {"x-forwarded-for": ip} if ip else {}
    return client.post("/api/auth/login", json={"email": email, "password": "wrong-pass"}, headers=headers).status_code


def test_with_trusted_proxy_each_client_address_has_its_own_bucket(client, api, monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", True)
    victim = api.user()
    for _ in range(config.LOGIN_MAX_FAILURES):
        assert _bad(client, victim["email"], "203.0.113.7") == 401  # a stranger guesses
    assert _bad(client, victim["email"], "203.0.113.7") == 429      # ... and is stopped
    ok = client.post("/api/auth/login", json={"email": victim["email"], "password": "secret1"}, headers={"x-forwarded-for": "198.51.100.9"})
    assert ok.status_code == 200  # the real owner, from another address, is NOT locked out


def test_without_a_trusted_proxy_the_header_is_ignored_so_it_cannot_be_used_to_dodge_the_limit(client, api, monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", False)
    u = api.user()
    for i in range(config.LOGIN_MAX_FAILURES):
        assert _bad(client, u["email"], f"10.0.0.{i}") == 401
    assert _bad(client, u["email"], "10.9.9.9") == 429  # changing the spoofed header does not help


def test_dev_mailbox_can_be_switched_off(client, api, monkeypatch):
    u = api.user()
    assert client.get("/api/me/outbox", headers=u["h"]).status_code == 200
    monkeypatch.setattr(config, "DEV_MAILBOX", False)
    assert client.get("/api/me/outbox", headers=u["h"]).status_code == 404
