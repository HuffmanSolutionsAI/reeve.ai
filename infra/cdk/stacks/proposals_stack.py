"""Proposals queue: DynamoDB table + IAM roles.

Two roles enforce the propose-vs-approve boundary at IAM, not in code:
  - `reeve-app-proposals-writer`     — PutItem (queue) + Query (UI list).
  - `reeve-execution-layer`          — UpdateItem (advance to approved/
                                       rejected/executed) + Query/GetItem.
                                       This is what the API approve/reject
                                       endpoints assume; the agent process
                                       does NOT assume it.

GSI1 (status_created-index) makes the Approvals queue cheap:
  KeyCondition = investor_id = X AND status_created begins_with 'pending#'
"""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    aws_dynamodb as dynamodb,
    aws_iam as iam,
)
from constructs import Construct


class ProposalsStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        table = dynamodb.Table(
            self,
            "Proposals",
            table_name="reeve-proposals",
            partition_key=dynamodb.Attribute(
                name="investor_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="proposal_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
        )
        table.add_global_secondary_index(
            index_name="status_created-index",
            partition_key=dynamodb.Attribute(
                name="investor_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="status_created", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # The agent process can queue proposals (PutItem) and read them
        # (Query for the UI). It cannot UpdateItem — that's how the
        # propose-vs-approve boundary is enforced at the cloud edge.
        app_role = iam.Role(
            self,
            "AppProposalsWriter",
            role_name="reeve-app-proposals-writer",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            ),
            description="Queue proposals (PutItem) + list (Query). No UpdateItem.",
        )
        app_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:PutItem", "dynamodb:Query", "dynamodb:GetItem"],
            resources=[
                table.table_arn,
                f"{table.table_arn}/index/status_created-index",
            ],
        ))

        # The execution layer (the API process that handles /approve and
        # /reject) advances proposals. Deploy this with the API binary, not
        # with the agent loop.
        exec_role = iam.Role(
            self,
            "ExecutionLayer",
            role_name="reeve-execution-layer",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            ),
            description=(
                "Advance proposals (UpdateItem with status condition). "
                "This is the only role that can move a proposal forward."
            ),
        )
        exec_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "dynamodb:GetItem", "dynamodb:Query",
                "dynamodb:UpdateItem",
            ],
            resources=[
                table.table_arn,
                f"{table.table_arn}/index/status_created-index",
            ],
        ))

        cdk.CfnOutput(self, "ProposalsTableName", value=table.table_name)
        cdk.CfnOutput(self, "ProposalsTableArn", value=table.table_arn)
        cdk.CfnOutput(self, "AppWriterRoleArn", value=app_role.role_arn)
        cdk.CfnOutput(self, "ExecutionLayerRoleArn", value=exec_role.role_arn)
