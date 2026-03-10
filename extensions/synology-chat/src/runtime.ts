import type { PluginRuntime } from "openclaw/plugin-sdk/synology-chat";
import { createPluginRuntimeStore } from "openclaw/plugin-sdk/compat";

const { setRuntime: setSynologyRuntime, getRuntime: getSynologyRuntime } =
  createPluginRuntimeStore<PluginRuntime>(
    "Synology Chat runtime not initialized - plugin not registered",
  );
export { getSynologyRuntime, setSynologyRuntime };
