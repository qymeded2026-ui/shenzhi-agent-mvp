const path = require("path");
const { pathToFileURL } = require("url");
const { chromium } = require("playwright");

async function main() {
  const [, , inputPath, outputPath] = process.argv;
  if (!inputPath || !outputPath) {
    console.error("Usage: node scripts/html_to_pdf.cjs input.html output.pdf");
    process.exit(1);
  }

  const edgePath = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge";
  const browser = await chromium.launch({
    headless: true,
    executablePath: edgePath,
  });

  try {
    const page = await browser.newPage({ viewport: { width: 1240, height: 1754 } });
    const fileUrl = pathToFileURL(path.resolve(inputPath)).href;
    await page.goto(fileUrl, { waitUntil: "networkidle" });
    await page.pdf({
      path: outputPath,
      format: "A4",
      printBackground: true,
      preferCSSPageSize: true,
      margin: { top: "14mm", right: "12mm", bottom: "14mm", left: "12mm" },
    });
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
