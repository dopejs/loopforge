import { beforeEach, describe, expect, it } from "vitest";
import {
  OPERATOR_STORAGE_KEY,
  isConfigured,
  loadOperator,
  saveOperator
} from "./operator";

function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => void map.set(key, value),
    removeItem: (key) => void map.delete(key),
    clear: () => map.clear(),
    key: (index) => [...map.keys()][index] ?? null,
    get length() {
      return map.size;
    }
  } as Storage;
}

describe("operator identity", () => {
  let storage: Storage;
  beforeEach(() => {
    storage = memoryStorage();
  });

  it("starts unconfigured with an id but no name", () => {
    const operator = loadOperator(storage);
    expect(operator.id).toMatch(/^op_/);
    expect(operator.name).toBe("");
    // Nothing is defaulted: an approval must name someone who chose to approve.
    expect(isConfigured(operator)).toBe(false);
  });

  it("round-trips a configured operator", () => {
    saveOperator({ id: "op_fixed", name: "Ada" }, storage);
    expect(loadOperator(storage)).toEqual({ id: "op_fixed", name: "Ada" });
  });

  it("keeps the id stable across a rename", () => {
    saveOperator({ id: "op_fixed", name: "Ada" }, storage);
    saveOperator({ ...loadOperator(storage), name: "Ada L" }, storage);
    expect(loadOperator(storage).id).toBe("op_fixed");
  });

  it("replaces a blank stored id rather than approving as nobody", () => {
    storage.setItem(OPERATOR_STORAGE_KEY, JSON.stringify({ id: "", name: "Ada" }));
    const operator = loadOperator(storage);
    expect(operator.id).toMatch(/^op_/);
    expect(operator.name).toBe("Ada");
  });

  it("survives corrupt storage", () => {
    storage.setItem(OPERATOR_STORAGE_KEY, "{not json");
    expect(loadOperator(storage).name).toBe("");
  });

  it("treats a whitespace name as unconfigured", () => {
    expect(isConfigured({ id: "op_1", name: "   " })).toBe(false);
  });
});
