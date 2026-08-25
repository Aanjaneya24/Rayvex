
import uuid

import redis
from langchain_core.tools import StructuredTool
from sqlalchemy.orm import Session

from services.agent.tools.proposal_tools import build_action_proposal_tools, build_record_decision_tool
from services.agent.tools.read_tools import build_read_tools
from services.agent.tools.reasoning_tools import build_reasoning_tools
from services.payments.provider import PaymentProvider
from services.payments.provider_factory import build_default_payment_provider


def build_agent_tools(
    session: Session,
    redis_client: redis.Redis,
    *,
    case_id: uuid.UUID,
    correlation_id: uuid.UUID,
    model_backend: str,
    model_name: str,
    prompt_version: str,
    schema_version: str,
    tool_trace: list[dict],
    provider: PaymentProvider | None = None,
    usage_stats: dict | None = None,
) -> list[StructuredTool]:
    provider = provider if provider is not None else build_default_payment_provider(session)

    return [
        *build_read_tools(session, provider),
        *build_reasoning_tools(session, redis_client),
        *build_action_proposal_tools(),
        build_record_decision_tool(
            session, case_id=case_id, correlation_id=correlation_id,
            model_backend=model_backend, model_name=model_name, prompt_version=prompt_version,
            schema_version=schema_version, tool_trace=tool_trace, usage_stats=usage_stats,
        ),
    ]
