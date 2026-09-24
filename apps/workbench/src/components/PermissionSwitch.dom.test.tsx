/**
 * @vitest-environment jsdom
 */
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

/**
 * How much the agent may do, beside the box you ask in.
 *
 * It used to live only in Settings, which is the wrong place: this governs the
 * turn you are about to send, and it changes as the work does -- tightened the
 * moment the agent does something surprising, loosened before asking it to
 * write twenty files. Set once in a settings page it is a setting nobody
 * remembers exists, and the moment you most want it you are looking at the
 * transcript.
 */

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("../agent", async () => {
  const actual = await vi.importActual<typeof import("../agent")>("../agent");
  return { ...actual, isDesktopRuntime: () => true };
});
vi.mock("../i18n", async () => {
  const { en } = await import("../i18n/locales/en");
  return {
    useI18n: () => ({
      locale: "en",
      t: (key: string) => {
        const template = (en as Record<string, string>)[key];
        if (template === undefined) throw new Error(`missing message key: ${key}`);
        return template;
      }
    })
  };
});

const { PermissionSwitch } = await import("./PermissionSwitch");

const MODES = [
  { mode: "ask", summary: "Ask before anything that changes the project." },
  { mode: "allow-edit", summary: "Run builds and captures without asking." },
  { mode: "auto", summary: "Never ask." }
];

function serving(mode: string) {
  invoke.mockImplementation((command: string) => {
    if (command === "agent_permissions") {
      return Promise.resolve({
        schema_version: "loopforge-permission-v1",
        mode,
        summary: "",
        modes: MODES
      });
    }
    return Promise.resolve({
      schema_version: "loopforge-permission-v1",
      mode,
      summary: "",
      modes: MODES
    });
  });
}

afterEach(() => {
  cleanup();
  invoke.mockReset();
});

describe("PermissionSwitch", () => {
  it("shows the mode the runtime is actually in", async () => {
    serving("allow-edit");
    render(<PermissionSwitch projectRoot="/p" enabled />);

    expect(await screen.findByRole("button", { name: "Allow edits" })).toBeTruthy();
  });

  it("shows nothing until the runtime has answered", () => {
    // A switch that guessed a mode would tell someone the agent is more
    // restricted than it is, which is the wrong way to be wrong.
    serving("ask");
    const { container } = render(<PermissionSwitch projectRoot="/p" enabled />);

    expect(container.textContent).toBe("");
  });

  it("offers every mode the runtime has, with what each one means", async () => {
    // Listed by the runtime rather than here: a list kept in the interface is
    // a list that describes an older build.
    serving("ask");
    render(<PermissionSwitch projectRoot="/p" enabled />);
    fireEvent.click(await screen.findByRole("button", { name: "Ask first" }));

    expect(screen.getByRole("option", { name: /Allow edits/ })).toBeTruthy();
    expect(screen.getByRole("option", { name: /Don't ask/ })).toBeTruthy();
    expect(screen.getByText(/Ask before anything that changes the project/)).toBeTruthy();
  });

  it("saves the mode that was picked", async () => {
    serving("ask");
    render(<PermissionSwitch projectRoot="/p" enabled />);
    fireEvent.click(await screen.findByRole("button", { name: "Ask first" }));
    fireEvent.click(screen.getByRole("option", { name: /Allow edits/ }));

    await waitFor(() => {
      const call = invoke.mock.calls.find((entry) => entry[0] === "agent_save_permissions");
      expect(call).toBeTruthy();
      expect((call![1] as Record<string, unknown>).mode).toBe("allow-edit");
    });
  });

  it("marks which mode is current", async () => {
    serving("auto");
    render(<PermissionSwitch projectRoot="/p" enabled />);
    fireEvent.click(await screen.findByRole("button", { name: "Don't ask" }));

    expect(
      screen.getByRole("option", { name: /Don't ask/ }).getAttribute("aria-selected")
    ).toBe("true");
    expect(
      screen.getByRole("option", { name: /Ask first/ }).getAttribute("aria-selected")
    ).toBe("false");
  });

  it("closes without saving when the same mode is picked again", async () => {
    serving("ask");
    render(<PermissionSwitch projectRoot="/p" enabled />);
    fireEvent.click(await screen.findByRole("button", { name: "Ask first" }));
    fireEvent.click(screen.getByRole("option", { name: /Ask first/ }));

    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
    expect(
      invoke.mock.calls.find((entry) => entry[0] === "agent_save_permissions")
    ).toBeUndefined();
  });

  it("closes when something outside it is clicked", async () => {
    // A menu that outlives the click that dismissed it covers whatever was
    // clicked next -- here, the box you were about to type in.
    serving("ask");
    render(<PermissionSwitch projectRoot="/p" enabled />);
    fireEvent.click(await screen.findByRole("button", { name: "Ask first" }));
    expect(screen.getByRole("listbox")).toBeTruthy();

    fireEvent.mouseDown(document.body);

    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
  });

  it("closes on Escape", async () => {
    serving("ask");
    render(<PermissionSwitch projectRoot="/p" enabled />);
    fireEvent.click(await screen.findByRole("button", { name: "Ask first" }));

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
  });

  it("asks the runtime for nothing when the Agent is not running", async () => {
    serving("ask");
    render(<PermissionSwitch projectRoot="/p" enabled={false} />);

    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(invoke).not.toHaveBeenCalled();
  });

  it("shows a mode this build has no name for rather than crashing", async () => {
    // The set of modes comes from the runtime. One added there arrives with no
    // translation, and its id is worse than a name and far better than a
    // missing-key crash.
    invoke.mockImplementation(() =>
      Promise.resolve({
        schema_version: "loopforge-permission-v1",
        mode: "supervised",
        summary: "",
        modes: [{ mode: "supervised", summary: "Something later." }]
      })
    );
    render(<PermissionSwitch projectRoot="/p" enabled />);

    expect(await screen.findByRole("button", { name: "supervised" })).toBeTruthy();
  });
});
