
import json

from pydantic import ValidationError

from services.agent.exceptions import MalformedAgentOutputError
from services.agent.schema import AgentDecisionOutput


def parse_agent_decision(raw_output: str | dict) -> AgentDecisionOutput:
    if isinstance(raw_output, str):
        try:
            payload = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise MalformedAgentOutputError(f"not valid JSON: {exc}", raw_output=raw_output) from exc
    else:
        payload = raw_output

    if not isinstance(payload, dict):
        raise MalformedAgentOutputError(
            f"expected a JSON object, got {type(payload).__name__}",
            raw_output=str(raw_output),
        )

    try:
        return AgentDecisionOutput.model_validate(payload)
    except ValidationError as exc:
        raise MalformedAgentOutputError(str(exc), raw_output=str(raw_output)) from exc
