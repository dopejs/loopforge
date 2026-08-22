/**
 * The last of the invented provider data.
 *
 * The provider inventory, model roles and the configuration dialog are all
 * real now (see ./providers.ts). Kura exposes a fixed set of providers, so the
 * thirty-source catalogue this file used to hold described choices that could
 * not be made and has been removed.
 */

export type ProviderKind = "cloud" | "local" | "custom" | "account";

/** Tool names shown in Permissions, which the Agent does not expose yet. */
export const TOOL_CHIPS = [
  "read_file",
  "edit_file",
  "grep",
  "run_tests",
  "playtest_sim",
  "git",
  "shell (sandbox)",
  "asset_import"
] as const;
