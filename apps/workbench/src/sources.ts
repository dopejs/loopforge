/**
 * Known model sources.
 *
 * Every one of these speaks the OpenAI-compatible protocol, which is the only
 * HTTP protocol Kura implements. They are presets rather than distinct
 * providers: choosing one fills in an endpoint the user would otherwise have
 * to look up, and the runtime sees the same configured provider either way.
 *
 * Names are proper nouns and are not translated. The endpoints are each
 * vendor's documented OpenAI-compatible base URL; a wrong one here is a
 * support burden, so anything not verifiable belongs under "custom" instead of
 * being guessed at.
 */

export type SourceKind = "account" | "cloud" | "local" | "custom";

export type Source = {
  id: string;
  name: string;
  kind: SourceKind;
  /** Empty for `custom`, where the user supplies it, and for `account`. */
  baseUrl: string;
  protocol: "openai_compatible" | "local_cli_bridge";
  /** Shown as a hint, not a list to choose from: a key can reach any of them. */
  exampleModel: string;
  /**
   * The runtime's own id for an account source.
   *
   * Present only for `account`: those are not endpoints this app configures
   * but providers Kura already knows, reached by borrowing a CLI the user has
   * signed into. Everything else is a preset over the one HTTP provider.
   */
  providerId?: string;
  /**
   * The subscription account this vendor also offers, where it has one.
   *
   * Present only for vendors that genuinely support signing in. The wizard
   * offers an account as an alternative to a key exactly where this is set,
   * rather than showing a disabled control on every preset.
   */
  oauthProviderId?: string;
};

export const SOURCES: readonly Source[] = [
  {
    // Signed in through the tool's own login, so usage counts against an
    // existing subscription and no key is entered here.
    id: "claude_managed",
    name: "Claude (subscription)",
    kind: "account",
    baseUrl: "",
    protocol: "local_cli_bridge",
    exampleModel: "",
    providerId: "claude_managed"
  },
  {
    id: "codex_managed",
    name: "Codex (subscription)",
    kind: "account",
    baseUrl: "",
    protocol: "local_cli_bridge",
    exampleModel: "",
    providerId: "codex_managed"
  },
  {
    id: "openai",
    name: "OpenAI",
    kind: "cloud",
    baseUrl: "https://api.openai.com/v1",
    protocol: "openai_compatible",
    exampleModel: "gpt-4o-mini"
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    kind: "cloud",
    baseUrl: "https://api.deepseek.com/v1",
    protocol: "openai_compatible",
    exampleModel: "deepseek-chat"
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    kind: "cloud",
    baseUrl: "https://openrouter.ai/api/v1",
    protocol: "openai_compatible",
    exampleModel: "anthropic/claude-3.5-sonnet"
  },
  {
    id: "moonshot",
    name: "Moonshot",
    kind: "cloud",
    baseUrl: "https://api.moonshot.cn/v1",
    protocol: "openai_compatible",
    exampleModel: "moonshot-v1-8k"
  },
  {
    id: "zhipu",
    name: "Zhipu GLM",
    kind: "cloud",
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    protocol: "openai_compatible",
    exampleModel: "glm-4-flash"
  },
  {
    id: "dashscope",
    name: "Alibaba DashScope",
    kind: "cloud",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    protocol: "openai_compatible",
    exampleModel: "qwen-plus"
  },
  {
    id: "groq",
    name: "Groq",
    kind: "cloud",
    baseUrl: "https://api.groq.com/openai/v1",
    protocol: "openai_compatible",
    exampleModel: "llama-3.3-70b-versatile"
  },
  {
    id: "together",
    name: "Together AI",
    kind: "cloud",
    baseUrl: "https://api.together.xyz/v1",
    protocol: "openai_compatible",
    exampleModel: "meta-llama/Llama-3.3-70B-Instruct-Turbo"
  },
  {
    // omp reaches these through a "open this page, paste the key" helper
    // rather than an OAuth flow, which is what this list already is: the
    // endpoint the user would otherwise have to look up, with a key they
    // fetch themselves.
    id: "minimax",
    name: "MiniMax",
    kind: "cloud",
    baseUrl: "https://api.minimax.io/v1",
    protocol: "openai_compatible",
    exampleModel: "MiniMax-M3"
  },
  {
    id: "xiaomi",
    name: "Xiaomi MiMo",
    kind: "cloud",
    baseUrl: "https://api.xiaomimimo.com/v1",
    protocol: "openai_compatible",
    exampleModel: "mimo-v2.5"
  },
  {
    id: "anthropic_api",
    name: "Anthropic (API key)",
    kind: "cloud",
    baseUrl: "https://api.anthropic.com/v1",
    protocol: "openai_compatible",
    exampleModel: "claude-sonnet-4-5",
    oauthProviderId: "anthropic"
  },
  {
    id: "xai",
    name: "xAI",
    kind: "cloud",
    baseUrl: "https://api.x.ai/v1",
    protocol: "openai_compatible",
    exampleModel: "grok-4",
    oauthProviderId: "xai"
  },
  {
    id: "zai",
    name: "Z.ai",
    kind: "cloud",
    baseUrl: "https://api.z.ai/api/coding/paas/v4",
    protocol: "openai_compatible",
    exampleModel: "glm-4.6",
    oauthProviderId: "zai"
  },
  {
    id: "cerebras",
    name: "Cerebras",
    kind: "cloud",
    baseUrl: "https://api.cerebras.ai/v1",
    protocol: "openai_compatible",
    exampleModel: "llama-3.3-70b"
  },
  {
    id: "fireworks",
    name: "Fireworks",
    kind: "cloud",
    baseUrl: "https://api.fireworks.ai/inference/v1",
    protocol: "openai_compatible",
    exampleModel: "accounts/fireworks/models/llama-v3p3-70b-instruct"
  },
  {
    id: "nvidia",
    name: "NVIDIA NIM",
    kind: "cloud",
    baseUrl: "https://integrate.api.nvidia.com/v1",
    protocol: "openai_compatible",
    exampleModel: "meta/llama-3.3-70b-instruct"
  },
  {
    id: "huggingface",
    name: "Hugging Face",
    kind: "cloud",
    baseUrl: "https://router.huggingface.co/v1",
    protocol: "openai_compatible",
    exampleModel: "meta-llama/Llama-3.3-70B-Instruct"
  },
  {
    id: "novita",
    name: "Novita",
    kind: "cloud",
    baseUrl: "https://api.novita.ai/openai/v1",
    protocol: "openai_compatible",
    exampleModel: "meta-llama/llama-3.3-70b-instruct"
  },
  {
    id: "siliconflow",
    name: "SiliconFlow",
    kind: "cloud",
    baseUrl: "https://api.siliconflow.com/v1",
    protocol: "openai_compatible",
    exampleModel: "Qwen/Qwen2.5-72B-Instruct"
  },
  {
    id: "siliconflow_cn",
    name: "SiliconFlow (\u4e2d\u56fd)",
    kind: "cloud",
    baseUrl: "https://api.siliconflow.cn/v1",
    protocol: "openai_compatible",
    exampleModel: "Qwen/Qwen2.5-72B-Instruct"
  },
  {
    id: "qianfan",
    name: "Qianfan",
    kind: "cloud",
    baseUrl: "https://qianfan.baidubce.com/v2",
    protocol: "openai_compatible",
    exampleModel: "ernie-4.5-turbo-128k"
  },
  {
    id: "qwen_portal",
    name: "Qwen Portal",
    kind: "cloud",
    baseUrl: "https://portal.qwen.ai/v1",
    protocol: "openai_compatible",
    exampleModel: "qwen3-coder-plus"
  },
  {
    id: "alibaba_coding",
    name: "Alibaba Coding Plan",
    kind: "cloud",
    baseUrl: "https://coding-intl.dashscope.aliyuncs.com/v1",
    protocol: "openai_compatible",
    exampleModel: "qwen3-coder-plus"
  },
  {
    id: "zhipu_coding",
    name: "Zhipu Coding Plan",
    kind: "cloud",
    baseUrl: "https://open.bigmodel.cn/api/coding/paas/v4",
    protocol: "openai_compatible",
    exampleModel: "glm-4.6"
  },
  {
    id: "baseten",
    name: "Baseten",
    kind: "cloud",
    baseUrl: "https://inference.baseten.co/v1",
    protocol: "openai_compatible",
    exampleModel: "deepseek-ai/DeepSeek-V3"
  },
  {
    id: "coreweave",
    name: "CoreWeave",
    kind: "cloud",
    baseUrl: "https://api.inference.wandb.ai/v1",
    protocol: "openai_compatible",
    exampleModel: "meta-llama/Llama-3.3-70B-Instruct"
  },
  {
    id: "gmi_cloud",
    name: "GMI Cloud",
    kind: "cloud",
    baseUrl: "https://api.gmi-serving.com/v1",
    protocol: "openai_compatible",
    exampleModel: "deepseek-ai/DeepSeek-V3"
  },
  {
    id: "nanogpt",
    name: "NanoGPT",
    kind: "cloud",
    baseUrl: "https://nano-gpt.com/api/v1",
    protocol: "openai_compatible",
    exampleModel: "deepseek-v3"
  },
  {
    id: "venice",
    name: "Venice",
    kind: "cloud",
    baseUrl: "https://api.venice.ai/api/v1",
    protocol: "openai_compatible",
    exampleModel: "llama-3.3-70b"
  },
  {
    id: "sakana",
    name: "Sakana AI",
    kind: "cloud",
    baseUrl: "https://api.sakana.ai/v1",
    protocol: "openai_compatible",
    exampleModel: ""
  },
  {
    id: "synthetic",
    name: "Synthetic",
    kind: "cloud",
    baseUrl: "https://api.synthetic.new/openai/v1",
    protocol: "openai_compatible",
    exampleModel: ""
  },
  {
    id: "zenmux",
    name: "ZenMux",
    kind: "cloud",
    baseUrl: "https://zenmux.ai/api/v1",
    protocol: "openai_compatible",
    exampleModel: ""
  },
  {
    id: "aiand",
    name: "ai&",
    kind: "cloud",
    baseUrl: "https://api.aiand.com/v1",
    protocol: "openai_compatible",
    exampleModel: ""
  },
  {
    id: "umans",
    name: "Umans AI",
    kind: "cloud",
    baseUrl: "https://api.code.umans.ai",
    protocol: "openai_compatible",
    exampleModel: ""
  },
  {
    id: "kimi",
    name: "Kimi",
    kind: "cloud",
    baseUrl: "https://api.moonshot.cn/v1",
    protocol: "openai_compatible",
    exampleModel: "kimi-k2",
    oauthProviderId: "kimi"
  },
  {
    id: "llamacpp",
    name: "llama.cpp",
    kind: "local",
    baseUrl: "http://127.0.0.1:8080/v1",
    protocol: "openai_compatible",
    exampleModel: ""
  },
  {
    id: "vllm",
    name: "vLLM",
    kind: "local",
    baseUrl: "http://127.0.0.1:8000/v1",
    protocol: "openai_compatible",
    exampleModel: ""
  },
  {
    id: "ollama",
    name: "Ollama",
    kind: "local",
    baseUrl: "http://localhost:11434/v1",
    protocol: "openai_compatible",
    exampleModel: "llama3.2"
  },
  {
    id: "lmstudio",
    name: "LM Studio",
    kind: "local",
    baseUrl: "http://localhost:1234/v1",
    protocol: "openai_compatible",
    exampleModel: "local-model"
  },
  {
    id: "custom",
    name: "Custom provider",
    kind: "custom",
    baseUrl: "",
    protocol: "openai_compatible",
    exampleModel: ""
  }
];

/** Matches on name and endpoint, so "deepseek" and "api.deepseek" both work. */
export function matchSources(query: string): readonly Source[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return SOURCES;
  return SOURCES.filter(
    (source) =>
      // Custom always survives: it is the answer when nothing else matches.
      source.kind === "custom" ||
      source.name.toLowerCase().includes(needle) ||
      source.baseUrl.toLowerCase().includes(needle)
  );
}

/** The source a stored endpoint came from, by URL. */
export function sourceForBaseUrl(baseUrl: string): Source | undefined {
  const normalized = baseUrl.trim().replace(/\/+$/, "").toLowerCase();
  if (!normalized) return undefined;
  return SOURCES.find(
    (source) => source.baseUrl && source.baseUrl.toLowerCase() === normalized
  );
}

/**
 * Whether this source is configured with a key at all.
 *
 * Local endpoints run on this machine, and account sources borrow a session
 * the user established elsewhere -- neither takes a credential here.
 */
export function needsApiKey(source: Source): boolean {
  return source.kind !== "local" && source.kind !== "account";
}

/** Account sources are signed into rather than configured. */
export function isAccountSource(source: Source): boolean {
  return source.kind === "account";
}
