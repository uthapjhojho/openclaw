import type { Api, Model } from "@mariozechner/pi-ai";

function isOpenAiCompletionsModel(model: Model<Api>): model is Model<"openai-completions"> {
  return model.api === "openai-completions";
}

export function normalizeModelCompat(model: Model<Api>): Model<Api> {
  const baseUrl = model.baseUrl ?? "";
  const isZai = model.provider === "zai" || baseUrl.includes("api.z.ai");
  const isNvidia = model.provider === "nvidia" || baseUrl.includes("integrate.api.nvidia.com");

  if (!isOpenAiCompletionsModel(model)) {
    return model;
  }

  const openaiModel = model;
  let compat = openaiModel.compat ?? undefined;
  let mutated = false;

  if (isZai && compat?.supportsDeveloperRole !== false) {
    compat = compat
      ? { ...compat, supportsDeveloperRole: false }
      : { supportsDeveloperRole: false };
    mutated = true;
  }

  // NVIDIA's API requires user message content as a plain string, not an array.
  // Sending an array causes: 400 "Input should be a valid string" at (body, messages, N, content).
  if (isNvidia && compat?.requiresStringUserContent !== true) {
    compat = compat
      ? { ...compat, requiresStringUserContent: true }
      : { requiresStringUserContent: true };
    mutated = true;
  }

  if (!mutated) {
    return model;
  }

  openaiModel.compat = compat;
  return openaiModel;
}
