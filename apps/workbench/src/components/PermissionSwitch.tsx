import React, { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n/locales/en";
import { savePermissionMode, usePermissions } from "../approvals";

/**
 * How much the agent may do without asking, beside the box you ask in.
 *
 * It used to live only in Settings, and that is the wrong place for it: this
 * governs the turn you are about to send, and it changes as the work does --
 * tightened the moment the agent does something surprising, loosened before
 * asking it to write twenty files. Set once in a settings page, it is a
 * setting nobody remembers exists, and the moment you most want to change it
 * you are looking at the transcript, not at settings.
 *
 * Settings keeps its copy. Both read the runtime and both write through the
 * same call, so neither is a second source of truth -- and someone browsing
 * what the app can do should still find this among it.
 */
/**
 * The modes this build has a name for.
 *
 * Listed rather than derived, and that is the one thing here that is: the set
 * of modes comes from the runtime, so a mode added there arrives with no
 * translation. Showing its id -- `allow-edit` -- is worse than a translation
 * and much better than a missing-key crash or the key itself on a button.
 */
const MODE_KEYS: Record<string, MessageKey> = {
  ask: "permission.mode.ask",
  "allow-edit": "permission.mode.allow-edit",
  auto: "permission.mode.auto"
};

export function PermissionSwitch({
  projectRoot,
  enabled
}: {
  projectRoot: string;
  /** Only while the Agent could answer; a dead one has no mode to report. */
  enabled: boolean;
}): React.JSX.Element | null {
  const { t } = useI18n();
  const { permissions, reload } = usePermissions(projectRoot, enabled);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);

  // A menu that outlives the click that dismissed it is a menu that covers
  // whatever you clicked next.
  useEffect(() => {
    if (!open) return;
    const dismiss = (event: MouseEvent): void => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", dismiss);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", dismiss);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  if (!permissions) return null;

  const label = (mode: string): string => {
    const key = MODE_KEYS[mode];
    return key ? t(key) : mode;
  };

  const choose = async (mode: string): Promise<void> => {
    if (saving || mode === permissions.mode) {
      setOpen(false);
      return;
    }
    setSaving(true);
    try {
      await savePermissionMode(projectRoot, mode);
      reload();
      setOpen(false);
    } catch {
      // Left as it was. Reporting a mode the runtime did not accept would be
      // worse than saying nothing: someone would send a turn believing the
      // agent is more restricted than it is.
      reload();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="permission-switch" ref={wrapper}>
      <button
        type="button"
        className="composer-chip"
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={saving}
        onClick={() => setOpen((value) => !value)}
      >
        {label(permissions.mode)}
      </button>
      {open && (
        <ul className="permission-menu" role="listbox" aria-label={t("permission.label")}>
          {/*
            The choices come from the runtime, not from a list kept here: a
            list maintained in the interface is a list that describes an older
            build. The summaries do too -- what a mode means is the runtime's
            answer, and a second wording of it would drift.
          */}
          {permissions.modes.map((choice) => (
            <li key={choice.mode}>
              <button
                type="button"
                role="option"
                aria-selected={choice.mode === permissions.mode}
                className={
                  choice.mode === permissions.mode
                    ? "permission-option active"
                    : "permission-option"
                }
                onClick={() => void choose(choice.mode)}
              >
                <span className="permission-option-name">
                  {label(choice.mode)}
                </span>
                <span className="permission-option-summary">{choice.summary}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
