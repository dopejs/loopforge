export function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error) return error.message;
  return typeof error === "string" ? error : fallback;
}

type AgentLifecycleState = {
  ready: boolean;
};

export async function ensureAgentReady<T extends AgentLifecycleState>(
  request: (command: "agent_status" | "agent_start") => Promise<T>
): Promise<T> {
  const status = await request("agent_status");
  return status.ready ? status : request("agent_start");
}
