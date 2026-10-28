import re

from sqlalchemy import select

from app.extensions import db
from app.models import AckStatus, Assignment, AssetStatus, AuditLog, User


def test_pages_require_login(app, data):
    resp = app.test_client().get("/assets/")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_lockout_after_five_failures(app, data):
    client = app.test_client()
    for _ in range(5):
        client.post("/login", data={"email": "mgr@test.example", "password": "wrong-password!"})
    resp = client.post("/login", data={"email": "mgr@test.example", "password": "correct-horse-battery"})
    assert resp.status_code == 429
    assert db.session.scalar(select(User).where(User.email == "mgr@test.example")).locked_until


def test_main_pages_render(client):
    for url in ["/", "/assets/", "/assets/1", "/assets/new", "/employees/", "/employees/1",
                "/assignments/", "/reports/", "/audit/", "/assets/?export=csv"]:
        assert client.get(url).status_code == 200, url
    for slug in ["inventory", "by-employee", "warranty", "aging", "financial", "disposals"]:
        assert client.get(f"/reports/{slug}").status_code == 200, slug
        assert client.get(f"/reports/{slug}?export=csv").mimetype == "text/csv"


def test_checkout_and_employee_acceptance_flow(client, data):
    resp = client.post("/assets/1/checkout", data={"employee_id": data["employee"].id, "condition": "Good"},
                       follow_redirects=True)
    assert b"checked out to Erika Mustermann" in resp.data
    token = re.search(rb"/ack/([\w-]+)", resp.data).group(1).decode()

    public = client.application.test_client()
    page = public.get(f"/ack/{token}")
    assert b"Please confirm receipt" in page.data
    wrong = public.post(f"/ack/{token}", data={"choice": "accept", "typed_name": "Someone Else"})
    assert b"Type your full name" in wrong.data
    # Even from a browser with an IT session, the response is the employee's, not the manager's.
    ok = client.post(f"/ack/{token}", data={"choice": "accept", "typed_name": "erika mustermann"})
    assert b"You have confirmed receipt" in ok.data
    entry = db.session.scalar(select(AuditLog).where(AuditLog.action == "ack_accepted"))
    assert entry.user_id is None and entry.asset_id == data["asset"].id

    ack = db.session.scalar(select(Assignment)).acknowledgement
    assert ack.status == AckStatus.ACCEPTED and ack.typed_name == "erika mustermann" and ack.ip_address
    assert public.get(f"/ack/{token}").status_code == 404  # single use


def test_retire_while_assigned_shows_rule(client, data):
    client.post("/assets/1/checkout", data={"employee_id": data["employee"].id})
    resp = client.post("/assets/1/retire", data={"reason": "End of life"}, follow_redirects=True)
    assert b"before retiring it" in resp.data
    assert data["asset"].status == AssetStatus.ASSIGNED
