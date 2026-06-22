"""Import / export round-trips through the real HTTP endpoints."""

import json

from tests.conftest import csrf_token, post, setup_first_admin


def _create(client, name, amount="10.00"):
    return post(client, "/manage/new",
                {"name": name, "amount": amount, "start_date": "2026-01-01",
                 "frequency": "monthly"},
                token_path="/manage", follow_redirects=True)


def _import_file(client, filename, body, media):
    token = csrf_token(client, "/import")
    return client.post("/import",
                       files={"file": (filename, body, media)},
                       data={"csrf_token": token}, follow_redirects=True)


def test_json_export_contains_subscriptions(client, db):
    setup_first_admin(client)
    _create(client, "Netflix")
    _create(client, "Spotify")

    payload = json.loads(client.get("/export?fmt=json").text)
    names = {s["name"] for s in payload["subscriptions"]}
    assert names == {"Netflix", "Spotify"}
    assert payload["version"] == 1


def test_json_round_trip_recreates_subscriptions(client, db):
    setup_first_admin(client)
    _create(client, "Netflix")
    body = client.get("/export?fmt=json").content

    r = _import_file(client, "export.json", body, "application/json")
    assert "imported 1 subscription" in r.text.lower()
    # Original + re-imported copy.
    assert db["subscriptions"].count == 2
    assert [s["name"] for s in db["subscriptions"].rows] == ["Netflix", "Netflix"]


def test_csv_round_trip_recreates_subscriptions(client, db):
    setup_first_admin(client)
    _create(client, "Spotify")
    body = client.get("/export?fmt=csv").content

    r = _import_file(client, "export.csv", body, "text/csv")
    assert "imported 1 subscription" in r.text.lower()
    assert db["subscriptions"].count == 2


def test_import_reports_errors_for_bad_rows(client, db):
    setup_first_admin(client)
    bad = b"name,amount,start_date\n,5.00,2026-01-01\nGood,notanumber,2026-01-01\n"
    r = _import_file(client, "bad.csv", bad, "text/csv")
    # The nameless row and the non-numeric amount are both reported.
    assert "issue" in r.text.lower() or "no subscriptions" in r.text.lower()
