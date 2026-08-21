import React from "react";
import { useKey } from "../primitives";
import { TASK_BOARD } from "../../fixtures";

export function TasksWorkspace(): React.JSX.Element {
  const key = useKey();

  return (
    <div className="workspace-body padded">
      <div className="board-columns">
        {TASK_BOARD.map((column) => (
          <section key={column.id} className="board-column">
            <header className="column-head">
              <span className="column-title">{key("tasks", column.id)}</span>
              <span className="mono faint">{column.cards.length}</span>
            </header>
            {column.cards.map((card) => (
              <article key={card.title} className="task-card">
                <p className="task-title">{card.title}</p>
                <div className="task-meta">
                  <span className="tag">{card.tag}</span>
                  {card.diff && <span className="mono faint">{card.diff}</span>}
                </div>
              </article>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}
