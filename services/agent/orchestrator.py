
import os
import time
import uuid

import redis
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy.orm import Session

from models.case import Case
from services.agent.cost_estimation import estimate_cost_usd
from services.agent.exceptions import MalformedAgentOutputError
from services.agent.prompts.system_prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_case_prompt
from services.agent.schema import SCHEMA_VERSION, AgentDecisionOutput
from services.agent.tools import build_agent_tools
from services.agent.validation import parse_agent_decision

MAX_TOOL_CALLING_STEPS = 8


def build_llm() -> BaseChatModel:
    if os.environ.get("GROQ_API_KEY"):
        from langchain_groq import ChatGroq

        return ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
    if os.environ.get("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model="gpt-4o", temperature=0)
    raise RuntimeError(
        "Neither GROQ_API_KEY nor OPENAI_API_KEY is set. The agent orchestrator "
        "needs a real LLM backend configured in .env to run for real. Tests use "
        "LangChain's FakeMessagesListChatModel instead: see tests/agent/fakes.py."
    )


class RecoveryAgentOrchestrator:

    def __init__(self, llm: BaseChatModel):
        self.llm = llm

    def propose(
        self,
        session: Session,
        redis_client: redis.Redis,
        *,
        case_id: uuid.UUID,
        correlation_id: uuid.UUID,
        untrusted_fields: dict | None = None,
        provider=None,
    ) -> AgentDecisionOutput:
        case = session.get(Case, case_id)
        if case is None:
            raise ValueError(f"no case found for case_id={case_id}")

        case_context = {
            "case_id": str(case.id), "merchant_id": case.merchant_id,
            "current_state": case.current_state.value,
        }
        tool_trace: list[dict] = []
        usage_stats = {"llm_call_count": 0, "total_latency_ms": 0, "estimated_cost_usd": 0.0}
        model_backend = type(self.llm).__name__
        model_name = getattr(self.llm, "model_name", None) or model_backend

        tools = build_agent_tools(
            session, redis_client, case_id=case_id, correlation_id=correlation_id,
            model_backend=model_backend, model_name=model_name,
            prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION, tool_trace=tool_trace,
            provider=provider, usage_stats=usage_stats,
        )
        tools_by_name = {t.name: t for t in tools}
        bound_llm = self.llm.bind_tools(tools)

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=build_case_prompt(case_context, untrusted_fields or {})),
        ]

        for _ in range(MAX_TOOL_CALLING_STEPS):
            call_started = time.monotonic()
            response: AIMessage = bound_llm.invoke(messages)
            usage_stats["llm_call_count"] += 1
            usage_stats["total_latency_ms"] += int((time.monotonic() - call_started) * 1000)
            usage = getattr(response, "usage_metadata", None)
            if usage:
                usage_stats["estimated_cost_usd"] += estimate_cost_usd(
                    model_name, input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                )
            messages.append(response)

            if not response.tool_calls:
                break

            for call in response.tool_calls:
                if call["name"] == "record_decision":
                    decision = parse_agent_decision(call["args"].get("decision_json", ""))
                    tools_by_name["record_decision"].invoke(call["args"])
                    tool_trace.append({"tool": "record_decision", "args": call["args"]})
                    return decision

                tool_fn = tools_by_name.get(call["name"])
                result = (
                    tool_fn.invoke(call["args"]) if tool_fn is not None
                    else {"error": f"unknown tool '{call['name']}'"}
                )
                tool_trace.append({"tool": call["name"], "args": call["args"], "result": result})
                messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

        raise MalformedAgentOutputError(
            f"agent did not call record_decision with valid output within "
            f"{MAX_TOOL_CALLING_STEPS} steps"
        )
