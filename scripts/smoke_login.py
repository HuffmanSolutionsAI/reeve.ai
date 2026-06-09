"""Login + password smoke: email/password login, wrong-password rejection,
change-password, and that the old password stops working after a change.

No agent dispatch — this is the auth surface the LoginScreen + Settings
password form use."""
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("AUDIT_BACKEND", "mongo")
os.environ.setdefault("PROPOSALS_BACKEND", "mongo")

from mongomock_motor import AsyncMongoMockClient

import reeve.audit as audit_mod
import reeve.db.mongo as mongo_module
import reeve.proposals as proposals_mod
from reeve.config import settings


def install_mock_db() -> AsyncMongoMockClient:
    client = AsyncMongoMockClient()
    mongo_module._client = client
    proposals_mod.set_default(None)
    return client


class _NullAudit:
    def emit(self, **kw): return None
    def write(self, e): return e
    def feed(self, *a, **k): return []
    def by_entity(self, *a, **k): return []


def main() -> None:
    print("smoke_login:")
    install_mock_db()
    audit_mod.set_default(_NullAudit())
    settings.password_iterations = 50_000  # fast in tests

    from fastapi.testclient import TestClient
    from reeve.api import build_app

    app = build_app()
    with TestClient(app) as client:
        EMAIL = "investor@example.com"
        PW = "correct horse battery"

        # ---- signup -------------------------------------------------------
        r = client.post("/api/auth/signup", json={
            "email": EMAIL, "password": PW, "name": "Test Investor",
        })
        assert r.status_code == 200, r.text
        investor_id = r.json()["investor_id"]
        print(f"  signup: {investor_id[:8]}…")

        # ---- login with correct creds ------------------------------------
        r = client.post("/api/auth/login", json={"email": EMAIL, "password": PW})
        assert r.status_code == 200, r.text
        assert r.json()["investor_id"] == investor_id
        token = r.json()["access_token"]
        print("  login (correct password) → 200, token issued")

        # ---- login is case-insensitive on email --------------------------
        r = client.post("/api/auth/login", json={"email": "INVESTOR@example.com", "password": PW})
        assert r.status_code == 200
        print("  login email is case-insensitive")

        # ---- wrong password → 401 ----------------------------------------
        r = client.post("/api/auth/login", json={"email": EMAIL, "password": "wrong"})
        assert r.status_code == 401, r.status_code
        print("  login (wrong password) → 401")

        # ---- unknown email → 401 (same as wrong password, no enumeration)-
        r = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": PW})
        assert r.status_code == 401
        print("  login (unknown email) → 401 (no account enumeration)")

        # ---- change password requires the current one --------------------
        h = {"Authorization": f"Bearer {token}"}
        r = client.patch("/api/me/password",
                         json={"current_password": "wrong", "new_password": "newpassword123"},
                         headers=h)
        assert r.status_code == 403, r.status_code
        print("  change-password (wrong current) → 403")

        NEW_PW = "a-brand-new-password"
        r = client.patch("/api/me/password",
                         json={"current_password": PW, "new_password": NEW_PW},
                         headers=h)
        assert r.status_code == 200, r.text
        print("  change-password (correct current) → 200")

        # ---- old password no longer works; new one does ------------------
        r = client.post("/api/auth/login", json={"email": EMAIL, "password": PW})
        assert r.status_code == 401, "old password still works!"
        r = client.post("/api/auth/login", json={"email": EMAIL, "password": NEW_PW})
        assert r.status_code == 200, r.text
        print("  old password rejected, new password accepted")

        # ---- dev-token still works (backdoor enabled in dev) -------------
        r = client.post("/api/auth/dev-token", json={"investor_id": investor_id})
        assert r.status_code == 200
        print("  dev-token still issues a token by id")

        # ---- dev-token disabled → 404 ------------------------------------
        settings.enable_dev_token = False
        r = client.post("/api/auth/dev-token", json={"investor_id": investor_id})
        assert r.status_code == 404
        settings.enable_dev_token = True
        print("  dev-token returns 404 when disabled")

    print("ok.")


if __name__ == "__main__":
    main()
