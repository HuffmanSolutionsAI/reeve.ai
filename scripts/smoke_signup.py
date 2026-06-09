"""Smoke for Phase-1 identity plumbing: signup, /me read+patch,
buy-box patch, cascade delete, and the post-delete 401 on /me.

No agent dispatch involved — this exercises the REST surface that the
SignupScreen + Settings view will use."""
from __future__ import annotations

import asyncio
import os
from typing import Any

os.environ.setdefault("AUDIT_BACKEND", "mongo")
os.environ.setdefault("PROPOSALS_BACKEND", "mongo")

from mongomock_motor import AsyncMongoMockClient

import reeve.audit as audit_mod
import reeve.db.mongo as mongo_module
import reeve.proposals as proposals_mod
from reeve.models import (
    Building,
    Deal,
    DealSource,
    DealStatus,
    Portfolio,
    Unit,
    UnitStatus,
)
from reeve.models.stubs import (
    Lease,
    LeaseStatus,
    Tenant,
    TenantContact,
    Transaction,
    Vendor,
)
from reeve.repos.deals import upsert_deal
from reeve.repos.leases import upsert_lease
from reeve.repos.tenants import upsert_tenant
from reeve.repos.transactions import insert_transactions
from reeve.repos.vendors import upsert_vendor


def install_mock_db() -> AsyncMongoMockClient:
    client = AsyncMongoMockClient()
    mongo_module._client = client
    proposals_mod.set_default(None)
    return client


class _InMemoryAudit:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, **kw: Any) -> Any:
        from reeve.audit import AuditEvent
        ev = AuditEvent(**kw)
        self.events.append(ev.model_dump())
        return ev

    def write(self, e: Any) -> Any:
        self.events.append(e.model_dump() if hasattr(e, "model_dump") else e)
        return e

    def feed(self, investor_id: str, *, limit: int = 50) -> list[dict]:
        return [e for e in self.events if e.get("investor_id") == investor_id][:limit]

    def by_entity(self, *a: Any, **k: Any) -> list[dict]:
        return []


def install_mock_audit() -> _InMemoryAudit:
    sink = _InMemoryAudit()
    audit_mod.set_default(sink)
    return sink


async def _seed_data_for(investor_id: str) -> None:
    """Populate every cascade target so the delete count is non-trivial."""
    portfolio = Portfolio(investor_id=investor_id, name="Oakwood")
    await mongo_module.db()["portfolios"].insert_one(portfolio.model_dump(by_alias=True))
    building = Building(portfolio_id=portfolio.id, address="412 Lincoln St", units_count=4)
    await mongo_module.db()["buildings"].insert_one(building.model_dump(by_alias=True))
    for i in range(4):
        unit = Unit(
            building_id=building.id, label=f"{(i // 2) + 1}{'AB'[i % 2]}",
            market_rent=1466, status=UnitStatus.OCCUPIED,
        )
        await mongo_module.db()["units"].insert_one(unit.model_dump(by_alias=True))
    await upsert_deal(Deal(
        investor_id=investor_id, address="1423 Elmwood",
        source=DealSource.MANUAL, status=DealStatus.SOURCED,
    ))
    tenant = Tenant(
        investor_id=investor_id, name="Priya Nair",
        contacts=[TenantContact(kind="email", value="priya@example.com")],
    )
    await upsert_tenant(tenant)
    await upsert_lease(Lease(
        investor_id=investor_id, unit_id="some-unit", tenant_id=tenant.id,
        term_start="2025-09-01", term_end="2026-08-31", rent=1350.0,
        status=LeaseStatus.ACTIVE,
    ))
    await upsert_vendor(Vendor(
        investor_id=investor_id, name="ACME Plumbing", trades=["plumbing"],
    ))
    await insert_transactions([Transaction(
        investor_id=investor_id, building_id=building.id,
        date="2026-04-01", amount=-180.0, description="Plumbing repair",
        plaid_id=f"x-{investor_id[:8]}-1",
    )])


async def main() -> None:
    print("smoke_signup:")
    install_mock_db()
    install_mock_audit()
    # Keep password hashing fast in tests.
    from reeve.config import settings
    settings.password_iterations = 50_000

    from fastapi.testclient import TestClient
    from reeve.api import build_app

    app = build_app()
    with TestClient(app) as client:
        # ---- 1) POST /api/auth/signup ---------------------------------------
        r = client.post("/api/auth/signup", json={
            "email": "jake@test.example",
            "password": "hunter2hunter2",
            "name": "Jake Test",
            "entity_name": "Test Holdings",
            "buy_box": {
                "cap_floor": 0.075,
                "min_dscr": 1.25,
                "target_coc": 0.08,
                "markets": ["Westfield, NJ", "Summit, NJ"],
                "unit_range": [4, 16],
                "price_range": [500000, 2000000],
            },
        })
        assert r.status_code == 200, r.text
        body = r.json()
        token = body["access_token"]
        investor_id = body["investor_id"]
        print(f"  /signup: created investor {investor_id[:8]}…")

        client.headers.update({"Authorization": f"Bearer {token}"})

        # ---- 2) GET /api/me reflects the signup payload, NO password hash ---
        r = client.get("/api/me")
        assert r.status_code == 200
        me = r.json()
        assert me["name"] == "Jake Test"
        assert me["entity_name"] == "Test Holdings"
        assert me["email"] == "jake@test.example"
        assert "password" not in me, "password hash leaked in /me response!"
        assert me["buy_box"]["cap_floor"] == 0.075
        assert me["buy_box"]["markets"] == ["Westfield, NJ", "Summit, NJ"]
        assert me["buy_box"]["unit_range"] == [4, 16]
        print(f"  /me: name={me['name']!r}, email={me['email']!r}, password hidden")

        # ---- 2b) Duplicate email → 409 -------------------------------------
        dup = TestClient(app).post("/api/auth/signup", json={
            "email": "JAKE@test.example",  # case-insensitive dedupe
            "password": "anotherpassword",
            "name": "Impostor",
        })
        assert dup.status_code == 409, dup.status_code
        print("  duplicate email (case-insensitive) → 409")

        # ---- 2c) Bad email / short password → 422 --------------------------
        bad_email = TestClient(app).post("/api/auth/signup", json={
            "email": "not-an-email", "password": "longenough1", "name": "X",
        })
        assert bad_email.status_code == 422
        short_pw = TestClient(app).post("/api/auth/signup", json={
            "email": "ok@test.example", "password": "short", "name": "X",
        })
        assert short_pw.status_code == 422
        print("  invalid email + short password → 422")

        # ---- 3) PATCH /api/me updates only what was sent -------------------
        r = client.patch("/api/me", json={"entity_name": "Test Holdings LLC"})
        assert r.status_code == 200
        assert r.json()["entity_name"] == "Test Holdings LLC"
        # Name and buy-box untouched
        assert r.json()["name"] == "Jake Test"
        assert r.json()["buy_box"]["cap_floor"] == 0.075
        print("  PATCH /me: entity_name updated, other fields untouched")

        # ---- 4) PATCH /api/me/buy-box is a true partial patch --------------
        r = client.patch("/api/me/buy-box", json={"min_dscr": 1.30, "markets": ["Columbus, OH"]})
        assert r.status_code == 200
        bb = r.json()["buy_box"]
        assert bb["min_dscr"] == 1.30
        assert bb["markets"] == ["Columbus, OH"]
        # Other buy-box fields untouched
        assert bb["cap_floor"] == 0.075
        assert bb["target_coc"] == 0.08
        assert bb["unit_range"] == [4, 16]
        print(f"  PATCH /me/buy-box: min_dscr={bb['min_dscr']}, "
              f"markets={bb['markets']}, others untouched")

        # ---- 5) Empty PATCH bodies → 400 -----------------------------------
        r = client.patch("/api/me", json={})
        assert r.status_code == 400
        r = client.patch("/api/me/buy-box", json={})
        assert r.status_code == 400
        print("  empty patches → 400")

        # ---- 6) Seed every cascade target, then DELETE /me -----------------
        await _seed_data_for(investor_id)
        r = client.delete("/api/me")
        assert r.status_code == 200, r.text
        body = r.json()
        counts = body["counts"]
        # Investors row is gone, plus everything we seeded
        assert counts["investors"] == 1
        assert counts["portfolios"] == 1
        assert counts["buildings"] == 1
        assert counts["units"] == 4
        assert counts["deals"] == 1
        assert counts["transactions"] == 1
        assert counts["leases"] == 1
        assert counts["tenants"] == 1
        assert counts["vendors"] == 1
        print(f"  DELETE /me wiped: {counts}")

        # ---- 7) /me after delete → 401 (token references a vanished investor)
        r = client.get("/api/me")
        assert r.status_code == 401
        print("  post-delete /me → 401 (vanished investor)")

        # ---- 8) Signup is required to be auth-free --------------------------
        # Mint a fresh signup without any auth header — works.
        fresh = TestClient(app)  # no headers
        r = fresh.post("/api/auth/signup", json={
            "email": "another@test.example", "password": "anotherpassword",
            "name": "Another User",
        })
        assert r.status_code == 200, r.text
        # GET /me with no token → 401
        r = fresh.get("/api/me")
        assert r.status_code == 401
        print("  signup is public; /me still requires a token")

    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
