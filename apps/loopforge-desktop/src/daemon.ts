export type ChatQueryBody = {
  query: string;
  skills: ["loopforge-router"];
};

export function buildChatQueryBody(query: string): ChatQueryBody {
  return {
    query: query.trim(),
    skills: ["loopforge-router"]
  };
}

export function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) return error.message;
  return typeof error === "string" ? error : fallback;
}
