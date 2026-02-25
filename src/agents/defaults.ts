// Defaults for agent metadata when upstream does not supply them.
// Model id uses pi-ai's built-in NVIDIA catalog.
export const DEFAULT_PROVIDER = "nvidia";
export const DEFAULT_MODEL = "nvidia/llama-3.1-nemotron-70b-instruct";
// Conservative fallback used when model metadata is unavailable.
export const DEFAULT_CONTEXT_TOKENS = 200_000;
