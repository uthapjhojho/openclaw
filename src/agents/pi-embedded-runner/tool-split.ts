import type { AgentTool } from "@mariozechner/pi-agent-core";
import type { CreateAgentSessionOptions } from "@mariozechner/pi-coding-agent";
import { toToolDefinitions } from "../pi-tool-definition-adapter.js";

// We always pass tools via `customTools` so our policy filtering, sandbox integration,
// and extended toolset remain consistent across providers.
type AnyAgentTool = AgentTool;

export function splitSdkTools(options: { tools: AnyAgentTool[]; sandboxEnabled: boolean }): {
  builtInTools: NonNullable<CreateAgentSessionOptions["tools"]> | undefined;
  customTools: ReturnType<typeof toToolDefinitions>;
} {
  const { tools } = options;
  return {
    // undefined = no built-in tool allowlist; all tools are passed via customTools.
    // Do NOT use [] here: pi-coding-agent 0.68.0+ treats [] as a truthy allowlist
    // that creates an empty Set, filtering out ALL tools from _toolRegistry.
    builtInTools: undefined,
    customTools: toToolDefinitions(tools),
  };
}
