import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import User, Team, Membership, WorkItem
from app.security import hash_password

@pytest.fixture()
def test_context():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False}, future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    ops = Team(name="Test Operations")
    finance = Team(name="Test Finance")
    db.add_all([ops, finance]); db.flush()
    admin = User(email="admin@test.local", name="Admin Tester", password_hash=hash_password("AdminPass!2026"))
    lead = User(email="lead@test.local", name="Lead Tester", password_hash=hash_password("LeadPass!2026"))
    member = User(email="member@test.local", name="Member Tester", password_hash=hash_password("MemberPass!2026"))
    viewer = User(email="viewer@test.local", name="Viewer Tester", password_hash=hash_password("ViewerPass!2026"))
    outsider = User(email="outsider@test.local", name="Outsider Tester", password_hash=hash_password("OutsidePass!2026"))
    db.add_all([admin, lead, member, viewer, outsider]); db.flush()
    db.add_all([
        Membership(user_id=admin.id, team_id=ops.id, role="Admin"),
        Membership(user_id=admin.id, team_id=finance.id, role="Admin"),
        Membership(user_id=lead.id, team_id=ops.id, role="Lead"),
        Membership(user_id=member.id, team_id=ops.id, role="Member"),
        Membership(user_id=viewer.id, team_id=ops.id, role="Viewer"),
        Membership(user_id=outsider.id, team_id=finance.id, role="Member"),
    ])
    db.commit()
    db.close()
    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield {"client": client, "ops_id": ops.id, "finance_id": finance.id, "engine": engine}
    app.dependency_overrides.clear()
    engine.dispose()
    try: os.unlink(path)
    except OSError: pass

def login(client, email="member@test.local", password="MemberPass!2026"):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

@pytest.fixture
def ctx(test_context):
    test_context["login"] = login
    return test_context
