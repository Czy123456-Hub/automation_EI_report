const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const assetsDir = process.argv[2];

if (!assetsDir) {
  console.error("Usage: node capture_el_nino_assets.js <assets-dir>");
  process.exit(2);
}

fs.mkdirSync(assetsDir, { recursive: true });

const IMD_PAGE_URL = "https://mausam.imd.gov.in/responsive/rainfallinformation.php?msg=C";
const IMD_RAINFALL_MAP_NAME = "imd_rainfall_cumulative.png";
const IMD_RAINFALL_LEGEND_NAME = "imd_rainfall_legend.svg";
const IMD_RAINFALL_FULL_NAME = "imd_rainfall_full.png";
const VCI_PAGE_URL =
  "https://www.star.nesdis.noaa.gov/smcd/emb/vci/VH/vh_adminMeanByCrop.php?type=Province_Weekly_MeanPlot";

const EXPORT_AMCHARTS_PNG_JS = `
async () => {
  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
  for (let i = 0; i < 80; i++) {
    const charts = (
      window.AmCharts &&
      window.AmCharts.charts &&
      Array.isArray(window.AmCharts.charts)
    ) ? window.AmCharts.charts : [];
    const chart = charts
      .filter(c => c && c.export && c.div && c.div.offsetWidth > 300 && c.div.offsetHeight > 300)
      .sort((a, b) => (b.div.offsetWidth * b.div.offsetHeight) - (a.div.offsetWidth * a.div.offsetHeight))[0];
    if (chart && chart.export) {
      return await new Promise((resolve, reject) => {
        try {
          chart.export.capture({}, function () {
            this.toCanvas({ backgroundColor: "#FFFFFF", multiplier: 2 }, function (canvas) {
              resolve(canvas.toDataURL("image/png"));
            });
          });
        } catch (err) {
          reject(String(err && err.stack ? err.stack : err));
        }
      });
    }
    await sleep(500);
  }
  throw new Error("没有找到可导出的 AmCharts 图表对象");
}
`;

const VCI_TARGETS = [
  {
    name: "Brazil Sao Paulo sugarcane VCI",
    countryPrefix: "20:",
    provincePrefix: "25:",
    crop: "sugarcane",
    vhType: "VCI",
    adminVersion: "GC_current",
    outName: "vci_brazil_sao_paulo_sugarcane.png",
  },
  {
    name: "China Guangxi sugarcane VCI",
    countryPrefix: "31:",
    provincePrefix: "7:",
    crop: "sugarcane",
    vhType: "VCI",
    adminVersion: "GC_current",
    outName: "vci_china_guangxi_sugarcane.png",
  },
  {
    name: "Thailand Nakhon Phanom sugarcane VCI",
    countryPrefix: "143:",
    provincePrefix: "27:",
    crop: "sugarcane",
    vhType: "VCI",
    adminVersion: "GC_current",
    outName: "vci_thailand_nakhon_phanom_sugarcane.png",
  },
];

function fileToDataUri(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const mimeType =
    ext === ".svg" ? "image/svg+xml" :
    ext === ".png" ? "image/png" :
    ext === ".jpg" || ext === ".jpeg" ? "image/jpeg" :
    ext === ".gif" ? "image/gif" :
    "application/octet-stream";
  const encoded = fs.readFileSync(filePath).toString("base64");
  return `data:${mimeType};base64,${encoded}`;
}

async function optionList(selectLocator) {
  return await selectLocator.locator("option").evaluateAll((options) =>
    options.map((o) => ({ value: o.value, text: (o.textContent || "").trim() }))
  );
}

async function selectOptionByRule(selectLocator, { prefix, exact }) {
  const options = await optionList(selectLocator);
  const match = options.find((opt) => {
    const text = opt.text.trim();
    if (prefix && text.startsWith(prefix)) return true;
    if (exact && text.toLowerCase() === exact.trim().toLowerCase()) return true;
    return false;
  });
  if (!match) {
    throw new Error(`没有找到下拉选项 prefix=${prefix || ""} exact=${exact || ""}`);
  }
  await selectLocator.selectOption(match.value);
  return match;
}

async function waitUntilOptionExists(page, selectLocator, prefix, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start <= timeoutMs) {
    const options = await optionList(selectLocator);
    if (options.some((opt) => opt.text.trim().startsWith(prefix))) return;
    await page.waitForTimeout(500);
  }
  throw new Error(`等待 Province 选项 ${prefix} 超时`);
}

async function applyVciSettings(page, target) {
  const selects = page.locator("select:visible");
  const count = await selects.count();
  if (count < 5) throw new Error(`页面可见 select 数量不足，当前只有 ${count} 个`);

  const countrySelect = selects.nth(0);
  const provinceSelect = selects.nth(1);
  const cropSelect = selects.nth(2);
  const vhSelect = selects.nth(3);
  const adminSelect = selects.nth(4);

  await selectOptionByRule(countrySelect, { prefix: target.countryPrefix });
  await waitUntilOptionExists(page, provinceSelect, target.provincePrefix);
  await selectOptionByRule(provinceSelect, { prefix: target.provincePrefix });
  await selectOptionByRule(cropSelect, { exact: target.crop });
  await selectOptionByRule(vhSelect, { exact: target.vhType });
  await selectOptionByRule(adminSelect, { exact: target.adminVersion });
}

async function clickRefresh(page) {
  const selectors = [
    "input[value='Refresh the plots']",
    "input[value*='Refresh']",
    "button:has-text('Refresh')",
    "text=Refresh the plots",
  ];
  for (const selector of selectors) {
    const loc = page.locator(selector);
    try {
      if ((await loc.count()) > 0) {
        await loc.first().click({ timeout: 8000 });
        return;
      }
    } catch (_) {}
  }
  throw new Error("没有找到 Refresh the plots 按钮");
}

async function screenshotVciPlotArea(page, outPath) {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(1200);

  const distributionY = await page.evaluate(() => {
    const needle = "Distribution Map with crop";
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    let best = null;
    while ((node = walker.nextNode())) {
      const text = (node.nodeValue || "").trim();
      if (text.includes(needle)) {
        const range = document.createRange();
        range.selectNodeContents(node);
        const rect = range.getBoundingClientRect();
        if (rect && rect.width > 0 && rect.height > 0) {
          const y = rect.top + window.scrollY;
          best = best === null ? y : Math.min(best, y);
        }
      }
    }
    return best;
  });

  const chart = await page.evaluate((distributionYValue) => {
    const limitY = distributionYValue ?? 10000;
    return Array.from(document.querySelectorAll("img, svg, canvas"))
      .map((el, index) => {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return {
          index,
          x: rect.left + window.scrollX,
          y: rect.top + window.scrollY,
          width: rect.width,
          height: rect.height,
          area: rect.width * rect.height,
          display: style.display,
          visibility: style.visibility,
        };
      })
      .filter((item) =>
        item.display !== "none" &&
        item.visibility !== "hidden" &&
        item.width >= 550 &&
        item.height >= 250 &&
        item.x >= 220 &&
        item.y < limitY - 20
      )
      .sort((a, b) => (Math.abs(a.y - b.y) > 20 ? a.y - b.y : b.area - a.area))[0] || null;
  }, distributionY);

  if (!chart) throw new Error("没有找到 VCI 图表区域");

  const pad = 8;
  await page.screenshot({
    path: outPath,
    clip: {
      x: Math.max(0, Math.floor(chart.x) - pad),
      y: Math.max(0, Math.floor(chart.y) - pad),
      width: Math.floor(chart.width) + pad * 2,
      height: Math.floor(chart.height) + pad * 2,
    },
  });
}

async function captureImdRainfall(browser) {
  const outPath = path.join(assetsDir, IMD_RAINFALL_MAP_NAME);
  const context = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
  const page = await context.newPage();
  try {
    await page.goto(IMD_PAGE_URL, { waitUntil: "networkidle", timeout: 90000 });
    await page.waitForTimeout(3000);
    const dataUrl = await page.evaluate(`(${EXPORT_AMCHARTS_PNG_JS})()`);
    if (!dataUrl || !dataUrl.includes(",")) {
      throw new Error("AmCharts 导出没有返回 PNG data URL");
    }
    fs.writeFileSync(outPath, Buffer.from(dataUrl.split(",", 2)[1], "base64"));
    console.log(`IMD Rainfall cumulative saved: ${outPath}`);
  } finally {
    await context.close();
  }
}

async function makeImdRainfallFullImage(browser) {
  const mapPath = path.join(assetsDir, IMD_RAINFALL_MAP_NAME);
  const legendPath = path.join(assetsDir, IMD_RAINFALL_LEGEND_NAME);
  const outPath = path.join(assetsDir, IMD_RAINFALL_FULL_NAME);

  if (!fs.existsSync(mapPath)) {
    throw new Error(`缺少 IMD 降雨地图：${mapPath}`);
  }
  if (!fs.existsSync(legendPath)) {
    throw new Error(`缺少 IMD 降雨图例：${legendPath}`);
  }

  const panelWidth = 1280;
  const legendWidth = 790;
  const mapSrc = fileToDataUri(mapPath);
  const legendSrc = fileToDataUri(legendPath);
  const context = await browser.newContext({
    viewport: { width: panelWidth, height: 1800 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  try {
    await page.setContent(`
      <!doctype html>
      <html>
      <head>
        <meta charset="utf-8">
        <style>
          html, body {
            margin: 0;
            padding: 0;
            background: #ffffff;
          }
          #shot {
            width: ${panelWidth}px;
            background: #ffffff;
            overflow: hidden;
            box-sizing: border-box;
            font-family: Arial, Helvetica, sans-serif;
          }
          .legend-wrap {
            width: 100%;
            box-sizing: border-box;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 22px 10px 6px;
            background: #ffffff;
          }
          .legend-wrap img {
            display: block;
            width: ${legendWidth}px;
            max-width: 100%;
            height: auto;
          }
          .map-wrap {
            width: 100%;
            background: #ffffff;
          }
          .map-wrap img {
            display: block;
            width: 100%;
            height: auto;
            background: #ffffff;
          }
        </style>
      </head>
      <body>
        <div id="shot">
          <div class="legend-wrap">
            <img src="${legendSrc}" alt="IMD rainfall legend">
          </div>
          <div class="map-wrap">
            <img src="${mapSrc}" alt="IMD rainfall map">
          </div>
        </div>
      </body>
      </html>
    `, { waitUntil: "load" });
    await page.waitForFunction(() =>
      Array.from(document.images).every((img) => img.complete && img.naturalWidth > 0)
    );
    await page.locator("#shot").screenshot({
      path: outPath,
      animations: "disabled",
    });
    console.log(`IMD Rainfall full image saved: ${outPath}`);
  } finally {
    await context.close();
  }
}

async function captureVciPlots(browser) {
  const context = await browser.newContext({
    viewport: { width: 1700, height: 1050 },
    deviceScaleFactor: 2,
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  });
  try {
    for (const target of VCI_TARGETS) {
      const page = await context.newPage();
      try {
        await page.goto(VCI_PAGE_URL, { waitUntil: "networkidle", timeout: 90000 });
        await applyVciSettings(page, target);
        await clickRefresh(page);
        await page.getByText("Averaged VCI", { exact: false }).first().waitFor({ timeout: 60000 }).catch(() => {});
        await page.waitForTimeout(3500);
        const outPath = path.join(assetsDir, target.outName);
        await screenshotVciPlotArea(page, outPath);
        console.log(`${target.name} saved: ${outPath}`);
      } finally {
        await page.close();
      }
    }
  } finally {
    await context.close();
  }
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    await captureImdRainfall(browser).catch((err) => {
      console.error(`WARNING: IMD Rainfall capture failed: ${err.message || err}`);
    });
    await makeImdRainfallFullImage(browser).catch((err) => {
      console.error(`WARNING: IMD Rainfall full image failed: ${err.message || err}`);
    });
    await captureVciPlots(browser).catch((err) => {
      console.error(`WARNING: VCI capture failed: ${err.message || err}`);
    });
  } finally {
    await browser.close();
  }
})().catch((err) => {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
