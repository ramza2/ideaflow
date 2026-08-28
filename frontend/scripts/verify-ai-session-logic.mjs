/**
 * Lightweight verification for useAiSession pure helpers (no test runner).
 * Run: node frontend/scripts/verify-ai-session-logic.mjs
 */
import assert from "node:assert/strict";

// Mirror pure helpers (keep in sync with useAiSession.ts)
function sessionRequestKey(workspaceId, sessionId) {
  if (!workspaceId || !sessionId) return null;
  return `${workspaceId}:${sessionId}`;
}

function shouldApplySessionResponse(activeKey, requestKey, cancelled) {
  return !cancelled && activeKey === requestKey;
}

function mapProvenanceSource(source) {
  switch (source) {
    case "USER_INPUT":
      return "user_input";
    case "LLM_SUMMARY":
      return "llm_structured";
    case "LLM_INFERENCE":
      return "llm_inferred";
    case "WEB_EVIDENCE":
      return "web_evidence";
    case "USER_EDIT":
      return "user_edited";
    default:
      return null;
  }
}

function shouldContinuePolling(status) {
  return status === "PROCESSING";
}

// --- sessionRequestKey ---
assert.equal(sessionRequestKey("ws", "sid"), "ws:sid");
assert.equal(sessionRequestKey(undefined, "sid"), null);

// --- shouldApplySessionResponse (stale A→B fencing) ---
const keyA = "ws:a";
const keyB = "ws:b";
assert.equal(shouldApplySessionResponse(keyB, keyA, false), false, "stale A must not apply on B");
assert.equal(shouldApplySessionResponse(keyB, keyB, false), true);
assert.equal(shouldApplySessionResponse(keyB, keyB, true), false, "cancelled blocks apply");

// --- mapProvenanceSource ---
assert.equal(mapProvenanceSource("LLM_SUMMARY"), "llm_structured");
assert.equal(mapProvenanceSource(undefined), null);
assert.equal(mapProvenanceSource("UNKNOWN"), null);

// --- shouldContinuePolling ---
assert.equal(shouldContinuePolling("PROCESSING"), true);
assert.equal(shouldContinuePolling("READY_FOR_REVIEW"), false);
assert.equal(shouldContinuePolling(null), false);

console.log("PASS verify-ai-session-logic");
