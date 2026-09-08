/**
 * Lightweight pure-function checks for Step 19 toast gating.
 * Run from frontend/: npx --yes tsx scripts/check-ai-task-toast.ts
 */
import {
  isTerminalAiTaskStatus,
  shouldEmitAiTaskCompletionToast,
} from "../src/ai/aiTaskDisplay";

type Case = {
  name: string;
  task: { type: "CREATE" | "REFINE" | "RESEARCH"; status: string; is_active: boolean };
  terminal: boolean;
  completionToast: boolean;
};

const cases: Case[] = [
  {
    name: "PROCESSING active",
    task: { type: "CREATE", status: "PROCESSING", is_active: true },
    terminal: false,
    completionToast: false,
  },
  {
    name: "PROCESSING → NEEDS_CLARIFICATION",
    task: { type: "CREATE", status: "NEEDS_CLARIFICATION", is_active: false },
    terminal: false,
    completionToast: false,
  },
  {
    name: "REFINE NEEDS_CLARIFICATION",
    task: { type: "REFINE", status: "NEEDS_CLARIFICATION", is_active: false },
    terminal: false,
    completionToast: false,
  },
  {
    name: "PROCESSING → READY_FOR_REVIEW",
    task: { type: "CREATE", status: "READY_FOR_REVIEW", is_active: false },
    terminal: true,
    completionToast: true,
  },
  {
    name: "PROCESSING → FAILED",
    task: { type: "CREATE", status: "FAILED", is_active: false },
    terminal: true,
    completionToast: false,
  },
  {
    name: "RESEARCH READY",
    task: { type: "RESEARCH", status: "READY", is_active: false },
    terminal: true,
    completionToast: true,
  },
  {
    name: "RESEARCH FAILED",
    task: { type: "RESEARCH", status: "FAILED", is_active: false },
    terminal: true,
    completionToast: false,
  },
];

let failed = 0;
for (const c of cases) {
  const terminal = isTerminalAiTaskStatus(c.task);
  const completionToast = shouldEmitAiTaskCompletionToast(c.task);
  if (terminal !== c.terminal || completionToast !== c.completionToast) {
    failed += 1;
    console.error(
      `FAIL ${c.name}: terminal=${terminal} (want ${c.terminal}), completionToast=${completionToast} (want ${c.completionToast})`,
    );
  } else {
    console.log(`OK   ${c.name}`);
  }
}

const wasActive = new Set(["session:1"]);
const notified = new Set<string>();
const afterClarification = {
  id: "session:1",
  type: "CREATE" as const,
  status: "NEEDS_CLARIFICATION",
  is_active: false,
};
const wouldToastClarification =
  wasActive.has(afterClarification.id) &&
  isTerminalAiTaskStatus(afterClarification) &&
  !notified.has(afterClarification.id);
if (wouldToastClarification) {
  failed += 1;
  console.error("FAIL transition PROCESSING→NEEDS_CLARIFICATION would toast");
} else {
  console.log("OK   transition PROCESSING→NEEDS_CLARIFICATION no toast");
}

const afterReady = {
  id: "session:1",
  type: "CREATE" as const,
  status: "READY_FOR_REVIEW",
  is_active: false,
};
const wouldToastReady =
  wasActive.has(afterReady.id) &&
  isTerminalAiTaskStatus(afterReady) &&
  !notified.has(afterReady.id);
if (!wouldToastReady) {
  failed += 1;
  console.error("FAIL transition PROCESSING→READY_FOR_REVIEW would not toast");
} else {
  notified.add(afterReady.id);
  console.log("OK   transition PROCESSING→READY_FOR_REVIEW toast once");
}

const wouldToastReadyAgain =
  wasActive.has(afterReady.id) &&
  isTerminalAiTaskStatus(afterReady) &&
  !notified.has(afterReady.id);
if (wouldToastReadyAgain) {
  failed += 1;
  console.error("FAIL repeated READY_FOR_REVIEW would toast again");
} else {
  console.log("OK   repeated READY_FOR_REVIEW no second toast");
}

if (failed > 0) {
  console.error(`\n${failed} check(s) failed`);
  throw new Error("aiTaskDisplay toast gating checks failed");
}
console.log("\nAll aiTaskDisplay toast gating checks passed");
