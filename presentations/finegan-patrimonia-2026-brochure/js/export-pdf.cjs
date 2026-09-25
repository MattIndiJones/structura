const { chromium } = require("playwright");
const fs = require("fs");

const sourceUrl = process.argv[2];
const outputPath = process.argv[3];

if (!sourceUrl || !outputPath) {
  throw new Error("Usage: node export-pdf.cjs <url> <output.pdf>");
}

(async () => {
  const browserCandidates = [
    process.env.CHROME_PATH,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
  ].filter(Boolean);
  const executablePath = browserCandidates.find((candidate) => fs.existsSync(candidate));
  const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const page = await browser.newPage();
  await page.goto(sourceUrl, { waitUntil: "networkidle" });
  await page.emulateMedia({ media: "print" });
  await page.pdf({
    path: outputPath,
    printBackground: true,
    preferCSSPageSize: true,
    width: "303mm",
    height: "216mm",
    margin: { top: 0, right: 0, bottom: 0, left: 0 }
  });
  await browser.close();
})();
