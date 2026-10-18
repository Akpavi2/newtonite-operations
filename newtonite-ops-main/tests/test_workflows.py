from concurrent.futures import ThreadPoolExecutor
from app.database import Base
from app.models import WorkItem, ActivityEvent
from .conftest import login


def create_item(client, headers, team_id, **overrides):
    payload = {"title": "Investigate failed payment", "description": "Customer reports a delayed refund.", "item_type": "payment", "priority": "Urgent", "team_id": team_id}
    payload.update(overrides)
    response = client.post("/api/items", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_login_and_create_item(ctx):
    client = ctx["client"]
    headers = login(client)
    item = create_item(client, headers, ctx["ops_id"])
    fetched = client.get(f"/api/items/{item['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Investigate failed payment"
    assert fetched.json()["status"] == "Open"


def test_claim_can_only_succeed_once(ctx):
    client = ctx["client"]
    headers_a = login(client, "member@test.local", "MemberPass!2026")
    headers_b = login(client, "lead@test.local", "LeadPass!2026")
    item = create_item(client, headers_a, ctx["ops_id"])
    def claim(headers):
        return client.post(f"/api/items/{item['id']}/claim", headers=headers)
    # Fire both requests from separate threads; the conditional database update decides the winner.
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(claim, [headers_a, headers_b]))
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response for response in responses if response.status_code == 200)
    assert winner.json()["assignee_id"] is not None


def test_stale_update_rejected_and_data_preserved(ctx):
    client = ctx["client"]
    headers = login(client)
    item = create_item(client, headers, ctx["ops_id"])
    update1 = client.patch(f"/api/items/{item['id']}", headers=headers, json={"version": 1, "priority": "High"})
    assert update1.status_code == 200
    update2 = client.patch(f"/api/items/{item['id']}", headers=headers, json={"version": 1, "priority": "Low"})
    assert update2.status_code == 409
    current = client.get(f"/api/items/{item['id']}", headers=headers).json()
    assert current["priority"] == "High"
    assert current["version"] == 2


def test_idempotency_key_prevents_duplicate_items(ctx):
    client = ctx["client"]
    headers = {**login(client), "Idempotency-Key": "test-create-payment-001"}
    payload = {"title": "Only one task", "description": "Repeat-safe", "item_type": "task", "priority": "Medium", "team_id": ctx["ops_id"]}
    first = client.post("/api/items", headers=headers, json=payload)
    second = client.post("/api/items", headers=headers, json=payload)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    listing = client.get("/api/items?q=Only%20one%20task", headers=login(client)).json()
    assert listing["total"] == 1


def test_cross_team_access_is_blocked(ctx):
    client = ctx["client"]
    finance_headers = login(client, "outsider@test.local", "OutsidePass!2026")
    ops_headers = login(client, "member@test.local", "MemberPass!2026")
    item = create_item(client, ops_headers, ctx["ops_id"])
    response = client.get(f"/api/items/{item['id']}", headers=finance_headers)
    assert response.status_code == 404
    denied_create = client.post("/api/items", headers=finance_headers, json={"title":"Wrong team task", "team_id":ctx["ops_id"]})
    assert denied_create.status_code == 403


def test_invalid_workflow_transition_is_rejected(ctx):
    client = ctx["client"]
    headers = login(client)
    item = create_item(client, headers, ctx["ops_id"])
    response = client.post(f"/api/items/{item['id']}/transition", headers=headers, json={"version":1,"status":"Closed"})
    assert response.status_code == 422
    assert client.get(f"/api/items/{item['id']}", headers=headers).json()["status"] == "Open"


def test_activity_history_tracks_change(ctx):
    client = ctx["client"]
    headers = login(client)
    item = create_item(client, headers, ctx["ops_id"])
    response = client.patch(f"/api/items/{item['id']}", headers=headers, json={"version":1,"priority":"High"})
    assert response.status_code == 200
    activity = client.get(f"/api/items/{item['id']}/activity", headers=headers)
    assert activity.status_code == 200
    actions = [entry["action"] for entry in activity.json()]
    assert "created" in actions
    assert "priority_changed" in actions


def test_viewer_cannot_create_items(ctx):
    client = ctx["client"]
    headers = login(client, "viewer@test.local", "ViewerPass!2026")
    response = client.post("/api/items", headers=headers, json={"title":"Viewer task", "team_id":ctx["ops_id"]})
    assert response.status_code == 403


def test_transition_activity_records_old_and_new_status(ctx):
    client = ctx["client"]
    headers = login(client)
    item = create_item(client, headers, ctx["ops_id"])
    moved = client.post(f"/api/items/{item['id']}/transition", headers=headers, json={"version": 1, "status": "In Progress"})
    assert moved.status_code == 200
    activity = client.get(f"/api/items/{item['id']}/activity", headers=headers).json()
    transition = next(entry for entry in activity if entry["action"] == "status_changed")
    assert transition["detail"] == "Open → In Progress"
