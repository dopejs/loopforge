import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { IconRail } from "./components/IconRail";
import { Sidebar } from "./components/Sidebar";
import { AgentPanel } from "./components/AgentPanel";
import { Workspace, WorkspaceHeader } from "./components/Workspace";
import { Settings, type SettingsGroup } from "./components/Settings";
import { useAgent } from "./agent";
import { useI18n } from "./i18n";
import {
  type Appearance,
  accentColor,
  accentInk,
  loadAppearance,
  resolveTheme,
  saveAppearance
} from "./appearance";
import { type Mode, isWorkspaceMode, stepMode } from "./modes";
import {
  addProjectRoot,
  loadActiveProject,
  loadProjectRoots,
  rememberProject,
  saveProjectSelection,
  useRecentProjects
} from "./projects";
import { isApplePlatform, matchShortcut } from "./shortcuts";
import { errorMessage } from "./daemon";
import { startWindowDrag } from "./window";

const VERSION: string = __APP_VERSION__;

function usePrefersDark(): boolean {
  const [prefersDark, setPrefersDark] = useState(
    () => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true
  );
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!query) return;
    const onChange = (event: MediaQueryListEvent): void => setPrefersDark(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return prefersDark;
}

export function App(): React.JSX.Element {
  const { t, direction } = useI18n();
  const { preference: localePreference, setPreference: setLocalePreference } = useI18n();

  const [appearance, setAppearance] = useState<Appearance>(() => loadAppearance(localStorage));
  const [projectRoots, setProjectRoots] = useState<readonly string[]>(() =>
    loadProjectRoots(localStorage)
  );
  const [projectRoot, setProjectRoot] = useState(() => {
    const roots = loadProjectRoots(localStorage);
    // Honour "restore last project" on the very first render, before any
    // effect has had a chance to run.
    return loadAppearance(localStorage).restoreLastProject
      ? loadActiveProject(localStorage, roots)
      : "";
  });
  const [mode, setMode] = useState<Mode>("chat");
  const [settingsGroup, setSettingsGroup] = useState<SettingsGroup>("general");
  const [menuOpen, setMenuOpen] = useState(false);
  const [panelVisible, setPanelVisible] = useState(true);
  const [addingProject, setAddingProject] = useState(false);
  const [projectError, setProjectError] = useState<string>();

  const composerRef = useRef<HTMLTextAreaElement>(null);
  const agent = useAgent(projectRoot);
  const prefersDark = usePrefersDark();
  const theme = resolveTheme(appearance.theme, prefersDark);
  const apple = useMemo(
    () => isApplePlatform(typeof navigator === "undefined" ? "" : navigator.platform || navigator.userAgent),
    []
  );

  useEffect(() => {
    // The cache that makes the next launch's first render correct.
    saveProjectSelection(localStorage, [...projectRoots], projectRoot);
  }, [projectRoot, projectRoots]);

  // The store is authoritative; the cached list above is what the window
  // opened with. Merging rather than replacing keeps a project added in this
  // session visible even if recording it has not landed yet.
  const { projects: storedProjects, loaded: storeLoaded } = useRecentProjects();
  useEffect(() => {
    if (!storeLoaded || storedProjects.length === 0) return;
    setProjectRoots((current) => {
      const merged = [...storedProjects.map((item) => item.path), ...current];
      const unique = [...new Set(merged.filter(Boolean))];
      return unique.length === current.length && unique.every((v, i) => v === current[i])
        ? current
        : unique;
    });
  }, [storeLoaded, storedProjects]);

  // Recorded when the active project changes, which is also when the mode a
  // user left it in is worth keeping.
  useEffect(() => {
    if (projectRoot) rememberProject(projectRoot, mode);
  }, [projectRoot]);

  useEffect(() => {
    saveAppearance(localStorage, appearance);
  }, [appearance]);

  // Theme, density and accent are all expressed as data attributes and custom
  // properties on the shell root so the whole stylesheet can key off them.
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.dataset.density = appearance.density;
    root.style.setProperty("--accent", accentColor(appearance.accent));
    root.style.setProperty("--accentInk", accentInk(appearance.accent));
    root.style.setProperty("--accentSoft", `${accentColor(appearance.accent)}26`);
  }, [appearance.accent, appearance.density, theme]);

  // macOS draws the traffic lights over the client area, so reserve a strip for
  // them. Other platforms keep their own title bar and need no inset.
  useEffect(() => {
    document.documentElement.style.setProperty("--titlebar-inset", apple ? "28px" : "0px");
  }, [apple]);

  const changeAppearance = useCallback((patch: Partial<Appearance>): void => {
    setAppearance((current) => ({ ...current, ...patch }));
  }, []);

  const addProject = useCallback(async (): Promise<void> => {
    if (addingProject) return;
    setAddingProject(true);
    setProjectError(undefined);
    try {
      const selected = await invoke<string | null>("select_project_directory");
      if (selected) {
        setProjectRoots((roots) => addProjectRoot([...roots], selected));
        setProjectRoot(selected);
        setMenuOpen(false);
      }
    } catch (error) {
      setProjectError(errorMessage(error, t("error.selectProject")));
    } finally {
      setAddingProject(false);
    }
  }, [addingProject, t]);

  const selectProject = useCallback(
    (root: string): void => {
      if (root === projectRoot) {
        setMenuOpen(false);
        return;
      }
      setProjectRoot(root);
      setMenuOpen(false);
    },
    [projectRoot]
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      const action = matchShortcut(event, apple);
      if (!action) return;
      event.preventDefault();
      switch (action) {
        case "nextMode":
          setMode((current) => stepMode(current, 1));
          break;
        case "previousMode":
          setMode((current) => stepMode(current, -1));
          break;
        case "focusComposer":
          setPanelVisible(true);
          // Let the panel mount before moving focus into it.
          window.requestAnimationFrame(() => composerRef.current?.focus());
          break;
        case "projectMenu":
          setMode((current) => (current === "settings" ? "chat" : current));
          setMenuOpen((open) => !open);
          break;
        case "settings":
          setMode((current) => (current === "settings" ? "chat" : "settings"));
          break;
        case "toggleAgentPanel":
          setPanelVisible((visible) => !visible);
          break;
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [apple]);

  const running = agent.phase === "ready" || agent.phase === "starting";

  return (
    <div className="shell" dir={direction}>
      <div className="titlebar" onMouseDown={startWindowDrag} />
      <div className="shell-columns">
        <IconRail mode={mode} onSelect={setMode} />

        {mode === "settings" ? (
          <Settings
            group={settingsGroup}
            appearance={appearance}
            localePreference={localePreference}
            projectRoot={projectRoot}
            version={VERSION}
            onSelectGroup={setSettingsGroup}
            onChangeAppearance={changeAppearance}
            onChangeLocale={setLocalePreference}
            onClose={() => setMode("chat")}
          />
        ) : (
          <>
            <Sidebar
              mode={mode}
              projectRoot={projectRoot}
              projectRoots={projectRoots}
              menuOpen={menuOpen}
              busy={addingProject || agent.lifecycleBusy}
              agentPhase={agent.phase}
              agentState={agent.state}
              sessionId={agent.sessionId}
              turns={agent.turns}
              onOpenSession={(id) => void agent.openSession(id)}
              onNewSession={agent.newSession}
              onToggleMenu={() => setMenuOpen((open) => !open)}
              onCloseMenu={() => setMenuOpen(false)}
              onSelectProject={selectProject}
              onAddProject={() => void addProject()}
            />

            <main className="workspace">
              <WorkspaceHeader
                mode={mode}
                running={running}
                busy={agent.lifecycleBusy}
                disabled={!projectRoot || agent.phase === "unsupported"}
                onToggleRun={() => void (running ? agent.stop() : agent.start())}
              />
              {projectError && (
                <p className="workspace-error" role="alert">
                  {projectError}
                </p>
              )}
              <Workspace
                mode={mode}
                projectRoot={projectRoot}
                agentPhase={agent.phase}
                agentState={agent.state}
                transcript={agent.transcript}
                busy={agent.busy}
                composerRef={composerRef}
                onSend={(query) => void agent.send(query)}
                onAddProject={() => void addProject()}
                addingProject={addingProject}
              />
            </main>

            {panelVisible && isWorkspaceMode(mode) && mode !== "chat" && (
              <AgentPanel
                phase={agent.phase}
                state={agent.state}
                transcript={agent.transcript}
                busy={agent.busy}
                composerRef={composerRef}
                onSend={(query) => void agent.send(query)}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
