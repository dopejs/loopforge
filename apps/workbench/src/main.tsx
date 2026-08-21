import { createRoot } from "react-dom/client";
import { App } from "./App";
import { I18nProvider } from "./i18n";
import "./styles.css";

const root = createRoot(document.getElementById("root")!);
// Deliberately not wrapped in StrictMode: its double-invoked effects would run
// the agent activation twice, and `agent_start` spawns a real sidecar process
// and writes runtime metadata, so a duplicate run can orphan a process.
root.render(
  <I18nProvider>
    <App />
  </I18nProvider>
);

if (import.meta.hot) {
  import.meta.hot.dispose(() => root.unmount());
}
