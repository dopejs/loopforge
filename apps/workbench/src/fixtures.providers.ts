/**
 * Preview data for the Add Provider wizard and the model-routing table.
 *
 * The provider inventory and model-role routing are both real now: they come
 * from the Agent's `loopforge-provider-v1` projection of Kura (see
 * ./providers.ts). What remains here is the Add Provider wizard's source
 * catalogue, which needs Kura's setup-session endpoints to become real.
 * Nothing entered in the wizard is persisted.
 */

export type ProviderKind = "cloud" | "local" | "custom" | "account";

export type ProviderSource = { label: string; note: string; kind: ProviderKind };

/** Sources offered by the Add Provider wizard, in the design's order. */
export const PROVIDER_SOURCES: readonly ProviderSource[] = [
  { label: "Claude Code subscription", note: "Pro / Max account · no API key", kind: "account" },
  { label: "Codex subscription", note: "ChatGPT Plus / Pro account", kind: "account" },
  { label: "Anthropic", note: "api.anthropic.com", kind: "cloud" },
  { label: "OpenAI", note: "api.openai.com", kind: "cloud" },
  { label: "Google Gemini", note: "generativelanguage.googleapis.com", kind: "cloud" },
  { label: "Azure OpenAI", note: "<resource>.openai.azure.com", kind: "cloud" },
  { label: "Amazon Bedrock", note: "bedrock-runtime · AWS credentials", kind: "cloud" },
  { label: "Google Vertex AI", note: "aiplatform.googleapis.com", kind: "cloud" },
  { label: "Mistral", note: "api.mistral.ai", kind: "cloud" },
  { label: "DeepSeek", note: "api.deepseek.com", kind: "cloud" },
  { label: "xAI", note: "api.x.ai", kind: "cloud" },
  { label: "Cohere", note: "api.cohere.com", kind: "cloud" },
  { label: "Groq", note: "api.groq.com", kind: "cloud" },
  { label: "Cerebras", note: "api.cerebras.ai", kind: "cloud" },
  { label: "Together", note: "api.together.xyz", kind: "cloud" },
  { label: "Fireworks", note: "api.fireworks.ai", kind: "cloud" },
  { label: "OpenRouter", note: "openrouter.ai · aggregator", kind: "cloud" },
  { label: "Novita", note: "api.novita.ai", kind: "cloud" },
  { label: "Nvidia NIM", note: "integrate.api.nvidia.com", kind: "cloud" },
  { label: "Moonshot Kimi", note: "api.moonshot.cn", kind: "cloud" },
  { label: "Zhipu GLM", note: "open.bigmodel.cn", kind: "cloud" },
  { label: "Alibaba DashScope", note: "dashscope.aliyuncs.com", kind: "cloud" },
  { label: "Volcano Ark", note: "ark.cn-beijing.volces.com", kind: "cloud" },
  { label: "Baidu Qianfan", note: "qianfan.baidubce.com", kind: "cloud" },
  { label: "SiliconFlow", note: "api.siliconflow.cn", kind: "cloud" },
  { label: "Ollama", note: "127.0.0.1:11434 · local", kind: "local" },
  { label: "LM Studio", note: "127.0.0.1:1234 · local", kind: "local" },
  { label: "vLLM", note: "self-hosted inference · local or intranet", kind: "local" },
  { label: "llama.cpp", note: "127.0.0.1:8080 · gguf", kind: "local" },
  { label: "Custom provider", note: "pick a protocol · set endpoint and key", kind: "custom" }
];

/** `note` is an i18n key suffix under `protocol.*`. */
export const PROTOCOLS = [
  { label: "Anthropic Messages", path: "POST /v1/messages", note: "anthropic" },
  { label: "OpenAI Chat Completions", path: "POST /v1/chat/completions", note: "openaiChat" },
  { label: "OpenAI Responses", path: "POST /v1/responses", note: "openaiResponses" },
  { label: "Legacy Completions", path: "POST /v1/completions", note: "legacy" },
  { label: "Gemini generateContent", path: "POST /v1beta/models/*", note: "gemini" }
] as const;

export type WizardModel = {
  name: string;
  ctx: string;
  maxOut: string;
  caps: readonly string[];
  alias: string;
  /** i18n key suffix under `role.*`. */
  role: string;
};

const GENERIC_MODELS: readonly WizardModel[] = [
  { name: "model-id", ctx: "32k", maxOut: "4k", caps: ["chat"], alias: "main", role: "primary" }
];

const SOURCE_MODELS: Record<string, readonly WizardModel[]> = {
  "Claude Code subscription": [
    { name: "claude-sonnet", ctx: "200k", maxOut: "64k", caps: ["chat", "vision", "tools"], alias: "sonnet", role: "primary" },
    { name: "claude-haiku", ctx: "200k", maxOut: "32k", caps: ["chat", "tools"], alias: "haiku", role: "fast" },
    { name: "claude-opus", ctx: "200k", maxOut: "32k", caps: ["chat", "vision", "tools"], alias: "opus", role: "none" }
  ],
  "Codex subscription": [
    { name: "codex", ctx: "192k", maxOut: "32k", caps: ["chat", "tools"], alias: "codex", role: "primary" },
    { name: "codex-mini", ctx: "128k", maxOut: "16k", caps: ["chat", "tools"], alias: "mini", role: "fast" }
  ],
  Anthropic: [
    { name: "claude-sonnet", ctx: "200k", maxOut: "64k", caps: ["chat", "vision", "tools"], alias: "sonnet", role: "primary" },
    { name: "claude-haiku", ctx: "200k", maxOut: "32k", caps: ["chat", "tools"], alias: "haiku", role: "fast" },
    { name: "claude-opus", ctx: "200k", maxOut: "32k", caps: ["chat", "vision", "tools"], alias: "opus", role: "none" }
  ],
  OpenAI: [
    { name: "gpt-4.1", ctx: "128k", maxOut: "32k", caps: ["chat", "vision", "tools"], alias: "main", role: "primary" },
    { name: "gpt-4.1-mini", ctx: "128k", maxOut: "16k", caps: ["chat", "tools"], alias: "fast", role: "fast" },
    { name: "text-embedding-3-large", ctx: "8k", maxOut: "—", caps: ["embed"], alias: "embed", role: "none" }
  ],
  "Google Gemini": [
    { name: "gemini-2.5-pro", ctx: "1M", maxOut: "64k", caps: ["chat", "vision", "tools"], alias: "pro", role: "primary" },
    { name: "gemini-2.5-flash", ctx: "1M", maxOut: "64k", caps: ["chat", "vision", "tools"], alias: "flash", role: "fast" }
  ],
  DeepSeek: [
    { name: "deepseek-chat", ctx: "128k", maxOut: "8k", caps: ["chat", "tools"], alias: "chat", role: "primary" },
    { name: "deepseek-reasoner", ctx: "128k", maxOut: "32k", caps: ["chat"], alias: "reason", role: "none" }
  ],
  vLLM: [
    { name: "qwen2.5-coder-32b-instruct", ctx: "32k", maxOut: "8k", caps: ["chat", "tools"], alias: "code", role: "primary" }
  ],
  Ollama: [
    { name: "deepseek-coder-v2:16b", ctx: "64k", maxOut: "8k", caps: ["chat", "tools"], alias: "code", role: "primary" },
    { name: "llava:13b", ctx: "32k", maxOut: "4k", caps: ["chat", "vision"], alias: "vision", role: "vision" },
    { name: "nomic-embed-text", ctx: "8k", maxOut: "—", caps: ["embed"], alias: "embed", role: "none" }
  ],
  "LM Studio": [
    { name: "qwen2.5-coder-14b", ctx: "32k", maxOut: "8k", caps: ["chat", "tools"], alias: "code", role: "primary" },
    { name: "mistral-nemo-12b", ctx: "128k", maxOut: "8k", caps: ["chat"], alias: "long", role: "fast" }
  ]
};

export function modelsForSource(label: string): readonly WizardModel[] {
  return SOURCE_MODELS[label] ?? GENERIC_MODELS;
}

export const ACCOUNT_DETAILS: Record<string, { mark: string; title: string; models: string }> = {
  "Claude Code subscription": { mark: "CC", title: "Claude Code", models: "sonnet · haiku · opus" },
  "Codex subscription": { mark: "CX", title: "Codex (ChatGPT)", models: "codex · codex-mini" }
};

export const PAIR_CODE = "FRG7-2K9D";

export const TOOL_CHIPS = [
  "read_file",
  "edit_file",
  "grep",
  "run_tests",
  "playtest_sim",
  "git",
  "shell (sandbox)",
  "asset_import"
] as const;
