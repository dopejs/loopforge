/**
 * Preview data for the workspaces whose Agent endpoints do not exist yet.
 *
 * This is placeholder content, not project data. It exists so the full
 * Workbench UI can be built, reviewed and styled ahead of the backend. Every
 * surface that renders it shows a "preview data" marker, and `isWired()` in
 * ./modes.ts decides which workspaces still depend on it.
 *
 * Content here is deliberately NOT translated: once an Agent capability lands,
 * these values are replaced by real project data (file names, test names, log
 * lines), which is never translated either.
 */

export const PREVIEW_PROJECT = {
  name: "星轨 Odyssey",
  engine: "Unity 2022.3",
  branch: "feat/boss-tuning",
  runId: "#3412"
} as const;

/* ------------------------------------------------------------------ canvas */

export const CANVAS_ASSETS = [
  { name: "concept_forge_guardian_v3.png", meta: "1024 × 768" },
  { name: "playtest_phase2_frame1842.png", meta: "1920 × 1080" }
] as const;

export const CANVAS_NOTE =
  "attackInterval 0.80 → 0.95, damageScale 1.40 → 1.19. Player deaths 4.2 → 2.6, and the share of players reaching phase three rose from 38% to 61%.";

export const CANVAS_FEEDBACK = {
  quote: "Phase two's fire pillars are too dense — there is no gap to move through.",
  author: "7 internal playtesters"
} as const;

export const CANVAS_TARGETS = [
  { id: "deaths", value: "2 – 3", ok: true },
  { id: "clear", value: "55 – 65%", ok: true },
  { id: "fps", value: "≥ 55", ok: false }
] as const;

export const DEATHS_PER_ATTEMPT = [
  5, 4, 6, 5, 4, 5, 3, 4, 5, 4, 3, 4, 3, 2, 3,
  3, 2, 3, 2, 2, 3, 2, 2, 1, 2, 3, 2, 2, 1, 2
] as const;

export const CANVAS_TOOLS = ["select", "hand", "note", "frame", "link", "image"] as const;
export type CanvasTool = (typeof CANVAS_TOOLS)[number];

/* -------------------------------------------------------------------- test */

export const TEST_STATS = [
  { id: "passed", value: "24", tone: "ok" },
  { id: "failed", value: "1", tone: "bad" },
  { id: "duration", value: "8.4s", tone: "text" },
  { id: "coverage", value: "71%", tone: "text" }
] as const;

export const TEST_SUITES = [
  { name: "BossRegression", count: "24 / 24", time: "3.1s", pass: 100, failed: false },
  { name: "CombatBalance", count: "18 / 18", time: "2.2s", pass: 100, failed: false },
  { name: "LightingBake", count: "5 / 6", time: "1.9s", pass: 83, failed: true },
  { name: "SaveMigration", count: "11 / 11", time: "0.8s", pass: 100, failed: false },
  { name: "Playtest sim", count: "3600 f", time: "4.2s", pass: 100, failed: false }
] as const;

export const TEST_FAILURE = {
  suite: "LightingBake · Level2_Bake_Deterministic",
  lines: [
    "Expected lightmap hash 0x8f21ac…",
    "Actual   lightmap hash 0x8f21bd…"
  ],
  at: "at LightingBakeTests.cs:118"
} as const;

export const PLAYTEST_FPS = [
  60, 60, 59, 58, 60, 57, 55, 58, 60, 59, 54, 52, 51, 55, 58,
  60, 59, 57, 56, 58, 60, 60, 59, 57, 53, 55, 58, 60, 59, 58
] as const;

export const PLAYTEST_SUMMARY = { avg: "58.7", min: "51", deaths: "2.6", clear: "61%" } as const;

/* ---------------------------------------------------------------- profiler */

export const PERF_STATS = [
  { id: "avgFrame", value: "16.2ms", tone: "ok" },
  { id: "p99Frame", value: "24.1ms", tone: "bad" },
  { id: "drawCalls", value: "1,842", tone: "text" },
  { id: "gcAlloc", value: "312 KB/s", tone: "text" }
] as const;

export const FRAME_TIMES = [
  14, 15, 16, 15, 17, 19, 22, 18, 16, 15, 14, 15, 16, 18, 21, 24, 19, 16, 15, 14,
  15, 16, 17, 16, 15, 14, 16, 18, 20, 17, 15, 14, 15, 16, 15, 14, 16, 17, 16, 15
] as const;

export const FRAME_BUDGET_MS = 16.6;

export const HOTSPOTS = [
  { name: "PillarVFX.Update()", ms: "4.82", calls: "3,600", delta: "−1.10", tone: "ok" },
  { name: "ForgeGuardian.PhaseTwoTick()", ms: "2.31", calls: "3,600", delta: "−0.42", tone: "ok" },
  { name: "Physics.Simulate", ms: "2.04", calls: "3,600", delta: "+0.03", tone: "faint" },
  { name: "Shadows.RenderCascade", ms: "1.77", calls: "10,800", delta: "+0.21", tone: "bad" },
  { name: "Audio.MixGroup(Boss)", ms: "0.94", calls: "3,600", delta: "−0.05", tone: "ok" }
] as const;

/* ---------------------------------------------------------------- terminal */

export type LogLevel = "INFO" | "PLAN" | "TOOL" | "EDIT" | "PASS" | "WARN" | "RUN";

export const LOG_LINES: readonly { time: string; level: LogLevel; message: string }[] = [
  { time: "09:42:01", level: "INFO", message: "session start · git @ feat/boss-tuning" },
  { time: "09:42:01", level: "PLAN", message: "4 steps · read → patch → test → playtest" },
  { time: "09:42:03", level: "TOOL", message: "read_file Assets/Scripts/Boss/ForgeGuardian.cs (412 lines)" },
  { time: "09:42:05", level: "TOOL", message: 'grep "phase2" Assets/Scripts/Boss → 7 matches' },
  { time: "09:42:09", level: "EDIT", message: "ForgeGuardian.cs +18 −6 · attackInterval 0.80 → 0.95" },
  { time: "09:42:10", level: "EDIT", message: "boss_tuning.json +6 −6 · damageScale 1.40 → 1.19" },
  { time: "09:42:11", level: "INFO", message: "unity batchmode compile … ok (6.2s)" },
  { time: "09:42:19", level: "PASS", message: "BossRegression · 24 passed, 0 failed in 8.4s" },
  { time: "09:42:20", level: "WARN", message: "LightingBake · Level2_Bake_Deterministic hash mismatch, flagged" },
  { time: "09:42:22", level: "INFO", message: "playtest sim start · 3600 frames · headless" },
  { time: "09:42:23", level: "RUN", message: "avg 59.1 fps · deaths 2 · phase2 reached at 00:38" }
];

/* ------------------------------------------------------------------- tasks */

export const TASK_BOARD = [
  {
    id: "backlog",
    cards: [
      { title: "Rewrite level 3 enemy AI patrol routes", tag: "gameplay", diff: null },
      { title: "Batch-compress audio assets ogg → 128k", tag: "assets", diff: null }
    ]
  },
  {
    id: "progress",
    cards: [{ title: "Boss “Forge Guardian” difficulty curve −15%", tag: "balance", diff: "+18 −6" }]
  },
  {
    id: "review",
    cards: [
      { title: "Inventory UI drag interaction and snap grid", tag: "ui", diff: "+240 −31" },
      { title: "Save migration script v3", tag: "tooling", diff: "+96 −8" }
    ]
  },
  {
    id: "done",
    cards: [
      { title: "Shader variant stripping −42 variants", tag: "perf", diff: "+12 −180" },
      { title: "Build time 6:12 → 3:48", tag: "build", diff: "+64 −22" }
    ]
  }
] as const;

/* ------------------------------------------------------------------ assets */

export const ASSETS = [
  { name: "fire_pillar_a.vfx", type: "VFX", meta: "2.1 MB", touched: true },
  { name: "fire_pillar_b.vfx", type: "VFX", meta: "2.4 MB", touched: false },
  { name: "forge_guardian.fbx", type: "MESH", meta: "18.6 MB · 12k tris", touched: false },
  { name: "guardian_albedo.png", type: "TEX", meta: "2048² · 5.2 MB", touched: false },
  { name: "boss_tuning.json", type: "CFG", meta: "4 KB", touched: true },
  { name: "boss_theme_loop.ogg", type: "AUD", meta: "3.8 MB · 128k", touched: false },
  { name: "arena_phase2.prefab", type: "PREFAB", meta: "96 KB", touched: false },
  { name: "concept_guardian_v3.png", type: "IMG", meta: "1024²", touched: false }
] as const;

/* ---------------------------------------------------------------- sidebar  */

export const SIDEBAR_ITEMS: Record<string, readonly { label: string; sub: string; meta?: string; tone?: "ok" | "bad" }[]> = {
  canvas: [
    { label: "Boss Phase 2 combat tuning", sub: "6 objects" },
    { label: "Level 3 patrol routes", sub: "12 objects" },
    { label: "Art direction reference wall", sub: "41 objects" }
  ],
  flow: [
    { label: "tune → test → review", sub: "5 nodes" },
    { label: "asset import batch", sub: "7 nodes" },
    { label: "nightly playtest sweep", sub: "9 nodes" },
    { label: "build & package", sub: "6 nodes" }
  ],
  test: [
    { label: "BossRegression", sub: "24 cases", meta: "PASS", tone: "ok" },
    { label: "CombatBalance", sub: "18 cases", meta: "PASS", tone: "ok" },
    { label: "LightingBake", sub: "6 cases", meta: "FAIL", tone: "bad" },
    { label: "SaveMigration", sub: "11 cases", meta: "PASS", tone: "ok" },
    { label: "Playtest sim", sub: "3600 frames", meta: "PASS", tone: "ok" }
  ],
  terminal: [
    { label: "#3412 boss tuning", sub: "3m 02s" },
    { label: "#3411 inventory UI", sub: "11m 40s" },
    { label: "#3410 save migration", sub: "6m 12s" },
    { label: "#3409 lighting bake", sub: "failed · 1m 08s", tone: "bad" }
  ],
  tasks: [
    { label: "All tasks", sub: "7 tasks" },
    { label: "Awaiting my review", sub: "2 tasks" },
    { label: "Agent scheduled", sub: "3 tasks" },
    { label: "Archived", sub: "58 tasks" }
  ],
  assets: [
    { label: "Assets/VFX", sub: "142 files" },
    { label: "Assets/Art/Boss", sub: "86 files" },
    { label: "Assets/Audio", sub: "311 files" },
    { label: "Assets/Prefabs", sub: "204 files" },
    { label: "Assets/Config", sub: "19 files" }
  ],
  profiler: [
    { label: "09:42 phase2", sub: "3600 frames" },
    { label: "08:10 phase2", sub: "3600 frames" },
    { label: "21:03 full run", sub: "18k frames" },
    { label: "15:44 level 3", sub: "7.2k frames" }
  ],
  chat: [
    { label: "Boss difficulty curve −15%", sub: "#3412" },
    { label: "Inventory UI drag", sub: "#3411" },
    { label: "Save migration v3", sub: "#3410" },
    { label: "Lighting bake sweep", sub: "#3409" }
  ]
};

/* ------------------------------------------------------------ agent panel  */

export const AGENT_PLAN = [
  { title: "Locate the phase 2 difficulty parameters", meta: "read_file · grep · 2 files", state: "done" },
  { title: "Adjust the curve and sync config", meta: "edit_file · +24 −12", state: "done" },
  { title: "Add regression tests", meta: "BossPhase2CurveTests · 24 cases", state: "done" },
  { title: "Verify feel with a playtest sim", meta: "3600 frames · headless", state: "active" }
] as const;

export const AGENT_TOOL_CALLS = [
  { name: "read_file", arg: "Assets/Scripts/Boss/ForgeGuardian.cs", result: "412 lines" },
  { name: "grep", arg: '"phase2" in Assets/Scripts/Boss', result: "7 matches" },
  { name: "edit_file", arg: "ForgeGuardian.cs · phase2 curve", result: "+18 −6" },
  { name: "run_tests", arg: "BossRegression", result: "24 passed · 8.4s" }
] as const;

export const COMPOSER_CHIPS = ["@file", "/test", "/playtest"] as const;

export const SESSION_USAGE = { provider: "Anthropic · claude-sonnet", usage: "38.2k tokens · $0.42" } as const;
