from __future__ import annotations

from ..db.mongo import COLLECTIONS, db
from ..models.artifact import Artifact, ArtifactType, Confidence


async def write_artifact(
    *,
    type: ArtifactType,
    payload: dict,
    produced_by: str,
    agent_run_id: str,
    deal_id: str | None = None,
    inputs: dict | None = None,
    assumptions: list[str] | None = None,
    confidence: Confidence = Confidence.MEDIUM,
    unverified: list[str] | None = None,
    supersedes: str | None = None,
) -> Artifact:
    """Append a versioned, immutable artifact. A revision is a NEW document
    with `supersedes` pointing at the prior — never an in-place edit."""
    coll = db()[COLLECTIONS["artifacts"]]
    version = 1
    if supersedes:
        prior = await coll.find_one({"_id": supersedes})
        if prior:
            version = int(prior.get("version", 1)) + 1

    artifact = Artifact(
        type=type,
        version=version,
        produced_by=produced_by,
        agent_run_id=agent_run_id,
        payload=payload,
        inputs=inputs or {},
        assumptions=assumptions or [],
        confidence=confidence,
        unverified=unverified or [],
        deal_id=deal_id,
        supersedes=supersedes,
    )
    await coll.insert_one(artifact.model_dump(by_alias=True))
    return artifact
