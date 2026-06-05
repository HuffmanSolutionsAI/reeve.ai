from enum import Enum


class Tier(str, Enum):
    """The three capability tiers enforced by `run_agent`.

    READ          — scoped data the agent may see.
    ACT_INTERNAL  — reversible, no money/legal/tenant; runs inline.
    ACT_GATED     — money / legal obligation / external comms; INTERCEPTED
                    into a proposal. The runtime never calls the handler from
                    the agent loop. Only `execute_approved_proposal` runs it,
                    after a human approves.
    """

    READ = "read"
    ACT_INTERNAL = "act_internal"
    ACT_GATED = "act_gated"
