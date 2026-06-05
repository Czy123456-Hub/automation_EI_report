from __future__ import annotations

import base64
import csv
import json
import mimetypes
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from html import escape, unescape
from pathlib import Path
from urllib.parse import quote, urljoin
import urllib.request


ROOT = Path(os.environ.get("EL_NINO_ROOT", Path(__file__).resolve().parent)).resolve()
OUTPUT_DIR = Path(os.environ.get("EL_NINO_OUTPUT_DIR", ROOT / "outputs"))
if not OUTPUT_DIR.is_absolute():
    OUTPUT_DIR = ROOT / OUTPUT_DIR
RUNTIME_DIR = OUTPUT_DIR / "el_nino_tracker_runtime"
ASSETS_DIR = RUNTIME_DIR / "assets"
OUTPUT_HTML = Path(os.environ.get("EL_NINO_OUTPUT_HTML", OUTPUT_DIR / "厄尔尼诺指标跟踪.html"))
if not OUTPUT_HTML.is_absolute():
    OUTPUT_HTML = ROOT / OUTPUT_HTML
BROWSER_CAPTURE_SCRIPT = ROOT / "capture_el_nino_assets.js"

METRICS_PAYLOAD_JSON_PATH = ASSETS_DIR / "enso_metrics_for_html.json"
METRICS_LIST_JSON_PATH = ASSETS_DIR / "enso_metrics_latest.json"
METRICS_CSV_PATH = ASSETS_DIR / "enso_metrics_latest.csv"

HEADERS = {"User-Agent": "Ei-Nino-Dashboard/1.0"}
BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0"}
BOM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Codex builtin runtime)",
    "Referer": "https://www.bom.gov.au/climate/influences/graphs/?index=iod&period=weekly",
}

NINO34_URL = "https://psl.noaa.gov/data/correlation/nina34.anom.data"
SOI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/soi"
EQSOI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/reqsoi.for"
HEATCENTRA_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ocean/index/heat_content_index.txt"
HEATCENTRA_REGION = "160E-80W"
IOD_URL = f"https://www.bom.gov.au/clim_data/IDCK000072/iod_1.txt?{int(time.time())}="
IOD_SUMMARY_URL = "https://www.bom.gov.au/climate/enso/"
WEEKLY_NINO34_URL = "https://www.cpc.ncep.noaa.gov/data/indices/rel_wksst9120.txt"

CPC_30DAY_REGIONS = {
    "seasia": {
        "name": "Southeast Asia 30-Day Anomaly",
        "page_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/SEAsia/index.shtml",
        "fallback_img_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/SEAsia/daily/p.30day.figb.gif",
        "out_path": ASSETS_DIR / "cpc_seasia_30day_anom.gif",
    },
    "china": {
        "name": "China 30-Day Anomaly",
        "page_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/China/index.shtml",
        "fallback_img_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/China/daily/p.30day.figb.gif",
        "out_path": ASSETS_DIR / "cpc_china_30day_anom.gif",
    },
    "brazil": {
        "name": "Brazil 30-Day Anomaly",
        "page_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/Brazil/index.shtml",
        "fallback_img_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/Brazil/daily/p.30day.figb.gif",
        "out_path": ASSETS_DIR / "cpc_brazil_30day_anom.gif",
    },
}

CPC_WEEK1_PAGES = {
    "india": {
        "page_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/India/GFS_forecasts.shtml",
        "fallback_img_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/GFS/India_curr.p.gfs1b.gif",
        "out_path": ASSETS_DIR / "cpc_india_week1_anomaly.gif",
    },
    "seasia": {
        "page_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/SEAsia/GFS_forecasts.shtml",
        "fallback_img_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/GFS/SEAsia_curr.p.gfs1b.gif",
        "out_path": ASSETS_DIR / "cpc_seasia_week1_anomaly.gif",
    },
    "brazil": {
        "page_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/Brazil/GFS_forecasts.shtml",
        "fallback_img_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/GFS/BR_curr.p.gfs1b.gif",
        "out_path": ASSETS_DIR / "cpc_brazil_week1_anomaly.gif",
    },
    "china": {
        "page_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/China/GFS_forecasts.shtml",
        "fallback_img_url": "https://www.cpc.ncep.noaa.gov/products/JAWF_Monitoring/GFS/China_curr.p.gfs1b.gif",
        "out_path": ASSETS_DIR / "cpc_china_week1_anomaly.gif",
    },
}

MAUSAM_PAGE_URL = "https://mausam.imd.gov.in/responsive/monsooninformation.php"
MAUSAM_OUT = ASSETS_DIR / "imd_monsoon_sw.png"

STATIC_BROWSER_ASSETS = [
    "imd_rainfall_cumulative.png",
    "vci_brazil_sao_paulo_sugarcane.png",
    "vci_china_guangxi_sugarcane.png",
    "vci_thailand_nakhon_phanom_sugarcane.png",
]

warnings: list[str] = []


def warn(message: str) -> None:
    warnings.append(message)
    print(f"WARNING: {message}")


def http_get_bytes(url: str, headers: dict | None = None) -> bytes:
    request_headers = dict(HEADERS)
    if headers:
        request_headers.update(headers)

    last_error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.read()
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 + attempt * 2)

    raise last_error


def fetch_text(url: str, headers: dict | None = None) -> str:
    raw = http_get_bytes(url, headers=headers)
    return raw.decode("utf-8", errors="replace").replace("\ufeff", "").replace("−", "-").replace("\r", "\n")


def is_valid_value(value: float) -> bool:
    return -90 < value < 900


def latest_from_psl_standard(data_url: str, name: str) -> dict:
    text = fetch_text(data_url)
    tokens = text.replace("\n", " ").split()

    start_year = int(tokens[0])
    end_year = int(tokens[1])
    latest = None
    i = 2

    while i + 12 < len(tokens):
        if not re.fullmatch(r"\d{4}", tokens[i]):
            break

        year = int(tokens[i])
        if year < start_year or year > end_year:
            break

        for month in range(1, 13):
            value = float(tokens[i + month])
            if is_valid_value(value):
                latest = {
                    "name": name,
                    "time": f"{year}-{month:02d}",
                    "value": value,
                    "unit": "°C",
                }

        i += 13

    if latest is None:
        raise ValueError(f"{name} 没有找到有效数据：{data_url}")

    return latest


def extract_section_between(text: str, start_marker: str, end_marker: str | None = None) -> str:
    upper_text = text.upper()
    start_pos = upper_text.find(start_marker.upper())

    if start_pos == -1:
        raise ValueError(f"没有找到数据段：{start_marker}")

    if end_marker is None:
        return text[start_pos:]

    end_pos = upper_text.find(end_marker.upper(), start_pos)
    if end_pos == -1:
        return text[start_pos:]

    return text[start_pos:end_pos]


def latest_from_cpc_year_12_file(
    data_url: str,
    name: str,
    section_start: str | None = None,
    section_end: str | None = None,
    unit: str = "",
) -> dict:
    text = fetch_text(data_url)
    if section_start is not None:
        text = extract_section_between(text, section_start, section_end)

    value_pattern = r"[-+]?\d+(?:\.\d+)?"
    row_pattern = re.compile(
        r"(?<!\d)((?:18|19|20)\d{2})\s*"
        r"((?:" + value_pattern + r"\s*){12})"
    )

    latest = None
    for match in row_pattern.finditer(text):
        year = int(match.group(1))
        values = [float(x) for x in re.findall(value_pattern, match.group(2))]
        if len(values) != 12:
            continue

        for month, value in enumerate(values, start=1):
            if is_valid_value(value):
                latest = {
                    "name": name,
                    "time": f"{year}-{month:02d}",
                    "value": value,
                    "unit": unit,
                }

    if latest is None:
        raise ValueError(f"{name} 没有找到有效数据：{data_url}")

    return latest


def latest_heat_content(data_url: str, region_column: str) -> dict:
    column_map = {
        "130E-80W": 0,
        "160E-80W": 1,
        "180W-100W": 2,
    }
    if region_column not in column_map:
        raise ValueError(f"不支持的 HEATCENTRA 区域列：{region_column}")

    text = fetch_text(data_url)
    value_pattern = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
    row_pattern = re.compile(
        r"\b((?:19|20)\d{2})\s+"
        r"(\d{1,2})\s+"
        r"(" + value_pattern + r")\s+"
        r"(" + value_pattern + r")\s+"
        r"(" + value_pattern + r")"
    )

    latest = None
    region_index = column_map[region_column]
    for match in row_pattern.finditer(text):
        year = int(match.group(1))
        month = int(match.group(2))
        values = [
            float(match.group(3)),
            float(match.group(4)),
            float(match.group(5)),
        ]
        value = values[region_index]

        if 1 <= month <= 12 and is_valid_value(value):
            latest = {
                "name": f"HEATCENTRA 上层0-300m温度距平 ({region_column})",
                "time": f"{year}-{month:02d}",
                "value": value,
                "unit": "°C",
            }

    if latest is None:
        raise ValueError("没有找到有效的 HEATCENTRA 数据")

    return latest


def latest_iod_weekly() -> dict:
    try:
        text = fetch_text(IOD_URL, headers=BOM_HEADERS).strip()
        rows = re.findall(
            r"(\d{8})\s*,\s*(\d{8})\s*,\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))",
            text,
        )
        if not rows:
            raise ValueError("IOD 原始 txt 没有解析到数据")

        latest = None
        for _start_date, end_date, value_text in rows:
            value = float(value_text)
            if is_valid_value(value):
                latest = {
                    "name": "IOD weekly",
                    "time": datetime.strptime(end_date, "%Y%m%d").date().isoformat(),
                    "value": value,
                    "unit": "°C",
                }

        if latest is None:
            raise ValueError("IOD 原始 txt 没有有效值")

        return latest

    except Exception:
        html = fetch_text(IOD_SUMMARY_URL, headers=BOM_HEADERS)
        html = re.sub(r"\s+", " ", html)

        match = re.search(
            r"As of\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4}),\s+the IOD index is\s+"
            r"([+-]?\d+(?:\.\d+)?)\s*°C",
            html,
            flags=re.I,
        )
        if not match:
            raise ValueError("IOD 原始数据和 BoM summary 页面都没有解析到最新值")

        return {
            "name": "IOD weekly",
            "time": datetime.strptime(match.group(1), "%d %B %Y").date().isoformat(),
            "value": float(match.group(2)),
            "unit": "°C",
        }


def detect_weekly_nino34_column(lines: list[str]) -> int:
    patterns = [
        ("NINO1+2", r"NINO\s*1\s*\+\s*2|NINO12|NINO1\+2"),
        ("NINO3.4", r"NINO\s*3\s*\.?\s*4|NINO34"),
        ("NINO3", r"NINO\s*3(?!\s*\.?\s*4)"),
        ("NINO4", r"NINO\s*4(?!\d)"),
    ]

    for line in lines:
        upper = line.upper()
        if "NINO" not in upper:
            continue

        found = []
        for name, pattern in patterns:
            match = re.search(pattern, upper)
            if match:
                found.append((match.start(), name))

        names_in_order = [name for _pos, name in sorted(found)]
        if "NINO3.4" in names_in_order:
            return names_in_order.index("NINO3.4")

    return 3


def latest_weekly_nino34(data_url: str) -> dict:
    text = fetch_text(data_url)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    nino34_col = detect_weekly_nino34_column(lines)

    latest = None
    for line in lines:
        parts = line.split()
        if len(parts) < 5:
            continue

        try:
            date_value = datetime.strptime(parts[0].upper(), "%d%b%Y").date()
        except ValueError:
            continue

        value_index = 1 + nino34_col
        if len(parts) <= value_index:
            continue

        try:
            value = float(parts[value_index])
        except ValueError:
            continue

        if is_valid_value(value):
            latest = {
                "name": "Weekly Relative Niño 3.4 anomaly",
                "time": date_value.isoformat(),
                "value": value,
                "unit": "°C",
            }

    if latest is None:
        raise ValueError("没有解析到有效的 weekly Niño 3.4 数据")

    return latest


def metric_source(metric_name: str) -> str:
    name = metric_name.lower()
    if "weekly relative" in name:
        return WEEKLY_NINO34_URL
    if "niño 3.4 月度" in name or "nino 3.4 月度" in name:
        return NINO34_URL
    if "soi 海平面气压距平" in name:
        return SOI_URL
    if "equatorial soi" in name:
        return EQSOI_URL
    if "heatcentra" in name or "0-300m" in name:
        return HEATCENTRA_URL
    if "iod" in name:
        return IOD_URL
    return ""


def metric_period_type(metric_name: str) -> str:
    name = metric_name.lower()
    if "weekly" in name or "iod" in name:
        return "weekly"
    return "monthly"


def save_metrics(results: list[dict]) -> list[dict]:
    metric_results = []
    for idx, item in enumerate(results, start=1):
        metric_name = str(item.get("name", "")).strip()
        metric_results.append(
            {
                "order": idx,
                "name": metric_name,
                "time": str(item.get("time", "")).strip(),
                "period_type": metric_period_type(metric_name),
                "value": float(item["value"]) if item.get("value") is not None else None,
                "unit": str(item.get("unit", "")).strip(),
                "source": str(item.get("source", "") or metric_source(metric_name)),
            }
        )

    payload = {
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(metric_results),
        "metrics": metric_results,
    }

    METRICS_PAYLOAD_JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    METRICS_LIST_JSON_PATH.write_text(
        json.dumps(metric_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with METRICS_CSV_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["order", "name", "time", "period_type", "value", "unit", "source"],
        )
        writer.writeheader()
        writer.writerows(metric_results)

    return metric_results


def normalized_text(value: str) -> str:
    return str(value or "").lower().replace("niño", "nino").replace("–", "-")


def load_cached_metrics() -> list[dict]:
    paths = [
        METRICS_PAYLOAD_JSON_PATH,
        METRICS_LIST_JSON_PATH,
    ]

    for path in paths:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if isinstance(data, dict):
            metrics = data.get("metrics", [])
        elif isinstance(data, list):
            metrics = data
        else:
            continue

        clean = [item for item in metrics if isinstance(item, dict) and item.get("name")]
        if clean:
            return clean

    return []


def find_cached_metric(cached_metrics: list[dict], label: str) -> dict | None:
    label_norm = normalized_text(label)

    for item in cached_metrics:
        name_norm = normalized_text(item.get("name", ""))
        if label_norm == "heatcentra" and "heatcentra" in name_norm:
            return item
        if label_norm == name_norm or label_norm in name_norm:
            return item

    if "nino 3.4" in label_norm and "weekly" in label_norm:
        return find_metric(cached_metrics, ["weekly", "nino"])
    if "nino 3.4" in label_norm and "月度" in label_norm:
        return find_metric(cached_metrics, ["nino", "月度"])
    if "soi" in label_norm and "海平面" in label_norm:
        return find_metric(cached_metrics, ["soi", "海平面"])
    if "equatorial soi" in label_norm:
        return find_metric(cached_metrics, ["equatorial", "soi"])
    if "iod" in label_norm:
        return find_metric(cached_metrics, ["iod"])

    return None


def collect_metrics() -> list[dict]:
    cached_metrics = load_cached_metrics()
    jobs = [
        (
            "Niño 3.4 月度距平",
            lambda: latest_from_psl_standard(NINO34_URL, "Niño 3.4 月度距平"),
        ),
        (
            "SOI 海平面气压距平",
            lambda: latest_from_cpc_year_12_file(
                SOI_URL,
                "SOI 海平面气压距平",
                section_start="ANOMALY",
                section_end="STANDARDIZED",
            ),
        ),
        (
            "Equatorial SOI",
            lambda: latest_from_cpc_year_12_file(EQSOI_URL, "Equatorial SOI"),
        ),
        (
            "HEATCENTRA",
            lambda: latest_heat_content(HEATCENTRA_URL, HEATCENTRA_REGION),
        ),
        (
            "IOD weekly",
            latest_iod_weekly,
        ),
        (
            "Weekly Relative Niño 3.4 anomaly",
            lambda: latest_weekly_nino34(WEEKLY_NINO34_URL),
        ),
    ]

    results = []
    for label, getter in jobs:
        try:
            results.append(getter())
        except Exception as exc:
            cached = find_cached_metric(cached_metrics, label)
            if cached is None:
                warn(f"{label} 抓取失败且没有缓存，将在 HTML 中显示 N/A：{exc}")
                continue
            warn(f"{label} 抓取失败，使用缓存值 {cached.get('time')}：{exc}")
            results.append(cached)

    print("最新有效数据：")
    for item in results:
        unit = f" {item['unit']}" if item.get("unit") else ""
        try:
            value_text = f"{float(item['value']):+.2f}{unit}"
        except Exception:
            value_text = f"{item.get('value')}{unit}"
        print(f"{item['name']}：{item['time']}，值：{value_text}")

    return save_metrics(results)


def copy_seed_assets() -> None:
    # Keep existing runtime assets as cache, but do not read from user Desktop or local envs.
    return


def parse_attrs(attr_text: str) -> dict[str, str]:
    attrs = {}
    for match in re.finditer(
        r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""",
        attr_text,
    ):
        value = next(group for group in match.groups()[1:] if group is not None)
        attrs[match.group(1).lower()] = unescape(value)
    return attrs


def iter_img_attrs(html_text: str) -> list[dict[str, str]]:
    return [
        parse_attrs(match.group(1))
        for match in re.finditer(r"<\s*img\b([^>]*)>", html_text, flags=re.I | re.S)
    ]


def iter_links(html_text: str) -> list[tuple[str, str]]:
    links = []
    for match in re.finditer(r"<\s*a\b([^>]*)>(.*?)<\s*/\s*a\s*>", html_text, flags=re.I | re.S):
        attrs = parse_attrs(match.group(1))
        href = attrs.get("href", "")
        text = re.sub(r"<[^>]+>", " ", match.group(2))
        text = re.sub(r"\s+", " ", unescape(text)).strip()
        links.append((text, href))
    return links


def download_binary(url: str, out_path: Path, referer: str | None = None) -> Path:
    headers = dict(BROWSER_HEADERS)
    if referer:
        headers["Referer"] = referer

    content = http_get_bytes(url, headers=headers)

    valid_headers = (b"GIF87a", b"GIF89a", b"\x89PNG", b"\xff\xd8", b"<svg")
    if not content.startswith(valid_headers):
        raise ValueError(
            f"下载内容不像图片：{url}; 前20字节={content[:20]!r}"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(content)
    return out_path


def find_30day_anom_image_url(page_url: str, fallback_img_url: str) -> str:
    try:
        html_text = fetch_text(page_url, headers={**BROWSER_HEADERS, "Referer": page_url})

        for text, href in iter_links(html_text):
            text = text.lower()
            if "30-day" in text and "anom" in text and href:
                return urljoin(page_url, href)

        for attrs in iter_img_attrs(html_text):
            alt = attrs.get("alt", "").lower()
            src = attrs.get("src", "")
            if "30-day" in alt and "anomaly" in alt and src:
                return urljoin(page_url, src)

    except Exception as exc:
        print(f"解析 CPC 30天页面失败，使用兜底链接：{page_url}; {exc}")

    return fallback_img_url


def find_week1_anomaly_url(page_url: str, fallback_img_url: str) -> str:
    try:
        html_text = fetch_text(page_url, headers={**BROWSER_HEADERS, "Referer": page_url})

        for attrs in iter_img_attrs(html_text):
            alt = attrs.get("alt", "").lower()
            src = attrs.get("src", "")
            if "week 1" in alt and "anomaly" in alt and src:
                return urljoin(page_url, src)

        for text, href in iter_links(html_text):
            text = text.lower()
            if "week 1" in text and "anomaly" in text and href:
                return urljoin(page_url, href)

    except Exception as exc:
        print(f"解析 CPC Week 1 页面失败，使用兜底链接：{page_url}; {exc}")

    return fallback_img_url


def download_cpc_images() -> None:
    for item in CPC_30DAY_REGIONS.values():
        try:
            img_url = find_30day_anom_image_url(item["page_url"], item["fallback_img_url"])
            download_binary(img_url, item["out_path"], referer=item["page_url"])
            print(f"{item['name']} 下载成功：{item['out_path']}")
        except Exception as exc:
            warn(f"{item['name']} 下载失败，保留已有图片：{exc}")

    for key, item in CPC_WEEK1_PAGES.items():
        try:
            img_url = find_week1_anomaly_url(item["page_url"], item["fallback_img_url"])
            download_binary(img_url, item["out_path"], referer=item["page_url"])
            print(f"{key.upper()} Week 1 Anomaly 下载成功：{item['out_path']}")
        except Exception as exc:
            warn(f"{key.upper()} Week 1 Anomaly 下载失败，保留已有图片：{exc}")


def download_mausam_sw_monsoon() -> None:
    try:
        html_text = fetch_text(MAUSAM_PAGE_URL, headers=BROWSER_HEADERS)

        for attrs in iter_img_attrs(html_text):
            src = attrs.get("src", "")
            if "SW" in src.upper() or "MONSOON" in src.upper():
                url = urljoin(MAUSAM_PAGE_URL, src)
                download_binary(url, MAUSAM_OUT, referer=MAUSAM_PAGE_URL)
                print(f"Mausam SW Monsoon 图片下载成功：{MAUSAM_OUT}")
                return

        warn("Mausam 页面没有找到 SW Monsoon 图片，保留已有图片")
    except Exception as exc:
        warn(f"Mausam SW Monsoon 图片下载失败，保留已有图片：{exc}")


def run_browser_capture() -> None:
    node_bin = os.environ.get("EL_NINO_NODE") or shutil.which("node")
    if not node_bin:
        warn("没有找到 Node.js，跳过浏览器截图。")
        return
    if not BROWSER_CAPTURE_SCRIPT.exists():
        warn(f"浏览器截图脚本不存在，跳过：{BROWSER_CAPTURE_SCRIPT}")
        return

    try:
        completed = subprocess.run(
            [node_bin, str(BROWSER_CAPTURE_SCRIPT), str(ASSETS_DIR)],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired:
        warn("浏览器截图超时，HTML 将使用已有图片或占位图。")
        return
    except Exception as exc:
        warn(f"浏览器截图启动失败，HTML 将使用已有图片或占位图：{exc}")
        return

    if completed.stdout.strip():
        print(completed.stdout.strip())
    if completed.stderr.strip():
        for line in completed.stderr.strip().splitlines():
            if line.startswith("WARNING:"):
                warn(line.replace("WARNING:", "", 1).strip())
            else:
                print(line)
    if completed.returncode != 0:
        warn(f"浏览器截图脚本退出码 {completed.returncode}，HTML 将使用已有图片或占位图。")


def note_browser_assets() -> None:
    missing = [name for name in STATIC_BROWSER_ASSETS if not (ASSETS_DIR / name).exists()]
    if missing:
        warn("以下浏览器截图资产缺失，将在 HTML 中显示占位图：" + ", ".join(missing))


def image_file_to_data_uri(path: Path | None, title: str, subtitle: str) -> str:
    if not path or not path.exists():
        return make_placeholder_svg(title, subtitle)

    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        mime_type = "image/gif" if path.suffix.lower() == ".gif" else "image/png"

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def make_placeholder_svg(title: str, subtitle: str) -> str:
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="1200" height="760" viewBox="0 0 1200 760">
      <rect width="1200" height="760" rx="28" fill="#F3FBFF"/>
      <rect x="70" y="70" width="1060" height="620" rx="24" fill="#FFFFFF" stroke="#D7EEF8" stroke-width="4"/>
      <text x="110" y="170" font-family="Arial, Microsoft YaHei, sans-serif" font-size="42" font-weight="700" fill="#197EA8">{escape(title)}</text>
      <text x="110" y="235" font-family="Arial, Microsoft YaHei, sans-serif" font-size="24" fill="#64899C">{escape(subtitle)}</text>
      <line x1="110" y1="330" x2="1090" y2="330" stroke="#D7EEF8" stroke-width="4"/>
      <line x1="110" y1="445" x2="1090" y2="445" stroke="#E7F8FF" stroke-width="3"/>
      <line x1="110" y1="560" x2="1090" y2="560" stroke="#E7F8FF" stroke-width="3"/>
      <polyline points="130,585 260,500 390,530 520,420 650,455 780,350 910,390 1080,280"
                fill="none" stroke="#21A7D8" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
      <text x="110" y="650" font-family="Arial, Microsoft YaHei, sans-serif" font-size="24" fill="#8AA9B8">暂无可用图片</text>
    </svg>
    """
    return "data:image/svg+xml;charset=utf-8," + quote(" ".join(svg.split()))


def file_mtime(path: Path | None) -> str:
    if not path or not path.exists():
        return "未找到文件"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def format_value(metric: dict | None) -> str:
    if metric is None or metric.get("value") is None:
        return "N/A"

    value = metric.get("value")
    unit = str(metric.get("unit", "") or "").strip()

    try:
        value_text = f"{float(value):+.2f}"
    except Exception:
        value_text = str(value)

    return f"{value_text} {unit}".strip()


def format_time_zh(time_text: str | None) -> str:
    time_text = str(time_text or "").strip()
    if not time_text:
        return "未标注"

    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            dt = datetime.strptime(time_text, fmt)
        except ValueError:
            continue
        if fmt == "%Y-%m-%d":
            return f"{dt.year}年{dt.month}月{dt.day}日"
        return f"{dt.year}年{dt.month}月"

    return time_text


def find_metric(metrics: list[dict], keywords: list[str]) -> dict | None:
    keywords = [k.lower() for k in keywords]
    for item in metrics:
        name = str(item.get("name", "")).lower()
        if all(k in name for k in keywords):
            return item
    return None


def metric_cards_data(metrics: list[dict]) -> list[dict]:
    return [
        {
            "title": "Niño 3.4 周度",
            "metric": find_metric(metrics, ["weekly", "nino"])
            or find_metric(metrics, ["weekly", "niño"]),
            "date_label": "数据时间",
            "note": "",
            "explanation": "衡量Niño 3.4海区周度海温距平。正值偏向厄尔尼诺，负值偏向拉尼娜。周度数据反映快，但不确定性较大，需结合持续性判断。",
        },
        {
            "title": "SOI 30天",
            "metric": find_metric(metrics, ["soi", "海平面"]) or find_metric(metrics, ["soi"]),
            "date_label": "数据时间",
            "note": "",
            "explanation": "衡量海平面气压差。正值通常偏拉尼娜，负值通常偏向厄尔尼诺；与Niño 3.4 海温指标方向相反。",
        },
        {
            "title": "赤道太平洋 0-300m 次表层水温",
            "metric": find_metric(metrics, ["heatcentra"]) or find_metric(metrics, ["0-300m"]),
            "date_label": "数据时间",
            "note": "区域：160E-80W",
            "explanation": "衡量赤道太平洋0-300m上层海洋温度距平。正值表示次表层暖水储备偏多，支持后续偏暖；负值表示冷水储备偏多，支持后续偏冷。",
        },
        {
            "title": "Niño 3.4 月度",
            "metric": find_metric(metrics, ["niño", "月度"]) or find_metric(metrics, ["nino", "月度"]),
            "date_label": "数据月份",
            "note": "",
            "explanation": "衡量Niño 3.4 海区月度海温距平。正值偏向厄尔尼诺，负值偏向拉尼娜。相比周度数据更平滑，更适合观察趋势。",
        },
        {
            "title": "赤道 SOI",
            "metric": find_metric(metrics, ["equatorial", "soi"]) or find_metric(metrics, ["赤道", "soi"]),
            "date_label": "数据月份",
            "note": "",
            "explanation": "衡量东太平洋与印尼附近赤道气压差。正值偏向拉尼娜，负值偏向厄尔尼诺；对比大气是否和海温信号相符。",
        },
        {
            "title": "IOD",
            "metric": find_metric(metrics, ["iod"]),
            "date_label": "数据时间",
            "note": "",
            "explanation": "衡量印度洋东西部海温差。正值表示西印度洋偏暖，东印度洋偏冷；负值表示东印度洋偏暖，西印度洋偏冷。",
        },
    ]


def country_weather() -> list[dict]:
    return [
        {
            "country": "印度",
            "summary": "关注季风推进、累积降雨距平差和未来一周降雨距平差。",
            "images": [
                ("季风推进", "时间段：季风监测，具体日期以图中标注为准", ASSETS_DIR / "imd_monsoon_sw.png"),
                ("累积降雨距平差", "时间段：累积降雨，具体起止日期以图中标注为准", ASSETS_DIR / "imd_rainfall_cumulative.png"),
                ("未来一周降雨距平差", "时间段：未来一周预报，具体有效期以图中标注为准", ASSETS_DIR / "cpc_india_week1_anomaly.gif"),
            ],
        },
        {
            "country": "泰国",
            "summary": "以东南亚区域图作为泰国及周边产区参考。",
            "images": [
                ("过去30天降雨距平差", "时间段：过去30天，具体日期以图中标注为准", ASSETS_DIR / "cpc_seasia_30day_anom.gif"),
                ("未来一周降水距平差", "时间段：未来一周预报，具体有效期以图中标注为准", ASSETS_DIR / "cpc_seasia_week1_anomaly.gif"),
                ("VCI植被状况指数", "时间段：如图所示，最近一个工作日", ASSETS_DIR / "vci_thailand_nakhon_phanom_sugarcane.png"),
            ],
        },
        {
            "country": "巴西",
            "summary": "关注过去30天降雨距平差、未来一周降水距平差和植被状况。",
            "images": [
                ("过去30天降雨距平差", "时间段：过去30天，具体日期以图中标注为准", ASSETS_DIR / "cpc_brazil_30day_anom.gif"),
                ("未来一周降水距平差", "时间段：未来一周预报，具体有效期以图中标注为准", ASSETS_DIR / "cpc_brazil_week1_anomaly.gif"),
                ("VCI植被状况指数", "时间段：如图所示，最近一个工作日", ASSETS_DIR / "vci_brazil_sao_paulo_sugarcane.png"),
            ],
        },
        {
            "country": "中国",
            "summary": "关注过去30天降雨距平差、未来一周降水距平差和植被状况。",
            "images": [
                ("过去30天降雨距平差", "时间段：过去30天，具体日期以图中标注为准", ASSETS_DIR / "cpc_china_30day_anom.gif"),
                ("未来一周降水距平差", "时间段：未来一周预报，具体有效期以图中标注为准", ASSETS_DIR / "cpc_china_week1_anomaly.gif"),
                ("VCI植被状况指数", "时间段：如图所示，最近一个工作日", ASSETS_DIR / "vci_china_guangxi_sugarcane.png"),
            ],
        },
    ]


STYLE = """
:root {
  --page-bg: #F3FBFF;
  --card-bg: #FFFFFF;
  --primary: #197EA8;
  --accent: #21A7D8;
  --text: #183B56;
  --muted: #64899C;
  --border: #D7EEF8;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--text);
  background: linear-gradient(180deg, #FFFFFF 0%, var(--page-bg) 42%, #EAF8FF 100%);
  font-family: Arial, "Microsoft YaHei", "PingFang SC", sans-serif;
}
.page { width: min(1480px, calc(100% - 48px)); margin: 0 auto; padding: 28px 0 56px; }
.hero {
  display: flex; justify-content: space-between; gap: 24px; align-items: center;
  min-height: 136px; padding: 28px 32px; border: 1px solid var(--border);
  border-radius: 24px; background: rgba(255,255,255,.9); box-shadow: 0 18px 44px rgba(18,115,156,.10);
}
h1 { margin: 0; color: var(--primary); font-size: clamp(30px, 3vw, 46px); line-height: 1.08; }
.subtitle { margin: 10px 0 0; color: var(--muted); font-size: 15px; }
.hero-meta { display: grid; gap: 7px; text-align: right; color: var(--muted); font-size: 13px; }
.pill { justify-self: end; padding: 8px 12px; border-radius: 999px; background: #E7F8FF; color: var(--primary); font-weight: 700; }
.section-title { display: flex; align-items: center; gap: 10px; margin: 32px 0 16px; }
.section-title h2 { margin: 0; font-size: 23px; }
.rule { height: 1px; flex: 1; background: linear-gradient(90deg, var(--border), rgba(215,238,248,0)); }
.metrics-grid, .weather-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.metric-card, .country-section, .weather-card, .footer {
  background: rgba(255,255,255,.94); border: 1px solid var(--border); box-shadow: 0 12px 28px rgba(18,115,156,.08);
}
.metric-card { min-height: 154px; padding: 22px 20px; border-radius: 16px; text-align: center; border-top: 5px solid var(--accent); }
.metric-name { min-height: 38px; display: grid; place-items: center; color: var(--muted); font-weight: 800; font-size: 16px; }
.metric-value { margin: 8px 0 12px; color: var(--primary); font-size: clamp(31px, 3vw, 44px); line-height: 1; font-weight: 850; }
.metric-date { color: #7EA2B3; font-size: 13px; line-height: 1.45; }
.metric-note { margin-top: 6px; color: #2E8DB4; font-size: 12px; font-weight: 700; }
.metric-explanation { margin-top: 12px; color: #4F7081; font-size: 12px; line-height: 1.65; text-align: left; }
.country-section { margin-top: 22px; padding: 20px; border-radius: 18px; }
.country-header { display: flex; justify-content: space-between; gap: 20px; margin-bottom: 16px; }
.country-header h3 { margin: 0 0 6px; color: var(--primary); font-size: 24px; }
.country-header p { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.6; }
.country-badge { align-self: flex-start; padding: 7px 11px; border-radius: 999px; background: #E7F8FF; color: var(--primary); font-size: 13px; font-weight: 700; }
.weather-card { margin: 0; overflow: hidden; border-radius: 14px; }
.weather-image-wrap { padding: 11px 11px 0; background: linear-gradient(180deg, #FFFFFF, #F4FCFF); }
.weather-card img { display: block; width: 100%; aspect-ratio: 16 / 10; object-fit: contain; border: 1px solid var(--border); border-radius: 10px; background: #FFFFFF; }
figcaption { padding: 12px 14px 15px; }
.image-title { margin-bottom: 6px; color: var(--primary); font-weight: 800; font-size: 15px; line-height: 1.45; }
.image-period { margin-bottom: 6px; color: #2E8DB4; font-size: 12px; font-weight: 700; line-height: 1.55; }
.image-date { color: #8AA9B8; font-size: 11px; line-height: 1.45; }
.footer { margin-top: 28px; padding: 16px 20px; border-radius: 14px; color: var(--muted); font-size: 13px; line-height: 1.7; }
@media (max-width: 1120px) { .metrics-grid, .weather-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) {
  .page { width: min(100% - 28px, 1480px); padding-top: 18px; }
  .hero, .country-header { flex-direction: column; align-items: flex-start; }
  .hero-meta { text-align: left; }
  .pill { justify-self: start; }
  .metrics-grid, .weather-grid { grid-template-columns: 1fr; }
  .country-section { padding: 15px; }
}
"""


def metric_card(item: dict) -> str:
    metric = item["metric"]
    if metric is None:
        value_text = "N/A"
        date_text = "数据时间：未找到"
    else:
        value_text = format_value(metric)
        date_text = f"{item['date_label']}：{format_time_zh(metric.get('time'))}"

    note_html = f'<div class="metric-note">{escape(item["note"])}</div>' if item.get("note") else ""
    explanation_html = (
        f'<div class="metric-explanation">{escape(item["explanation"])}</div>'
        if item.get("explanation")
        else ""
    )
    return f"""
    <article class="metric-card">
      <div class="metric-name">{escape(item["title"])}</div>
      <div class="metric-value">{escape(value_text)}</div>
      <div class="metric-date">{escape(date_text)}</div>
      {note_html}
      {explanation_html}
    </article>
    """


def image_card(title: str, period: str, path: Path) -> str:
    img_src = image_file_to_data_uri(path if path.exists() else None, title, period)
    image_date = f"本地图片更新时间：{file_mtime(path)}" if path.exists() else "图片日期：占位图"
    return f"""
    <figure class="weather-card">
      <div class="weather-image-wrap">
        <img src="{img_src}" alt="{escape(title)}" loading="lazy" />
      </div>
      <figcaption>
        <div class="image-title">{escape(title)}</div>
        <div class="image-period">{escape(period)}</div>
        <div class="image-date">{escape(image_date)}</div>
      </figcaption>
    </figure>
    """


def country_section(section: dict) -> str:
    cards = "\n".join(image_card(title, period, path) for title, period, path in section["images"])
    return f"""
    <section class="country-section">
      <div class="country-header">
        <div>
          <h3>{escape(section["country"])}</h3>
          <p>{escape(section["summary"])}</p>
        </div>
        <span class="country-badge">3 张图</span>
      </div>
      <div class="weather-grid">
        {cards}
      </div>
    </section>
    """


def build_html(metrics: list[dict]) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    metrics_saved_at = datetime.fromtimestamp(METRICS_PAYLOAD_JSON_PATH.stat().st_mtime).strftime("%Y-%m-%d %H:%M")

    metric_cards = "\n".join(metric_card(item) for item in metric_cards_data(metrics))
    country_sections = "\n".join(country_section(section) for section in country_weather())

    warning_html = ""
    if warnings:
        warning_items = "".join(f"<li>{escape(item)}</li>" for item in warnings)
        warning_html = f"""
        <div class="footer">
          <b>运行提示：</b>
          <ul>{warning_items}</ul>
        </div>
        """

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>厄尔尼诺指标跟踪</title>
  <style>{STYLE}</style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <div>
        <h1>厄尔尼诺指标跟踪</h1>
        <p class="subtitle">海气指标与主产区天气监测看板</p>
      </div>
      <div class="hero-meta">
        <span class="pill">单文件 HTML</span>
        <span>页面生成时间：{escape(generated_at)}</span>
        <span>指标保存时间：{escape(metrics_saved_at)}</span>
      </div>
    </header>

    <div class="section-title">
      <h2>核心海气指标</h2>
      <span class="rule"></span>
    </div>

    <section class="metrics-grid">
      {metric_cards}
    </section>

    <div class="section-title">
      <h2>主产区天气图</h2>
      <span class="rule"></span>
    </div>

    {country_sections}

    {warning_html}

    <div class="footer">
      说明：图片的具体统计日期和预报有效期以图中标注为准。
    </div>
  </main>
</body>
</html>
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    copy_seed_assets()
    metrics = collect_metrics()
    download_cpc_images()
    download_mausam_sw_monsoon()
    run_browser_capture()
    note_browser_assets()

    html = build_html(metrics)
    OUTPUT_HTML.write_text(html, encoding="utf-8")

    print(f"HTML 已生成：{OUTPUT_HTML}")
    print(f"运行资产目录：{ASSETS_DIR}")
    if warnings:
        print("运行提示：")
        for item in warnings:
            print(f"- {item}")


if __name__ == "__main__":
    main()
