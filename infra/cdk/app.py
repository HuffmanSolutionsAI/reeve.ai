#!/usr/bin/env python3
"""CDK entry point. Stacks deployed today: AuditStack.

Future stacks (deferred per build order §8): ProposalsStack (Cole), API
runtime stack (Step 4), Mongo connectivity (likely external — Atlas)."""
import os

import aws_cdk as cdk

from stacks.audit_stack import AuditStack

app = cdk.App()

AuditStack(
    app,
    "ReeveAuditStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),
    ),
)

app.synth()
