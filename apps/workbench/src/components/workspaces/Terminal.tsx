import React from "react";
import { LOG_LINES } from "../../fixtures";

export function TerminalWorkspace(): React.JSX.Element {
  return (
    <div className="workspace-body">
      <div className="terminal-body">
        {LOG_LINES.map((line, index) => (
          <div key={index} className="log-line">
            <span className="log-time">{line.time}</span>
            <span className={`log-level level-${line.level.toLowerCase()}`}>{line.level}</span>
            <span className="log-message">{line.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
