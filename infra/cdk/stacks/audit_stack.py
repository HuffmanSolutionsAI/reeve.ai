"""Audit infra: DynamoDB table (Put-only at the IAM layer), Streams → Lambda → SNS.

Append-only is enforced two ways:
  1. App role granted ONLY `dynamodb:PutItem` (no UpdateItem / DeleteItem).
  2. Point-in-time recovery on; RemovalPolicy.RETAIN so the table outlives stack
     teardown.

The SNS topic is what surfaces the activity feed and (with Cole) notifications.
A single forwarder Lambda reads the stream and publishes one SNS message per
INSERT, with kind+investor_id as message attributes for subscriber filtering.
"""
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_lambda_event_sources as event_sources,
    aws_sns as sns,
)
from constructs import Construct


class AuditStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- table -----------------------------------------------------------
        table = dynamodb.Table(
            self,
            "AuditEvents",
            table_name="reeve-audit-events",
            partition_key=dynamodb.Attribute(
                name="investor_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="ts_event_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            stream=dynamodb.StreamViewType.NEW_IMAGE,
            point_in_time_recovery=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
        )

        table.add_global_secondary_index(
            index_name="entity_id-ts-index",
            partition_key=dynamodb.Attribute(
                name="entity_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="ts_event_id", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # --- app write role (Put-only) --------------------------------------
        # Assumable by the workload role (ECS/Lambda/EC2) that runs the API.
        # We don't bind a service principal here; attach this role by ARN.
        app_role = iam.Role(
            self,
            "AppPutOnlyRole",
            role_name="reeve-app-audit-writer",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            ),
            description="Put-only access to the audit table. No UpdateItem / DeleteItem.",
        )
        app_role.add_to_policy(
            iam.PolicyStatement(
                actions=["dynamodb:PutItem"],
                resources=[table.table_arn],
            )
        )

        # Reader role for the activity feed / per-entity history (Query only).
        reader_role = iam.Role(
            self,
            "AuditReaderRole",
            role_name="reeve-audit-reader",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            ),
            description="Query/Get the audit table and the entity GSI.",
        )
        reader_role.add_to_policy(
            iam.PolicyStatement(
                actions=["dynamodb:Query", "dynamodb:GetItem"],
                resources=[
                    table.table_arn,
                    f"{table.table_arn}/index/entity_id-ts-index",
                ],
            )
        )

        # --- activity-feed topic --------------------------------------------
        topic = sns.Topic(
            self,
            "AuditFeed",
            topic_name="reeve-audit-feed",
            display_name="Reeve audit feed",
        )

        # --- stream → SNS forwarder -----------------------------------------
        forwarder_dir = Path(__file__).parent / "forwarder"
        forwarder = lambda_.Function(
            self,
            "AuditStreamForwarder",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="forwarder.handler",
            code=lambda_.Code.from_asset(str(forwarder_dir)),
            environment={"TOPIC_ARN": topic.topic_arn},
            timeout=cdk.Duration.seconds(15),
            memory_size=256,
            description="Pushes each audit insert to the SNS activity feed.",
        )
        topic.grant_publish(forwarder)
        forwarder.add_event_source(
            event_sources.DynamoEventSource(
                table,
                starting_position=lambda_.StartingPosition.LATEST,
                batch_size=10,
                retry_attempts=3,
                bisect_batch_on_error=True,
            )
        )

        # --- outputs ---------------------------------------------------------
        cdk.CfnOutput(self, "AuditTableName", value=table.table_name)
        cdk.CfnOutput(self, "AuditTableArn", value=table.table_arn)
        cdk.CfnOutput(self, "AuditTopicArn", value=topic.topic_arn)
        cdk.CfnOutput(self, "AppWriterRoleArn", value=app_role.role_arn)
        cdk.CfnOutput(self, "ReaderRoleArn", value=reader_role.role_arn)
