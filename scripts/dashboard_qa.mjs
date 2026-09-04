/**
 * Visual QA for the published AI/BI dashboard.
 *
 * The problem this solves: `lakeview.create` accepts a serialized dashboard whose widget specs are
 * wrong. The API validates the envelope, not the encodings — so a bad `fieldName` or an unsupported
 * `widgetType` deploys cleanly and then renders as an empty tile with an error badge. Nothing short
 * of loading the page in a browser tells you which of the two you have.
 *
 * Auth is the awkward part. The dashboard page needs the user's Databricks SSO session, and Chrome
 * refuses to open a second instance on a profile that is already running. So instead of fighting for
 * the live profile, this COPIES the pieces that carry the session (`Local State` holds the key that
 * encrypts `Cookies`, and both must travel together or the cookies decrypt to nothing) into a
 * throwaway user-data-dir. The original profile is opened read-only and never written to.
 *
 *   node scripts/dashboard_qa.mjs <dashboard_id>
 */
import { execSync, spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import puppeteer from "puppeteer-core";

const DASHBOARD_ID = process.argv[2];
const HOST = process.env.DBX_HOST;
if (!HOST) { console.error("set DBX_HOST to your workspace URL"); process.exit(2); }
if (!DASHBOARD_ID) { console.error("usage: node scripts/dashboard_qa.mjs <dashboard_id>"); process.exit(2); }

const SRC = path.join(os.homedir(), "Library/Application Support/Google/Chrome");
const DIR = "/tmp/chrome-dash-qa";
const OUT = "/tmp/qa";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

fs.rmSync(DIR, { recursive: true, force: true });
fs.mkdirSync(path.join(DIR, "Default"), { recursive: true });
fs.mkdirSync(OUT, { recursive: true });
for (const [from, to] of [["Local State", "Local State"], ["Default/Cookies", "Default/Cookies"],
                          ["Default/Preferences", "Default/Preferences"]]) {
  const s = path.join(SRC, from);
  if (fs.existsSync(s)) fs.copyFileSync(s, path.join(DIR, to));
  else console.log(`  (no ${from} to copy)`);
}

const chrome = spawn(CHROME, [
  "--headless=new", "--remote-debugging-port=9333", `--user-data-dir=${DIR}`,
  "--no-first-run", "--no-default-browser-check", "--window-size=1600,1200",
], { stdio: "ignore", detached: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let browser;
for (let i = 0; i < 40; i++) {
  try { browser = await puppeteer.connect({ browserURL: "http://127.0.0.1:9333" }); break; }
  catch { await sleep(500); }
}
if (!browser) { chrome.kill(); console.error("could not attach to Chrome"); process.exit(1); }

const problems = [];
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 1200 });
await page.setCacheEnabled(false);   // a stale bundle once hid a fix for an entire debugging round
page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text().slice(0, 200)}`); });
page.on("pageerror", (e) => problems.push(`pageerror: ${String(e).slice(0, 200)}`));
page.on("requestfailed", (r) => problems.push(`requestfailed: ${r.url().slice(0, 120)}`));
page.on("response", (r) => { if (r.status() >= 400) problems.push(`http ${r.status()}: ${r.url().slice(0, 120)}`); });

const url = `${HOST}/dashboardsv3/${DASHBOARD_ID}/published`;
console.log("opening", url);
await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90000 });
await sleep(35000);   // tiles run real SQL on a warehouse that may be cold

const text = await page.evaluate(() => document.body.innerText);
if (/Continue with SSO|^\s*Log in\b|Single Sign-On/im.test(text) && text.length < 4000) {
  console.log("\nNOT AUTHENTICATED — the copied session did not carry. Verify the dashboard by hand.");
  await page.screenshot({ path: `${OUT}/dash-auth.png`, fullPage: true });
  await browser.disconnect(); try { process.kill(-chrome.pid); } catch {} process.exit(3);
}

await page.screenshot({ path: `${OUT}/dash-1-collections.png`, fullPage: true });
console.log("captured page 1");

// Walk the page tabs the dashboard renders for its three pages.
const tabs = ["Service & Grievance", "RM Performance & Incentive Integrity"];
for (let i = 0; i < tabs.length; i++) {
  const clicked = await page.evaluate((label) => {
    const el = [...document.querySelectorAll("button,[role=tab],a")]
      .find((x) => (x.textContent || "").trim().startsWith(label.slice(0, 18)));
    if (el) { el.click(); return true; }
    return false;
  }, tabs[i]);
  if (!clicked) { problems.push(`could not find dashboard page tab "${tabs[i]}"`); continue; }
  await sleep(28000);
  await page.screenshot({ path: `${OUT}/dash-${i + 2}-${tabs[i].split(" ")[0].toLowerCase()}.png`, fullPage: true });
  console.log(`captured page ${i + 2}`);
}

const all = await page.evaluate(() => document.body.innerText);
// These are the strings AI/BI puts on a tile it could not render or could not run.
for (const bad of ["Widget error", "Unable to render", "Invalid widget", "unsupported",
                   "Dataset not found", "Unknown field", "AnalysisException", "does not exist"]) {
  if (all.includes(bad)) problems.push(`dashboard tile error text: "${bad}"`);
}
const markers = ["GNPA", "Delinquency", "Out-of-hours", "synthetic"];
for (const m of markers) console.log(`  marker "${m}":`, all.includes(m) ? "present" : "MISSING");

console.log("\n=== problems (" + problems.length + ") ===");
[...new Set(problems)].slice(0, 25).forEach((p) => console.log("  " + p));
await browser.disconnect();
try { process.kill(-chrome.pid); } catch {}
