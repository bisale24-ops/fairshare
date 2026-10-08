"""The deployment files carry settings that make an API crash survivable; keep them from being 'cleaned up' by accident."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_nginx_follows_a_restarted_api_and_does_not_wait_a_minute_for_a_dead_one():
    conf = (ROOT / "frontend" / "nginx.conf").read_text()
    assert re.search(r"resolver\s+127\.0\.0\.11", conf), "without a resolver nginx keeps the API's OLD address after a restart"
    assert "set $api backend;" in conf and "proxy_pass http://$api:8000;" in conf, "a variable in proxy_pass makes nginx re-resolve the name"
    assert conf.count("proxy_connect_timeout 3s;") >= 2, "a dead address must fail in seconds, not after the default 60"
    assert "proxy_next_upstream off;" in conf, "never replay a POST behind the client's back"
    assert re.search(r"location = /api/stream \{[^}]*proxy_read_timeout 1h;", conf, re.S)


def test_compose_brings_a_dead_api_back_and_the_image_stops_streams_promptly():
    compose = (ROOT / "docker-compose.yml").read_text()
    backend = compose.split("  backend:")[1].split("\n  web:")[0]
    assert "restart: unless-stopped" in backend
    assert "healthcheck:" in backend
    assert "--timeout-graceful-shutdown" in (ROOT / "backend" / "Dockerfile").read_text()
    assert "USER app" in (ROOT / "backend" / "Dockerfile").read_text()
