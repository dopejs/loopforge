import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { errorMessage } from "./daemon";
import { isDesktopRuntime } from "./agent";

/**
 * Tool calls waiting on a person.
 *
 * A call the runtime holds open until someone answers. Nobody can approve what
 * they cannot see, so this is polled rather than read once: the question
 * appears while a turn is already running, and a surface that looked only on
 * mount would show nothing while the Agent sat waiting for it.
 */
export type Approval = {
  approval_id: string;
  action: string;
  server: string;
  tool: string;
  surface: string;
  /** What is being approved: the tool and the arguments, in words. */
  reason: string;
  requested_by: string;
  requested_at: string;
};

export type ApprovalList = {
  schema_version: "loopforge-approval-v1";
  approvals: readonly Approval[];
  reason?: string;
};

/**
 * How often to ask.
 *
 * The Agent gives a person three minutes to answer, so this is about how long a
 * question sits unseen rather than about load: a second is imperceptible next
 * to reading it, and anything slower makes the panel feel like it missed.
 */
const POLL_INTERVAL_MS = 1000;

export function useApprovals(projectRoot: string, enabled: boolean) {
  const [approvals, setApprovals] = useState<readonly Approval[]>([]);
  const [reason, setReason] = useState<string>();

  useEffect(() => {
    if (!enabled || !projectRoot || !isDesktopRuntime()) return;
    let cancelled = false;

    const read = async (): Promise<void> => {
      try {
        const list = await invoke<ApprovalList>("agent_approvals", {
          projectPath: projectRoot
        });
        if (cancelled) return;
        setApprovals(list.approvals ?? []);
        setReason(list.reason);
      } catch (error: unknown) {
        // A poll that fails is not worth surfacing on its own -- the Agent may
        // simply be starting -- but it must not leave a stale question on
        // screen that a click can no longer answer.
        if (!cancelled) {
          setApprovals([]);
          setReason(errorMessage(error, "Approvals unavailable"));
        }
      }
    };

    void read();
    const timer = window.setInterval(() => void read(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [enabled, projectRoot]);

  return { approvals, reason };
}

/** Answer one. The waiting call continues or stops immediately. */
export function resolveApproval(
  projectRoot: string,
  approvalId: string,
  approved: boolean,
  comment = ""
): Promise<ApprovalList> {
  return invoke<ApprovalList>("agent_resolve_approval", {
    projectPath: projectRoot,
    approvalId,
    approved,
    comment
  });
}

/**
 * How much the agent may do without asking.
 *
 * The choices come from the runtime rather than being listed here: a list
 * maintained in the interface is a list that describes an older build.
 */
export type PermissionChoice = {
  mode: string;
  summary: string;
};

export type Permissions = {
  schema_version: "loopforge-permission-v1";
  mode: string;
  summary: string;
  modes: readonly PermissionChoice[];
  reason?: string;
};

export function usePermissions(projectRoot: string, enabled: boolean) {
  const [permissions, setPermissions] = useState<Permissions | null>(null);
  const [reason, setReason] = useState<string>();
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    if (!enabled || !projectRoot || !isDesktopRuntime()) return;
    let cancelled = false;
    void invoke<Permissions>("agent_permissions", { projectPath: projectRoot })
      .then((result) => {
        if (!cancelled) setPermissions(result);
      })
      .catch((error: unknown) => {
        if (!cancelled) setReason(errorMessage(error, "Permissions unavailable"));
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, projectRoot, nonce]);

  return { permissions, reason, reload };
}

export function savePermissionMode(
  projectRoot: string,
  mode: string
): Promise<Permissions> {
  return invoke<Permissions>("agent_save_permissions", {
    projectPath: projectRoot,
    mode
  });
}
