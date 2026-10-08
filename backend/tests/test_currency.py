import pathlib

from app.currency import CURRENCIES, exponent, format_minor, typescript_table


def test_formatting_respects_the_number_of_minor_digits():
    assert format_minor(1000, "USD") == "10.00 USD"
    assert format_minor(1000, "JPY") == "1000 JPY"
    assert format_minor(1500, "KWD") == "1.500 KWD"
    assert format_minor(-5, "EUR") == "-0.05 EUR"
    assert exponent("jpy") == 0 and exponent("BHD") == 3 and exponent("ZZZ") == 2


def test_group_currency_is_validated_and_normalised(client, api):
    u = api.user()
    ok = client.post("/api/groups", json={"name": "T", "currency": "jpy"}, headers=u["h"])
    assert ok.status_code == 201 and ok.json()["currency"] == "JPY"
    assert client.post("/api/groups", json={"name": "T", "currency": "XYZ"}, headers=u["h"]).status_code == 422
    assert client.post("/api/groups", json={"name": "T", "currency": "ab"}, headers=u["h"]).status_code == 422


def test_reminder_and_summary_text_use_the_right_decimals(client, api, db):
    from sqlalchemy import select

    from app.models import Outbox

    a, b = api.user(), api.user()
    g = api.group(a, [b], currency="KWD")
    api.expense(g, a, a, 3001, api.equal([a["id"], b["id"]]))  # 3.001 KWD
    client.post(f"/api/groups/{g['id']}/close", headers=a["h"])
    mail = db.scalar(select(Outbox).where(Outbox.group_id == g["id"], Outbox.kind == "close_summary", Outbox.to_email == a["email"]))
    assert "Total spent: 3.001 KWD" in mail.body
    assert "pays" in mail.body and ("1.500 KWD" in mail.body or "1.501 KWD" in mail.body)


def test_frontend_currency_table_is_in_sync_with_the_backend():
    path = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "currencies.ts"
    assert path.read_text() == typescript_table(), "run: cd backend && uv run python scripts/gen_currencies.py"
    assert len(CURRENCIES) > 150
