"""FD ADK agent definition.

MCP authentication is controlled by MCP_AUTH_MODE:
  propagate (default)
    ADKTokenPropagationPlugin forwards the incoming Authorization header to
    every outbound MCP call.
    Used in UC1 Path B (OBO native): loan-agent's OBO token (client_id=loan-agent) is
    propagated unchanged to /fd-mcp. agentgateway CEL RBAC sees client_id=loan-agent
    and restricts the caller to get_total_fixed_deposits (read-only).
  workload
    WorkloadMCPTokenProvider fetches this agent's own token and injects it into
    every MCP call. Supports two sub-modes based on STS_URL:
    - STS_URL set: two-step RFC 8693 OBO exchange (KC client_credentials → KC
      token → STS → OBO token with client_id=fd-agent). Used for UC1 Path A (direct
      fd-agent identity): CEL RBAC allows both get_total_fixed_deposits and
      book_fixed_deposit for client_id=fd-agent.
    - No STS_URL: SA JWT → Keycloak token exchange. Used in UC2 (chain-fd-agent).

Environment variables:
  MODEL          LLM model name (default: gemini-2.0-flash)
  LLM_BASE_URL   Agentgateway provider base URL
  MCP_URL        FD MCP server URL through the agentgateway proxy
  MCP_AUTH_MODE  'propagate' or 'workload' (default: propagate)
  STS_URL        agentgateway STS endpoint (workload mode only, UC1 Path A)
"""

import os

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StreamableHTTPConnectionParams

_MCP_URL = os.environ.get(
    "MCP_URL",
    "http://agentgateway.agentgateway-system.svc.cluster.local:8080/fd-mcp",
)
_LLM_BASE_URL = os.environ.get(
    "LLM_BASE_URL",
    "http://agentgateway.agentgateway-system.svc.cluster.local:8080/openai",
)
_MODEL = os.environ.get("MODEL", "gemini-2.0-flash")
_MCP_AUTH_MODE = os.environ.get("MCP_AUTH_MODE", "propagate")

plugin = None

if _MCP_AUTH_MODE == "workload":
    from .workload_auth import WorkloadMCPTokenProvider as _WorkloadMCPTokenProvider
    _mcp_header_provider = _WorkloadMCPTokenProvider().header_provider
else:
    from agentsts.adk import ADKTokenPropagationPlugin as _ADKTokenPropagationPlugin
    plugin = _ADKTokenPropagationPlugin()
    _mcp_header_provider = plugin.header_provider

toolset = MCPToolset(
    connection_params=StreamableHTTPConnectionParams(url=_MCP_URL),
    header_provider=_mcp_header_provider,
)

root_agent = LlmAgent(
    name="fd_agent",
    model=LiteLlm(
        model=f"openai/{_MODEL}",
        api_base=_LLM_BASE_URL,
        api_key="none",
    ),
    tools=[toolset],
    instruction=(
        "You are a fixed deposit assistant. "
        "Use get_total_fixed_deposits to retrieve a customer's FD summary. "
        "Use book_fixed_deposit to create a new fixed deposit. "
        "Always confirm the customer_id and relevant details in your response."
    ),
)
