/**
 * Step 8 PR #9 supplemental browser checks (Playwright).
 * Run: node frontend/scripts/verify-step8-pr9.mjs
 */
import { chromium } from "playwright";
import assert from "node:assert/strict";

const BASE = process.env.E2E_BASE_URL || "http://127.0.0.1:5173";
const EMAIL = process.env.E2E_EMAIL || "e2e-ai@example.com";
const PASSWORD = process.env.E2E_PASSWORD || "E2eAiTest!234";
const WS = process.env.E2E_WORKSPACE_ID || "517736a7-00e2-4f15-863c-794733770e2f";

async function login(page) {
  await page.goto(`${BASE}/login`);
  await page.locator('input[type="email"]').fill(EMAIL);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: "로그인" }).click();
  await page.waitForURL(/\/w\//, { timeout: 45000 });
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  page.setDefaultTimeout(60000);

  await login(page);

  // 1. Legacy route redirects
  await page.goto(`${BASE}/w/${WS}/ideas/new/ai/analyzing`);
  await page.waitForURL(new RegExp(`/w/${WS}/ideas/new/ai$`), { timeout: 15000 });
  assert.match(page.url(), new RegExp(`/w/${WS}/ideas/new/ai$`), "legacy analyzing redirect");
  assert.doesNotMatch(page.url(), /\/login/, "must not redirect to login");

  await page.goto(`${BASE}/w/${WS}/ideas/new/ai/review`);
  await page.waitForURL(new RegExp(`/w/${WS}/ideas/new/ai$`), { timeout: 15000 });
  assert.match(page.url(), new RegExp(`/w/${WS}/ideas/new/ai$`), "legacy review redirect");
  console.log("PASS legacy route redirects");

  // 2. Stale session response race (route A → B before A resolves)
  const sessionA = "00000000-0000-4000-8000-000000000001";
  const sessionB = "00000000-0000-4000-8000-000000000002";
  const textA = "STALE_SESSION_A_UNIQUE_MARKER_12345";
  const textB = "STALE_SESSION_B_UNIQUE_MARKER_67890";

  await page.route(`**/api/v1/workspaces/${WS}/ai-sessions/${sessionA}`, async (route) => {
    await new Promise((r) => setTimeout(r, 2500));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: sessionA,
        workspace_id: WS,
        purpose: "CREATE",
        status: "READY_FOR_REVIEW",
        input_text: textA,
        draft: { title: "Stale A Title" },
        field_provenance: null,
        clarifying_questions: null,
        clarification_answers: null,
        research_recommended: false,
        research_topics: null,
        result_idea_id: null,
        failure: null,
        llm: { provider: null, model: null, prompt_version: null },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        ready_at: null,
        confirmed_at: null,
      }),
    });
  });

  await page.route(`**/api/v1/workspaces/${WS}/ai-sessions/${sessionB}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: sessionB,
        workspace_id: WS,
        purpose: "CREATE",
        status: "READY_FOR_REVIEW",
        input_text: textB,
        draft: { title: "Fresh B Title" },
        field_provenance: null,
        clarifying_questions: null,
        clarification_answers: null,
        research_recommended: false,
        research_topics: null,
        result_idea_id: null,
        failure: null,
        llm: { provider: null, model: null, prompt_version: null },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        ready_at: null,
        confirmed_at: null,
      }),
    });
  });

  await page.goto(`${BASE}/w/${WS}/ideas/new/ai/review/${sessionA}?visibility=PRIVATE`);
  await page.waitForTimeout(300);
  await page.goto(`${BASE}/w/${WS}/ideas/new/ai/review/${sessionB}?visibility=PRIVATE`);
  await page.waitForSelector("text=Fresh B Title", { timeout: 15000 });
  await page.waitForTimeout(3000);
  const bodyText = await page.locator("body").innerText();
  assert.ok(bodyText.includes(textB), "B input_text visible");
  assert.ok(!bodyText.includes(textA), "stale A input_text must not appear");
  assert.ok(!bodyText.includes("Stale A Title"), "stale A draft must not appear");
  console.log("PASS stale session A→B fencing");

  await page.unrouteAll();

  // 3. Poll transient error recovery
  const pollSession = "00000000-0000-4000-8000-000000000099";
  let pollCount = 0;
  await page.route(`**/api/v1/workspaces/${WS}/ai-sessions/${pollSession}`, async (route) => {
    pollCount += 1;
    if (pollCount === 1) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: pollSession,
          workspace_id: WS,
          purpose: "CREATE",
          status: "PROCESSING",
          input_text: "poll recovery test",
          draft: null,
          field_provenance: null,
          clarifying_questions: null,
          clarification_answers: null,
          research_recommended: false,
          research_topics: null,
          result_idea_id: null,
          failure: null,
          llm: { provider: "openai_compatible", model: "Qwen3-14B", prompt_version: "v1" },
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          ready_at: null,
          confirmed_at: null,
        }),
      });
      return;
    }
    if (pollCount === 2) {
      await route.abort("failed");
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: pollSession,
        workspace_id: WS,
        purpose: "CREATE",
        status: pollCount >= 4 ? "READY_FOR_REVIEW" : "PROCESSING",
        input_text: "poll recovery test",
        draft: pollCount >= 4 ? { title: "Poll Recovery Ready" } : null,
        field_provenance: null,
        clarifying_questions: null,
        clarification_answers: null,
        research_recommended: false,
        research_topics: null,
        result_idea_id: null,
        failure: null,
        llm: { provider: "openai_compatible", model: "Qwen3-14B", prompt_version: "v1" },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        ready_at: pollCount >= 4 ? new Date().toISOString() : null,
        confirmed_at: null,
      }),
    });
  });

  await page.goto(`${BASE}/w/${WS}/ideas/new/ai/analyzing/${pollSession}?visibility=PRIVATE`);
  await page.waitForSelector("text=상태를 확인하지 못했습니다", { timeout: 20000 });
  await page.getByRole("button", { name: /초안 검토하기/ }).waitFor({ timeout: 25000 });
  console.log("PASS poll transient error recovery");

  await browser.close();
  console.log("PASS verify-step8-pr9");
}

main().catch((err) => {
  console.error("FAIL", err);
  process.exit(1);
});
