import puppeteer from "puppeteer-core";

const BASE = "http://127.0.0.1:8899";
const OUT = "/tmp/qa";
const browser = await puppeteer.connect({ browserURL: "http://127.0.0.1:9222", defaultViewport: { width: 1440, height: 1000 } });
const page = await browser.newPage();
// Load-bearing. Without it Chrome serves the previous bundle from disk cache and the run "confirms"
// a fix that is not on the page — it cost an entire debugging round once, and did it again after the
// guard was documented but never actually written into this script.
await page.setCacheEnabled(false);

// Requests the embedded dashboard makes to the workspace UI are EXPECTED to fail here: this Chrome
// runs on a throwaway profile with no Databricks session, so /telemetry and /ui-flags return 401.
// Those are the iframe's own calls, not the app's, and counting them as defects would train everyone
// to ignore this list.
const EXPECTED_UNAUTH = /\/(telemetry(-unauth)?|ui-flags|config)\b/;

const problems = [];
// Same reasoning for console noise emitted by the embedded dashboard's own bundle.
const EXPECTED_CONSOLE = /safex|local override for deploymentMode|gocx|confx|telemetry-unauth/i;
page.on("console", (m) => {
  if (m.type() !== "error" && m.type() !== "warning") return;
  if (EXPECTED_CONSOLE.test(m.text())) return;
  problems.push(`console.${m.type()}: ${m.text().slice(0, 300)}`);
});
page.on("pageerror", (e) => problems.push(`pageerror: ${String(e).slice(0, 300)}`));
page.on("requestfailed", (r) => {
  if (!r.url().startsWith(BASE) && EXPECTED_UNAUTH.test(r.url())) return;
  // Third-party assets CANCELLED by teardown. The embedded dashboard's iframe is unmounted when the tab
  // changes, which aborts whatever workspace UI chunks it still had in flight. Measured: 17 such aborts
  // on one run and none on the next two, from the same build — entirely outside this application. A gate
  // that goes red at random is a gate people learn to ignore, which is the failure mode the comment above
  // is already guarding against. Anything from our OWN origin, and any non-abort failure, still counts.
  const why = r.failure()?.errorText ?? "";
  if (!r.url().startsWith(BASE) && /ERR_ABORTED/.test(why)) return;
  problems.push(`requestfailed: ${r.url().slice(0, 140)} ${why}`);
});
page.on("response", (r) => {
  if (r.status() < 400) return;
  if (r.status() === 401 && !r.url().startsWith(BASE) && EXPECTED_UNAUTH.test(r.url())) return;
  problems.push(`http ${r.status()}: ${r.url().replace(BASE, "").slice(0, 120)}`);
});

async function clickTab(label) {
  const ok = await page.evaluate((l) => {
    const b = [...document.querySelectorAll("nav button")].find((x) => x.textContent.trim() === l);
    if (b) { b.click(); return true; }
    return false;
  }, label);
  if (!ok) throw new Error(`tab '${label}' not found`);
  await new Promise((r) => setTimeout(r, 900));
}

// The three lanes now share ONE thread, so text from an earlier turn stays in the DOM. Asserting
// against document.body after that point is how a check passes without testing anything: waiting for
// "LN001135" succeeds instantly if a previous turn already resolved it. Every phase below therefore
// clears the thread first, which also exercises the clear button.
async function clearThread() {
  await page.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent.trim().startsWith("Clear thread"));
    if (b) b.click();
  });
  await page.waitForFunction(
    () => !/verified by unity_catalog:|score \d\.\d{3}/.test(document.body.innerText),
    { timeout: 15000 });
}

async function chip(text) {
  const ok = await page.evaluate((t) => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent.includes(t));
    if (b) { b.click(); return true; }
    return false;
  }, text);
  if (!ok) throw new Error(`example chip '${text}' not found`);
}

async function shot(name, waitMs = 0) {
  if (waitMs) await new Promise((r) => setTimeout(r, waitMs));
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
  const text = await page.evaluate(() => document.body.innerText);
  console.log(`--- ${name}: ${text.length} chars of text rendered`);
  return text;
}

await page.goto(BASE, { waitUntil: "networkidle2", timeout: 60000 });
await page.waitForFunction(() => document.body.innerText.includes("Genie Control Tower"), { timeout: 30000 });
const title = await page.title();
console.log("document title:", title);
// Assert the title POSITIVELY rather than denylisting whatever brand happened to be there before. The
// tab title once read another company's name for an entire session, inherited from a forked scaffold —
// but naming that company in the check just moves the problem into this file.
if (!/Genie Control Tower/i.test(title)) {
  problems.push(`page title is not the app's own: ${title}`);
}
// Analysis, the live call and the letter corpus are ONE screen now. Assert the merge positively:
// the three lanes must be gone from the nav, not merely present somewhere.
const tabs = await page.evaluate(() =>
  [...document.querySelectorAll("nav button")].map((b) => b.textContent.trim()));
console.log("tabs:", JSON.stringify(tabs));
const EXPECTED_TABS = ["Ask", "Dashboard", "Approvals", "Governance"];
if (JSON.stringify(tabs) !== JSON.stringify(EXPECTED_TABS)) {
  problems.push(`nav is ${JSON.stringify(tabs)}, expected ${JSON.stringify(EXPECTED_TABS)}`);
}

// THE APP MUST BE LIGHT EVEN FOR A VIEWER WHOSE OS IS IN DARK MODE. AppKit ships a
// prefers-color-scheme:dark block scoped to `:root:not(.light)` that outranks our own `:root`, so the
// theme depends on a class on <html> rather than on our stylesheet alone. Headless Chrome defaults to
// light, which is exactly why this went unnoticed until the built CSS was read by hand.
await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "dark" }]);
await new Promise((r) => setTimeout(r, 400));
// Compared as a RESOLVED TOKEN, not as a parsed colour. The first version of this check computed a
// luminance from `bg.match(/\d+/g)`, which on `oklch(0.141 0.005 285.823)` reads digits out of a decimal
// string — it happened to flag the regression and would not have survived a palette change. The light
// theme owns --background; if AppKit's dark block wins, that token is an oklch value, not our hex.
const LIGHT_BACKGROUND = "#f6f7f9";
const themeUnderDarkOS = await page.evaluate(() => ({
  token: getComputedStyle(document.documentElement).getPropertyValue("--background").trim(),
  pinned: document.documentElement.classList.contains("light"),
}));
console.log(`  under OS dark mode: --background = ${themeUnderDarkOS.token}, html.light = ${themeUnderDarkOS.pinned}`);
if (themeUnderDarkOS.token.toLowerCase() !== LIGHT_BACKGROUND) {
  problems.push(
    `app does not stay light for a viewer whose OS prefers dark: --background resolved to ` +
    `${themeUnderDarkOS.token}, expected ${LIGHT_BACKGROUND}. The light theme is not pinned ` +
    `(class="light" on <html> — see index.html).`);
}
await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "light" }]);

const askText = await shot("1-ask", 2500);
console.log("header sample:", askText.split("\n").slice(0, 8).join(" | "));
// The composer has to offer all three lanes from one place, or the merge only moved the seam.
for (const marker of ["Start a call", "Auto", "Analysis", "Live call", "Documents",
                      "Evaluate conduct at", "Call language"]) {
  const present = askText.includes(marker);
  console.log(`  composer control "${marker}":`, present ? "present" : "MISSING");
  if (!present) problems.push(`composer is missing the ${marker} control`);
}

// Documents lane — reached from the composer, not a tab.
await chip("agent came after dark");
// Retrieval + a governed read-back of every hit; allow for a cold warehouse.
await page.waitForFunction(
  () => /score \d\.\d{3}/.test(document.body.innerText), { timeout: 90000 });
const searchText = await shot("1b-documents-search", 1200);
const hitCount = (searchText.match(/score \d\.\d{3}/g) || []).length;
console.log("  semantic hits returned:", hitCount);
if (hitCount < 3) problems.push(`semantic search returned only ${hitCount} hits`);
console.log("  two-step governance note shown:",
  /re-read under YOUR entitlements/i.test(searchText));
if (!/re-read under YOUR entitlements/i.test(searchText)) {
  problems.push("search results do not explain that records were re-read under the caller's entitlements");
}
// Every hit must name an RBI ground, or the read-back silently failed.
console.log("  hits carry RBI ground:", /Recovery agents|Mis-selling|Payment systems/.test(searchText));

// A complaint id in the message opens the record and the letter side by side. This is also the auto
// router's docs branch: the chip forces no lane, the id decides it.
await chip("Open CM0009245");
await page.waitForFunction(
  () => /ground \(RBI\)/.test(document.body.innerText), { timeout: 90000 });
const docText = await shot("2-documents", 4000);
const routedDocs = /complaint CM0009245 is named/.test(docText);
console.log("  lane decision shown on the turn:", routedDocs);
if (!routedDocs) problems.push("the turn does not state which lane took it or why");
console.log("documents has letter text:", docText.includes("SYNTHETIC DOCUMENT"));
console.log("documents shows record:", docText.includes("Recovery agents") || docText.includes("ground (RBI)"));

// Wait for the HUD to actually resolve rather than sleeping and hoping. The first assist call runs
// several governed queries against a possibly-cold warehouse and took 16s once; a fixed 9s wait made
// the run report "account not resolved" for a HUD that was simply still loading, which is a flaky test
// masquerading as a defect.
async function waitForHud(expectId) {
  await page.waitForFunction(
    (id) => document.body.innerText.includes(id) && /verified by unity_catalog:/.test(document.body.innerText),
    { timeout: 90000 }, expectId);
}

// --- Call assist -----------------------------------------------------------
// Drive the lane the way an operator will: load the sample call, let the HUD resolve, then flip the
// clock to 21:45 IST and confirm the conduct banner actually CHANGES. A HUD that renders is not the
// same as a HUD that is evaluating anything, and the whole point of this tab is the refusal.
await clearThread();
await chip("Call that must stop");
await waitForHud("LN001135");
const voiceText = await shot("2-voice-current-clock", 500);
console.log("  voice resolved account:", voiceText.includes("LN001135"));
console.log("  voice resolved complaint:", voiceText.includes("CM0009245"));
// Deliberately not asserted: this shot uses the wall clock, so either verdict is correct depending
// on when the suite runs. Both sides are asserted explicitly below.
console.log("  conduct verdict on current clock:",
  /inside the 08:00-19:00 window/.test(voiceText) ? "inside window" : "outside window");
console.log("  grievance hold fires:", /open grievance/.test(voiceText));
console.log("  NPA flagged:", /NPA/.test(voiceText));
if (!/verified by unity_catalog:/.test(voiceText)) problems.push("voice: no verified_by provenance shown");

// Both sides of the RBI window, driven explicitly. The first version of this check read the wall
// clock and asserted the compliant path — which failed at 20:15 IST for the correct reason, because
// 20:15 really is outside the window. A conduct test whose expected result depends on what time the
// suite happens to run is not a test.
async function setClock(value, expectText) {
  // Target the clock select BY LABEL. It used to be `page.select("select", …)`, which takes the first
  // select on the page — and adding the language selector above it silently redirected every clock
  // change to the language dropdown. The run then timed out waiting for a verdict that could never
  // change. Positional selectors break the moment the UI grows.
  await page.select('select[aria-label="Conduct evaluation clock"]', value);
  if (expectText) {
    await page.waitForFunction((t) => document.body.innerText.includes(t), { timeout: 90000 }, expectText);
  } else {
    await new Promise((r) => setTimeout(r, 9000));
  }
}

await setClock("in", "10:30 IST is inside");
const inText = await shot("2b-voice-in-hours", 0);
const allowed = /10:30 IST is inside the 08:00-19:00 window/.test(inText);
console.log("  10:30 IST allowed:", allowed);
if (!allowed) problems.push("voice: 10:30 IST did not evaluate as inside the RBI conduct window");

await setClock("out", "21:45 IST is OUTSIDE");
const lateText = await shot("3-voice-out-of-hours", 0);
const refused = /21:45 IST is OUTSIDE the 08:00-19:00 window/.test(lateText);
console.log("  21:45 IST refusal shown:", refused);
if (!refused) problems.push("voice: 21:45 IST did not produce the out-of-hours refusal");
// Guards the exact bug this lane already had once: ist_hour() returns only the hour, so rendering it
// as "{hr}:00" printed a 21:45 call as "21:00 IST" — a time that never happened.
if (/2[01]:00 IST/.test(lateText)) problems.push("voice: banner shows a fabricated :00 minute rather than the real IST time");

// The compliant sample proves the HUD is not simply a red-light machine: with a current account and no
// open grievance every control must CLEAR. A panel that can only fail is not evidence of anything.
await setClock("in", "10:30 IST is inside");
await clearThread();
await chip("Call that may proceed");
await waitForHud("LN004703");
const conductText = await shot("3b-voice-compliant", 500);
const allClear = !/do not proceed with recovery/.test(conductText);
console.log("  compliant call clears every control:", allClear);
if (!allClear) problems.push("voice: the compliant sample (LN004703) still reports a failed control");
// Hard failures, not log lines. This sample was chosen BECAUSE the account has 66 attempts and 7 of
// them outside RBI hours, so an empty panel here means something is broken. It caught exactly that: a
// backend still serving the old column names while the new frontend read the new ones, so the panel
// rendered "no contact attempts are recorded" for an account with 66. A guard that turns a version
// skew into a reassuring empty state is worse than no guard.
const populated = /contact_attempts/.test(conductText);
const oohShown = /out_of_hours/.test(conductText);
console.log("  contact history populated:", populated);
console.log("  prior out-of-hours attempts shown:", oohShown);
if (!populated) problems.push("voice: contact history is empty for LN004703, which has recorded attempts");
if (!oohShown) problems.push("voice: out-of-hours attempts column missing from the contact-history panel");
if (/No contact attempts are recorded/.test(conductText)) {
  problems.push("voice: panel claims no contact attempts for LN004703, which has them — likely a frontend/backend field-name skew");
}
if (/attempts_90d|out_of_hours_90d|collected_90d/.test(conductText)) {
  problems.push("voice: contact history still labelled 90d, but the query applies no date filter");
}

// The Marathi sample proves the spoken-digit normaliser handles Devanagari, not only English. The
// thread is cleared first: LN001135 was already on screen from the earlier turn, and waiting for a
// string a previous turn put there is a check that cannot fail.
await clearThread();
await chip("मराठी");
await waitForHud("LN001135");
const mrText = await shot("3c-voice-marathi", 600);
console.log("  Marathi transcript resolved LN001135:", mrText.includes("LN001135"));
if (!mrText.includes("LN001135")) {
  problems.push("Marathi spoken digits did not resolve to a loan account");
}
const locales = await page.evaluate(() => {
  const el = document.querySelector('select[aria-label="Recogniser language"]');
  return el ? [...el.options].map((o) => o.value) : [];
});
console.log("  locale options:", JSON.stringify(locales));
if (!locales.includes("mr-IN")) problems.push("no Marathi locale in the recogniser selector");

// --- Dashboard -------------------------------------------------------------
// The iframe cannot render here: this Chrome runs on a throwaway profile with no Databricks session,
// which is exactly why the component ships an explanatory note rather than an empty grey box. Assert
// the frame is wired to the right dashboard and that the escape hatch is present.
await clickTab("Dashboard");
const dashText = await shot("4-dashboard", 6000);
const frame = await page.evaluate(() => {
  const f = document.querySelector("iframe");
  return f ? f.getAttribute("src") : null;
});
console.log("  iframe src:", frame);
if (!frame || !/\/embed\/dashboardsv3\/[0-9a-f]{32}$/.test(frame)) {
  problems.push(`dashboard: iframe src is not an embed URL with a dashboard id (${frame})`);
}
console.log("  open-in-workspace link:", dashText.includes("Open in workspace"));
console.log("  governance framing present:", /without embedded credentials/.test(dashText));

await clickTab("Approvals");
const apprText = await shot("5-approvals", 4000);
console.log("approvals rows:", (apprText.match(/schedule_field_visit|record_ptp|hold_incentive_payout|dispatch_customer_letter/g) || []).length);

await clickTab("Governance");
const govText = await shot("6-governance", 22000);
for (const marker of ["Kill switch", "Guardrail integrity", "What you are entitled to see",
                      "Enforced in Unity Catalog", "Conduct policies", "Usage"]) {
  console.log(`  governance panel "${marker}":`, govText.includes(marker) ? "rendered" : "MISSING");
}
console.log("  masked id shown:", /CU-[0-9a-f]{10}/.test(govText));

const unique = [...new Set(problems)];
console.log("\n=== problems (" + unique.length + ") ===");
unique.slice(0, 25).forEach((p) => console.log("  " + p));
await page.close();
await browser.disconnect();
// EXIT NON-ZERO on any problem. This printed its findings and exited 0, so every regression it detected —
// a missing composer control, a fabricated :00 IST minute — was a line of stdout that any wrapper or CI
// step read as a pass. A verification tool that cannot fail is not one.
process.exit(unique.length ? 1 : 0);
