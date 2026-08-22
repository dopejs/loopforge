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

export type SourceKind = "cloud" | "local" | "custom";

export type Source = {
  id: string;
  name: string;
  kind: SourceKind;
  /** Empty for `custom`, where the user supplies it. */
  baseUrl: string;
  protocol: "openai_compatible";
  /** Shown as a hint, not a list to choose from: a key can reach any of them. */
  exampleModel: string;
};

export const SOURCES: readonly Source[] = [
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

/** Local endpoints run on this machine and need no credential. */
export function needsApiKey(source: Source): boolean {
  return source.kind !== "local";
}
