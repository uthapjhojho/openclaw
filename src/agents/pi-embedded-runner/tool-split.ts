import type { AgentTool } from "@mariozechner/pi-agent-core";
import type { CreateAgentSessionOptions } from "@mariozechner/pi-coding-agent";
import { toToolDefinitions } from "../pi-tool-definition-adapter.js";

// We always pass tools via `customTools` so our policy filtering, sandbox integration,
// and extended toolset remain consistent across providers.
type AnyAgentTool = AgentTool;

export function splitSdkTools(options: { tools: AnyAgentTool[]; sandboxEnabled: boolean }): {
  builtInTools: NonNullable<CreateAgentSessionOptions["tools"]>;
  customTools: ReturnType<typeof toToolDefinitions>;
} {
  const { tools } = options;
  const customTools = toToolDefinitions(tools);
  return {
    // pi-coding-agent 0.68.0+ treats `tools` as a string[] allowlist.
    // Pass the exact custom tool names so Pi's built-in tools (bash, read,
    // edit, write) are filtered from _toolRegistry — we route everything
    // through customTools for consistent policy/sandbox handling.
    // Do NOT use []: truthy empty array creates an empty Set, blocking all tools.
    // Do NOT use undefined: enables Pi's default built-ins alongside customs,
    // causing duplicate/conflicting tool schemas that confuse some models.
    builtInTools: customTools.map((t) => t.name),
    customTools,
  };
}
