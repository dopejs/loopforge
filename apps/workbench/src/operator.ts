/**
 * Who is approving.
 *
 * Loopforge is a local agent with no cross-user collaboration, so there is no
 * role model here: the approver is whoever is using the Workbench. The core
 * already reflects that by stamping every approval `identity_source:
 * "local-declaration"` -- it does not claim the identity was verified, because
 * it was not.
 *
 * Stored Workbench-local rather than per project, like appearance: the person
 * does not change when the folder does.
 */

export const OPERATOR_STORAGE_KEY = "loopforge.operator";

export type Operator = {
  /** Stable across renames, so a history of approvals stays one person. */
  id: string;
  name: string;
};

function newOperatorId(): string {
  const random = globalThis.crypto?.randomUUID?.();
  return `op_${(random ?? `${Date.now()}`).replace(/-/g, "").slice(0, 24)}`;
}

export function loadOperator(storage: Storage | undefined = safeStorage()): Operator {
  const fallback: Operator = { id: newOperatorId(), name: "" };
  if (!storage) return fallback;
  try {
    const raw = storage.getItem(OPERATOR_STORAGE_KEY);
    if (!raw) return fallback;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return fallback;
    const value = parsed as Partial<Operator>;
    return {
      // A stored blank id would silently record approvals against nobody.
      id: typeof value.id === "string" && value.id ? value.id : fallback.id,
      name: typeof value.name === "string" ? value.name : ""
    };
  } catch {
    return fallback;
  }
}

export function saveOperator(
  operator: Operator,
  storage: Storage | undefined = safeStorage()
): void {
  if (!storage) return;
  try {
    storage.setItem(OPERATOR_STORAGE_KEY, JSON.stringify(operator));
  } catch {
    // A full or blocked store must not prevent the rest of the session.
  }
}

/**
 * An approval needs a name a reader can recognise months later.
 *
 * Nothing is defaulted: an approver the user never chose would attribute a
 * decision to a placeholder.
 */
export function isConfigured(operator: Operator): boolean {
  return operator.name.trim().length > 0;
}

function safeStorage(): Storage | undefined {
  try {
    return globalThis.localStorage;
  } catch {
    return undefined;
  }
}
