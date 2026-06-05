from .client import (
    DynamoProposalsClient,
    MongoProposalsClient,
    ProposalClientProtocol,
    get_client,
    set_default,
)

__all__ = [
    "DynamoProposalsClient",
    "MongoProposalsClient",
    "ProposalClientProtocol",
    "get_client",
    "set_default",
]
