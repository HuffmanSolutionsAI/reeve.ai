"""Auth smoke: token issuance, cross-investor isolation, missing/bad-token rejection."""
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("AUDIT_BACKEND", "mongo")
os.environ.setdefault("PROPOSALS_BACKEND", "mongo")

from mongomock_motor import AsyncMongoMockClient

import reeve.audit as audit_mod
import reeve.db.mongo as mongo_module
import reeve.proposals as proposals_mod
from reeve.models import Deal, DealSource, DealStatus, Investor
from reeve.repos.deals import upsert_deal
from reeve.repos.investors import upsert_investor


def install_mock_db() -> AsyncMongoMockClient:
    client = AsyncMongoMockClient()
    mongo_module._client = client
    proposals_mod.set_default(None)
    return client


class _InMemoryAudit:
    events: list = []
    def emit(self, **kw):
        from reeve.audit import AuditEvent
        ev = AuditEvent(**kw)
        self.events.append(ev)
        return ev
    def write(self, e):
        self.events.append(e); return e
    def feed(self, investor_id, *, limit=50):
        return [e.model_dump() for e in self.events if e.investor_id == investor_id][:limit]
    def by_entity(self, *a, **k): return []


async def _seed_investor(name: str) -> tuple[Investor, Deal]:
    inv = Investor(name=name, email=f"{name.lower()}@test.example")
    await upsert_investor(inv)
    deal = Deal(investor_id=inv.id, address=f"1 {name} St", status=DealStatus.PURSUE,
                source=DealSource.MANUAL)
    await upsert_deal(deal)
    return inv, deal


async def main() -> None:
    print("auth smoke:")
    install_mock_db()
    audit_mod.set_default(_InMemoryAudit())

    alice, alice_deal = await _seed_investor("Alice")
    bob, bob_deal = await _seed_investor("Bob")

    from fastapi.testclient import TestClient
    from reeve.api import build_app
    from reeve.api.auth import issue_token

    app = build_app()
    with TestClient(app) as client:
        # ---- 1) /api/auth/dev-token issues a token for an existing investor ----
        r = client.post("/api/auth/dev-token", json={"investor_id": alice.id})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["token_type"] == "Bearer"
        alice_token = body["access_token"]
        assert body["investor_id"] == alice.id
        print(f"  dev-token issued for Alice ({alice.id[:8]}…)")

        # 404 for an unknown investor.
        r = client.post("/api/auth/dev-token", json={"investor_id": "no-such-investor"})
        assert r.status_code == 404
        print("  dev-token rejects unknown investor (404)")

        # ---- 2) Bearer required on protected endpoints ------------------------
        r = client.get("/api/pipeline")
        assert r.status_code == 401, r.status_code
        r = client.get("/api/pipeline", headers={"Authorization": "Bearer not-a-jwt"})
        assert r.status_code == 401
        print("  missing/bad token → 401 on /api/pipeline")

        # ---- 3) Token gates /api/me to its own investor -----------------------
        r = client.get("/api/me", headers={"Authorization": f"Bearer {alice_token}"})
        assert r.status_code == 200
        assert r.json()["name"] == "Alice"
        print(f"  /api/me with Alice's token returns Alice")

        # ---- 4) Cross-investor isolation --------------------------------------
        bob_token = issue_token(bob.id)["access_token"]
        h_alice = {"Authorization": f"Bearer {alice_token}"}
        h_bob = {"Authorization": f"Bearer {bob_token}"}

        # Alice's pipeline includes her deal but not Bob's; vice versa.
        for headers, expected, forbidden in [
            (h_alice, alice_deal.address, bob_deal.address),
            (h_bob, bob_deal.address, alice_deal.address),
        ]:
            r = client.get("/api/pipeline", headers=headers)
            assert r.status_code == 200
            addrs = {d["address"] for status in r.json()["by_status"].values() for d in status}
            assert expected in addrs and forbidden not in addrs, addrs
        print("  /api/pipeline scoped to the token's investor")

        # ---- 5) Path-id cross-checks: Alice's token on Bob's deal-linked
        # artifact → 404. Use a real artifact so the cross-check fires.
        from reeve.repos.artifacts import write_artifact
        from reeve.models.artifact import ArtifactType, Confidence
        bob_artifact = await write_artifact(
            type=ArtifactType.DEAL_ANALYSIS,
            payload={"type": "deal_analysis", "address": bob_deal.address},
            produced_by="ana", agent_run_id="r1", deal_id=bob_deal.id,
            confidence=Confidence.MEDIUM,
        )
        r = client.get(f"/api/artifacts/{bob_artifact.id}", headers=h_alice)
        assert r.status_code == 404, r.status_code
        r = client.get(f"/api/artifacts/{bob_artifact.id}", headers=h_bob)
        assert r.status_code == 200
        print("  cross-investor artifact request 404s; owner gets 200")

        # ---- 6) Expired token --------------------------------------------------
        expired = issue_token(alice.id, ttl_minutes=-1)["access_token"]
        r = client.get("/api/me", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401 and "expired" in r.text.lower()
        print("  expired token → 401 with 'expired' in body")

    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
