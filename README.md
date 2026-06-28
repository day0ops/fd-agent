# fd-agent

Google ADK-based fixed deposit agent for the agentgateway RBAC demo.

Wraps the `fd-server-mcp` MCP server. Supports two MCP authentication modes:

- `propagate` (default) — forwards incoming JWT to MCP (UC1: jwt-propagation)
- `workload` — uses own Keycloak workload token for MCP (UC2: workload-identity)

## Usage

```bash
make build IMAGE_REPO=australia-southeast1-docker.pkg.dev/field-engineering-apac/kasunt
make push  IMAGE_REPO=australia-southeast1-docker.pkg.dev/field-engineering-apac/kasunt
make deploy
```
