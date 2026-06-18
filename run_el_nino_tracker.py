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
from zoneinfo import ZoneInfo


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
BEIJING_TZ = ZoneInfo("Asia/Shanghai")

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
NINO34_FORECAST_IMAGE_URL = "https://www.cpc.ncep.noaa.gov/products/CFSv2/imagesInd3/nino34Mon.gif"
ENSO_STRENGTH_PAGE_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/strengths/"
NINO34_FORECAST_OUT = ASSETS_DIR / "nino34Mon.gif"
ENSO_STRENGTH_PROB_OUT = ASSETS_DIR / "noaa_cpc_enso_strength_probabilities.png"
ENSO_STRENGTH_PROB_JSON = ASSETS_DIR / "enso_strength_probabilities_latest.json"

ENSO_STRENGTH_PROB_COLUMNS = [
    "la_nina_very_strong",
    "la_nina_strong",
    "la_nina_moderate",
    "la_nina_weak",
    "neutral",
    "el_nino_weak",
    "el_nino_moderate",
    "el_nino_strong",
    "el_nino_very_strong",
]
ENSO_EL_NINO_PROB_COLUMNS = [
    "el_nino_weak",
    "el_nino_moderate",
    "el_nino_strong",
    "el_nino_very_strong",
]
ENSO_LA_NINA_PROB_COLUMNS = [
    "la_nina_weak",
    "la_nina_moderate",
    "la_nina_strong",
    "la_nina_very_strong",
]
ENSO_STRENGTH_PROB_LABELS = {
    "la_nina_very_strong": "超强拉尼娜",
    "la_nina_strong": "强拉尼娜",
    "la_nina_moderate": "中等拉尼娜",
    "la_nina_weak": "弱拉尼娜",
    "neutral": "中性",
    "el_nino_weak": "弱厄尔尼诺",
    "el_nino_moderate": "中等厄尔尼诺",
    "el_nino_strong": "强厄尔尼诺",
    "el_nino_very_strong": "超强厄尔尼诺",
}
ENSO_EL_NINO_SHORT_LABELS = {
    "el_nino_weak": "弱",
    "el_nino_moderate": "中等",
    "el_nino_strong": "强",
    "el_nino_very_strong": "超强",
}
SEASON_LETTER_BY_MONTH = {
    1: "J",
    2: "F",
    3: "M",
    4: "A",
    5: "M",
    6: "J",
    7: "J",
    8: "A",
    9: "S",
    10: "O",
    11: "N",
    12: "D",
}

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

IMD_RAINFALL_PAGE_URL = "https://mausam.imd.gov.in/responsive/rainfallinformation.php?msg=C"
IMD_RAINFALL_LEGEND_URL = "https://mausam.imd.gov.in/responsive/img/img-in/legendsRFPer.svg"
IMD_RAINFALL_LEGEND_OUT = ASSETS_DIR / "imd_rainfall_legend.svg"
MAUSAM_PAGE_URL = "https://mausam.imd.gov.in/responsive/monsooninformation.php"
MAUSAM_OUT = ASSETS_DIR / "imd_monsoon_sw.png"

STATIC_BROWSER_ASSETS = [
    "imd_rainfall_cumulative.png",
    "vci_brazil_sao_paulo_sugarcane.png",
    "vci_china_guangxi_sugarcane.png",
    "vci_thailand_nakhon_phanom_sugarcane.png",
]

warnings: list[str] = []
enso_strength_probabilities_cache: dict | None = None


def now_beijing() -> datetime:
    return datetime.now(BEIJING_TZ)


def format_timestamp_beijing(timestamp: float, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return datetime.fromtimestamp(timestamp, BEIJING_TZ).strftime(fmt)


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
        "saved_at": now_beijing().strftime("%Y-%m-%d %H:%M:%S"),
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


def download_imd_rainfall_legend() -> None:
    try:
        svg_content = http_get_bytes(
            IMD_RAINFALL_LEGEND_URL,
            headers={**BROWSER_HEADERS, "Referer": IMD_RAINFALL_PAGE_URL},
        )
        if b"<svg" not in svg_content[:2048].lower():
            raise ValueError("IMD 图例地址没有返回有效 SVG 文件")

        IMD_RAINFALL_LEGEND_OUT.parent.mkdir(parents=True, exist_ok=True)
        IMD_RAINFALL_LEGEND_OUT.write_bytes(svg_content)
        print(f"IMD Rainfall 图例下载成功：{IMD_RAINFALL_LEGEND_OUT}")
    except Exception as exc:
        warn(f"IMD Rainfall 图例下载失败，保留已有图例：{exc}")


def find_enso_strength_probabilities_url(page_url: str, html_text: str | None = None) -> str:
    if html_text is None:
        html_text = fetch_text(page_url, headers={**BROWSER_HEADERS, "Referer": page_url})

    for attrs in iter_img_attrs(html_text):
        src = attrs.get("src") or attrs.get("data-src") or attrs.get("data-lazy-src")
        if not src:
            continue
        full_url = urljoin(page_url, src)
        if "enso-strengths-probs-current" in full_url:
            return full_url

    raise ValueError("没有找到 ENSO Strength Probabilities 主图")


def clean_html_text(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = unescape(text).replace("−", "-")
    return re.sub(r"\s+", " ", text).strip()


def parse_enso_strength_probabilities(html_text: str) -> dict:
    html_text = re.sub(r"<!--.*?-->", "", html_text, flags=re.S)
    issued_match = re.search(
        r"<h2[^>]*>\s*Issued\s+([^<]+?)\s*</h2>",
        html_text,
        flags=re.I | re.S,
    )
    issued = re.sub(r"\s+", " ", issued_match.group(1)).strip() if issued_match else "未标注"

    table_match = re.search(
        r"<table\b[^>]*id=[\"']probabilities-table[\"'][^>]*>(.*?)</table>",
        html_text,
        flags=re.I | re.S,
    )
    if table_match is None:
        raise ValueError("NOAA CPC 页面没有找到 ENSO 强度概率表")

    rows = []
    for row_match in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", table_match.group(1), flags=re.I | re.S):
        cells = re.findall(
            r"<t[dh]\b[^>]*>(.*?)</t[dh]>",
            row_match.group(1),
            flags=re.I | re.S,
        )
        if len(cells) != 10:
            continue

        season_text = clean_html_text(cells[0])
        season_match = re.match(r"([A-Z]{3})\b(.*)", season_text)
        if not season_match:
            continue

        values = []
        for cell in cells[1:]:
            value_match = re.search(r"-?\d+", clean_html_text(cell))
            if value_match is None:
                raise ValueError(f"ENSO 强度概率表存在无法解析的单元格：{cell!r}")
            values.append(int(value_match.group(0)))

        season = season_match.group(1)
        season_name = re.sub(r"\s+", "-", season_match.group(2).strip())
        row = {
            "season": season,
            "season_name": season_name,
        }
        row.update(dict(zip(ENSO_STRENGTH_PROB_COLUMNS, values)))
        rows.append(row)

    if not rows:
        raise ValueError("NOAA CPC ENSO 强度概率表没有解析到有效季节数据")

    return {
        "source_url": ENSO_STRENGTH_PAGE_URL,
        "issued": issued,
        "rows": rows,
        "fetched_at": now_beijing().strftime("%Y-%m-%d %H:%M"),
    }


def store_enso_strength_probabilities(payload: dict) -> dict:
    global enso_strength_probabilities_cache
    enso_strength_probabilities_cache = payload
    ENSO_STRENGTH_PROB_JSON.parent.mkdir(parents=True, exist_ok=True)
    ENSO_STRENGTH_PROB_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def load_cached_enso_strength_probabilities() -> dict | None:
    if not ENSO_STRENGTH_PROB_JSON.exists():
        return None
    try:
        payload = json.loads(ENSO_STRENGTH_PROB_JSON.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not payload.get("rows"):
        return None
    return payload


def latest_enso_strength_probabilities() -> dict | None:
    global enso_strength_probabilities_cache
    if enso_strength_probabilities_cache is not None:
        return enso_strength_probabilities_cache

    try:
        html_text = fetch_text(
            ENSO_STRENGTH_PAGE_URL,
            headers={**BROWSER_HEADERS, "Referer": ENSO_STRENGTH_PAGE_URL},
        )
        return store_enso_strength_probabilities(parse_enso_strength_probabilities(html_text))
    except Exception as exc:
        cached = load_cached_enso_strength_probabilities()
        if cached is not None:
            enso_strength_probabilities_cache = cached
            warn(f"NOAA CPC ENSO 强度概率表抓取失败，使用缓存结论：{exc}")
            return cached
        warn(f"NOAA CPC ENSO 强度概率表抓取失败，预测结论暂不显示：{exc}")
        return None


def probability_value(row: dict, key: str) -> int:
    try:
        return int(row.get(key, 0))
    except (TypeError, ValueError):
        return 0


def probability_sum(row: dict, keys: list[str]) -> int:
    return sum(probability_value(row, key) for key in keys)


def el_nino_strength_score(row: dict) -> int:
    return (
        probability_value(row, "el_nino_weak")
        + probability_value(row, "el_nino_moderate") * 2
        + probability_value(row, "el_nino_strong") * 3
        + probability_value(row, "el_nino_very_strong") * 4
    )


def dominant_probability(row: dict, keys: list[str]) -> tuple[str, int]:
    return max(
        ((key, probability_value(row, key)) for key in keys),
        key=lambda item: (item[1], keys.index(item[0])),
    )


def season_display(row: dict) -> str:
    season = str(row.get("season", "")).strip()
    season_name = str(row.get("season_name", "")).strip()
    if season_name:
        return f"{season}（{season_name}）"
    return season


def month_after(start_month: int, offset: int) -> int:
    return ((start_month - 1 + offset) % 12) + 1


def season_code_from_start_month(start_month: int) -> str:
    months = [month_after(start_month, offset) for offset in range(3)]
    return "".join(SEASON_LETTER_BY_MONTH[month] for month in months)


def season_start_month_from_code(season_code: str) -> int | None:
    season_code = str(season_code or "").upper()
    for month in range(1, 13):
        if season_code_from_start_month(month) == season_code:
            return month
    return None


def month_range_text(start_month: int) -> str:
    return f"{start_month}-{month_after(start_month, 2)}月"


def season_month_range_display(row: dict) -> str:
    start_month = season_start_month_from_code(str(row.get("season", "")))
    if start_month is None:
        return season_display(row)
    return month_range_text(start_month)


def centered_season_code(current: datetime) -> str:
    months = [
        ((current.month - 2) % 12) + 1,
        current.month,
        (current.month % 12) + 1,
    ]
    return "".join(SEASON_LETTER_BY_MONTH[month] for month in months)


def find_season_row(rows: list[dict], season_code: str) -> dict | None:
    for row in rows:
        if str(row.get("season", "")).upper() == season_code.upper():
            return row
    return None


def el_nino_probabilities_text(row: dict) -> str:
    parts = []
    for key in ENSO_EL_NINO_PROB_COLUMNS:
        value = probability_value(row, key)
        if value:
            parts.append(f"{ENSO_EL_NINO_SHORT_LABELS[key]} {value}%")
    if not parts:
        return "厄尔尼诺概率为 0%"
    return "，".join(parts)


def el_nino_probability_details(row: dict) -> list[tuple[str, int]]:
    return [
        ("中性", probability_value(row, "neutral")),
        ("弱", probability_value(row, "el_nino_weak")),
        ("中等", probability_value(row, "el_nino_moderate")),
        ("强", probability_value(row, "el_nino_strong")),
        ("超强", probability_value(row, "el_nino_very_strong")),
    ]


def el_nino_strength_floor(row: dict) -> str:
    strong_plus = probability_sum(row, ["el_nino_strong", "el_nino_very_strong"])
    moderate_plus = probability_sum(
        row,
        ["el_nino_moderate", "el_nino_strong", "el_nino_very_strong"],
    )
    total = probability_sum(row, ENSO_EL_NINO_PROB_COLUMNS)
    neutral_weak = probability_sum(row, ["neutral", "el_nino_weak"])

    if strong_plus >= 45:
        return "强以上"
    if moderate_plus >= 45:
        return "中等以上"
    if total >= 45:
        return "弱以上"
    if neutral_weak >= 45:
        return "中性至弱"
    if probability_value(row, "neutral") >= 45:
        return "中性"
    return "厄尔尼诺信号不足"


def forecast_display_rows(rows: list[dict], current: datetime) -> list[dict]:
    rows_by_code = {
        str(row.get("season", "")).upper(): row
        for row in rows
    }
    selected: list[dict] = []
    selected_codes: set[str] = set()
    for offset in (0, 2, 4, 6):
        code = season_code_from_start_month(month_after(current.month, offset))
        row = rows_by_code.get(code)
        if row is not None and code not in selected_codes:
            selected.append(row)
            selected_codes.add(code)

    for row in rows:
        code = str(row.get("season", "")).upper()
        if len(selected) >= 4:
            break
        if code not in selected_codes:
            selected.append(row)
            selected_codes.add(code)
    return selected


def forecast_segment_data(row: dict) -> dict:
    strong_plus = probability_sum(row, ["el_nino_strong", "el_nino_very_strong"])
    total = probability_sum(row, ENSO_EL_NINO_PROB_COLUMNS)
    dominant_key, dominant_value = dominant_probability(row, ENSO_EL_NINO_PROB_COLUMNS)
    return {
        "period": season_month_range_display(row),
        "level": el_nino_strength_floor(row),
        "dominant": ENSO_STRENGTH_PROB_LABELS[dominant_key],
        "dominant_value": dominant_value,
        "strong_plus": strong_plus,
        "total": total,
        "probabilities": el_nino_probability_details(row),
    }


def first_el_nino_start_row(rows: list[dict]) -> dict | None:
    for row in rows:
        if probability_sum(row, ENSO_EL_NINO_PROB_COLUMNS) >= 45:
            return row
    return None


def forecast_market_bias(peak_row: dict) -> tuple[str, str]:
    el_total = probability_sum(peak_row, ENSO_EL_NINO_PROB_COLUMNS)
    la_total = probability_sum(peak_row, ENSO_LA_NINA_PROB_COLUMNS)
    strong_plus = probability_sum(peak_row, ["el_nino_strong", "el_nino_very_strong"])
    moderate_plus = probability_sum(
        peak_row,
        ["el_nino_moderate", "el_nino_strong", "el_nino_very_strong"],
    )

    if el_total >= 45 and el_total >= la_total:
        if strong_plus >= 45:
            return (
                "偏利多糖价",
                "亚洲甘蔗产区偏干和单产下修风险上升，容易抬升糖价天气风险溢价。",
            )
        if moderate_plus >= 45 or el_total >= 70:
            return (
                "中性偏利多糖价",
                "厄尔尼诺风险占优，但还需要印度、泰国实际降雨继续验证。",
            )
        return (
            "轻微利多糖价，仍需观察",
            "厄尔尼诺信号存在，但天气风险溢价仍需要主产区降雨配合。",
        )

    if la_total >= 45 and la_total > el_total:
        return (
            "偏利空糖价",
            "拉尼娜概率占优时，亚洲季风水分条件改善的概率上升，可能压低糖价天气风险溢价。",
        )

    return (
        "中性观望",
        "ENSO 强度概率暂未形成明确方向，糖价更需要看主产区实际降雨和供应节奏。",
    )


def build_enso_strength_market_view(
    peak_row: dict,
    peak_key: str,
    peak_total: int,
    peak_strong_plus: int,
    decline_row: dict | None,
) -> dict:
    peak_season = season_display(peak_row)
    dominant_label = ENSO_STRENGTH_PROB_LABELS.get(peak_key, "厄尔尼诺")

    if decline_row is None:
        trend_note = "表内尚未出现明确回落，说明 NOAA 当前预测窗口内天气风险溢价不宜过早下修。"
    else:
        decline_season = season_display(decline_row["row"])
        trend_note = f"{decline_season}开始回落后，需要观察厄尔尼诺利多是否边际降温。"

    if peak_total < 50:
        return {
            "conclusion": (
                f"{peak_season}虽是表内厄尔尼诺评分最高季度，但总厄尔尼诺概率仅 {peak_total}%，"
                "暂未形成明确主导信号。"
            ),
            "focus": "印度、泰国和巴西的实际降雨、土壤水分、压榨进度，而不是单独依赖 ENSO 预测。",
            "sugar_impact": "糖价影响偏中性观望；ENSO 对糖价的天气风险溢价暂不构成强驱动。",
        }

    if peak_strong_plus >= 50:
        return {
            "conclusion": (
                f"{peak_season}厄尔尼诺强度风险较高，强及以上概率 {peak_strong_plus}%，"
                f"主导分档为{dominant_label}。"
            ),
            "focus": (
                "印度、泰国季风降雨是否偏弱、甘蔗产区土壤水分和单产预期；"
                f"同时跟踪巴西中南部降雨对压榨节奏的扰动。{trend_note}"
            ),
            "sugar_impact": (
                "偏利多糖价；逻辑是亚洲甘蔗产区偏干和单产下修风险上升，"
                "容易抬升糖价天气风险溢价。"
            ),
        }

    if peak_total >= 70:
        return {
            "conclusion": (
                f"{peak_season}厄尔尼诺概率占优，总厄尔尼诺概率 {peak_total}%，"
                f"但强及以上概率为 {peak_strong_plus}%，强度还不是最极端情形。"
            ),
            "focus": (
                "弱/中等厄尔尼诺是否继续升级，以及印度、泰国季风降雨是否出现连续偏少。"
                f"{trend_note}"
            ),
            "sugar_impact": "中性偏利多糖价；天气风险溢价存在，但需要产区实际降雨验证。",
        }

    return {
        "conclusion": (
            f"{peak_season}存在厄尔尼诺倾向，总厄尔尼诺概率 {peak_total}%，"
            f"主导分档为{dominant_label}。"
        ),
        "focus": (
            "厄尔尼诺概率是否继续抬升到中等及以上，同时观察印度、泰国降雨是否低于常年。"
            f"{trend_note}"
        ),
        "sugar_impact": "轻微利多糖价，仍需观察；如果后续概率升级或主产区降雨转差，利多会增强。",
    }


def analyze_enso_strength_forecast(payload: dict, current: datetime | None = None) -> dict:
    rows = list(payload.get("rows") or [])
    if not rows:
        raise ValueError("ENSO 强度概率数据为空")

    current = current or now_beijing()
    display_segments = [
        forecast_segment_data(row)
        for row in forecast_display_rows(rows, current)
    ]

    peak_index = max(
        range(len(rows)),
        key=lambda index: (
            el_nino_strength_score(rows[index]),
            probability_sum(rows[index], ["el_nino_strong", "el_nino_very_strong"]),
            probability_sum(rows[index], ENSO_EL_NINO_PROB_COLUMNS),
            index,
        ),
    )
    peak_row = rows[peak_index]
    peak_key, peak_probability = dominant_probability(peak_row, ENSO_EL_NINO_PROB_COLUMNS)

    decline_row = None
    previous_score = el_nino_strength_score(peak_row)
    previous_strong_plus = probability_sum(peak_row, ["el_nino_strong", "el_nino_very_strong"])
    for row in rows[peak_index + 1:]:
        score = el_nino_strength_score(row)
        if score < previous_score:
            decline_row = {
                "row": row,
                "previous_score": previous_score,
                "current_score": score,
                "previous_strong_plus": previous_strong_plus,
                "current_strong_plus": probability_sum(row, ["el_nino_strong", "el_nino_very_strong"]),
            }
            break
        previous_score = score
        previous_strong_plus = probability_sum(row, ["el_nino_strong", "el_nino_very_strong"])

    start_row = first_el_nino_start_row(rows)
    peak_total = probability_sum(peak_row, ENSO_EL_NINO_PROB_COLUMNS)
    peak_strong_plus = probability_sum(peak_row, ["el_nino_strong", "el_nino_very_strong"])
    peak_super = probability_value(peak_row, "el_nino_very_strong")
    peak_level = el_nino_strength_floor(peak_row)
    dominant_peak_label = ENSO_STRENGTH_PROB_LABELS[peak_key]
    sugar_bias_text, sugar_logic = forecast_market_bias(peak_row)

    if decline_row is None:
        decline = {
            "period": "预测窗口内未见明确回落",
            "detail": "峰值之后表内 RONI 加权评分尚未下降，利多天气风险暂不宜过早下修。",
            "has_decline": False,
        }
    else:
        decline = {
            "period": season_month_range_display(decline_row["row"]),
            "detail": (
                f"从{season_month_range_display(decline_row['row'])}开始，"
                f"强+超强概率由 {decline_row['previous_strong_plus']}% "
                f"降至 {decline_row['current_strong_plus']}%。"
            ),
            "has_decline": True,
        }

    if start_row is None:
        start = {
            "period": "预测窗口内未触发",
            "detail": "总厄尔尼诺概率尚未达到 45%，暂不判定明确起始窗口。",
        }
    else:
        start = {
            "period": season_month_range_display(start_row),
            "detail": (
                f"总厄尔尼诺概率 {probability_sum(start_row, ENSO_EL_NINO_PROB_COLUMNS)}%，"
                f"判定为{el_nino_strength_floor(start_row)}。"
            ),
        }

    conclusion = (
        f"{season_month_range_display(peak_row)}为表内最强预测窗口，"
        f"判定为{peak_level}；强+超强概率 {peak_strong_plus}%，"
        f"其中超强 {peak_super}%，总厄尔尼诺 {peak_total}%。"
    )
    focus = (
        "印度、泰国季风降雨是否偏弱、甘蔗产区土壤水分和单产预期；"
        "同时跟踪巴西中南部降雨对压榨节奏的扰动；"
        "回落窗口出现后，观察厄尔尼诺利多是否边际降温。"
    )

    return {
        "issued": payload.get("issued", "未标注"),
        "segments": display_segments,
        "start": start,
        "peak": {
            "period": season_month_range_display(peak_row),
            "level": peak_level,
            "dominant": dominant_peak_label,
            "dominant_value": peak_probability,
            "strong_plus": peak_strong_plus,
            "total": peak_total,
            "super": peak_super,
        },
        "decline": decline,
        "conclusion": conclusion,
        "focus": focus,
        "sugar_bias": sugar_bias_text,
        "sugar_logic": sugar_logic,
        "method_text": (
            "表格来源：NOAA CPC ENSO Strength Probabilities"
            f"（Issued {payload.get('issued', '未标注')}）。"
            "内部按 RONI / Relative Niño-3.4 分档概率计算：弱=1、中等=2、强=3、超强=4 加权，"
            "选择评分最高的月份窗口作为预测峰值；强度摘要按 45% 规则输出。"
        ),
    }


def download_forecast_images() -> None:
    try:
        download_binary(NINO34_FORECAST_IMAGE_URL, NINO34_FORECAST_OUT)
        print(f"Niño 3.4 预测图下载成功：{NINO34_FORECAST_OUT}")
    except Exception as exc:
        warn(f"Niño 3.4 预测图下载失败，保留已有图片：{exc}")

    try:
        html_text = fetch_text(
            ENSO_STRENGTH_PAGE_URL,
            headers={**BROWSER_HEADERS, "Referer": ENSO_STRENGTH_PAGE_URL},
        )
        try:
            payload = parse_enso_strength_probabilities(html_text)
            store_enso_strength_probabilities(payload)
            print(f"ENSO 强度概率表解析成功：Issued {payload['issued']}")
        except Exception as exc:
            warn(f"ENSO 强度概率表解析失败，预测结论将尝试使用缓存：{exc}")

        image_url = find_enso_strength_probabilities_url(ENSO_STRENGTH_PAGE_URL, html_text=html_text)
        download_binary(image_url, ENSO_STRENGTH_PROB_OUT, referer=ENSO_STRENGTH_PAGE_URL)
        print(f"ENSO 强度概率预测图下载成功：{ENSO_STRENGTH_PROB_OUT}")
    except Exception as exc:
        warn(f"ENSO 强度概率预测图下载失败，保留已有图片：{exc}")


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

    content = path.read_bytes()
    if content.startswith(b"\x89PNG"):
        mime_type = "image/png"
    elif content.startswith(b"\xff\xd8"):
        mime_type = "image/jpeg"
    elif content.startswith((b"GIF87a", b"GIF89a")):
        mime_type = "image/gif"
    else:
        mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        mime_type = "image/gif" if path.suffix.lower() == ".gif" else "image/png"

    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def imd_rainfall_legend_html(path: Path) -> str:
    if path.name != "imd_rainfall_cumulative.png" or not IMD_RAINFALL_LEGEND_OUT.exists():
        return ""

    legend_src = image_file_to_data_uri(
        IMD_RAINFALL_LEGEND_OUT,
        "IMD Rainfall legend",
        "Rainfall departure categories",
    )
    return f"""
        <div class="weather-legend">
          <img src="{legend_src}" alt="IMD Rainfall departure legend" loading="lazy" />
          <div class="weather-legend-note">图例来源：IMD 官方降雨距平分类</div>
        </div>
    """


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
    return format_timestamp_beijing(path.stat().st_mtime)


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


def metric_value(metric: dict | None) -> float | None:
    if metric is None:
        return None
    try:
        return float(metric.get("value"))
    except (TypeError, ValueError):
        return None


def interpretation(text: str, tone: str, role: str, rank: int = 0) -> dict:
    return {"text": text, "tone": tone, "role": role, "rank": rank}


def classify_nino34(value: float | None) -> dict:
    if value is None:
        return interpretation("数据缺失，暂无法解读", "neutral", "neutral")
    if value >= 2.0:
        return interpretation("超强厄尔尼诺倾向", "warm", "enso_warm", 4)
    if value >= 1.5:
        return interpretation("强厄尔尼诺倾向", "warm", "enso_warm", 3)
    if value >= 1.0:
        return interpretation("中等厄尔尼诺倾向", "warm", "enso_warm", 2)
    if value >= 0.5:
        return interpretation("弱厄尔尼诺倾向", "warm", "enso_warm", 1)
    if value > -0.5:
        return interpretation("中性", "neutral", "neutral")
    if value > -1.0:
        return interpretation("弱拉尼娜倾向", "cool", "enso_cool", 1)
    if value > -1.5:
        return interpretation("中等拉尼娜倾向", "cool", "enso_cool", 2)
    if value > -2.0:
        return interpretation("强拉尼娜倾向", "cool", "enso_cool", 3)
    return interpretation("超强拉尼娜倾向", "cool", "enso_cool", 4)


def classify_soi(value: float | None, equatorial: bool = False) -> dict:
    if value is None:
        return interpretation("数据缺失，暂无法解读", "neutral", "neutral")
    suffix = "赤道大气响应" if equatorial else "大气响应"
    if value <= -1.5:
        return interpretation(f"较强厄尔尼诺型{suffix}", "warm", "enso_warm", 3)
    if value <= -1.0:
        return interpretation(f"明显厄尔尼诺型{suffix}", "warm", "enso_warm", 2)
    if value <= -0.5:
        return interpretation(f"偏厄尔尼诺型{suffix}", "warm", "enso_warm", 1)
    if value < 0.5:
        return interpretation("中性", "neutral", "neutral")
    if value < 1.0:
        return interpretation(f"偏拉尼娜型{suffix}", "cool", "enso_cool", 1)
    if value < 1.5:
        return interpretation(f"明显拉尼娜型{suffix}", "cool", "enso_cool", 2)
    return interpretation(f"较强拉尼娜型{suffix}", "cool", "enso_cool", 3)


def classify_heat_content(value: float | None) -> dict:
    if value is None:
        return interpretation("数据缺失，暂无法解读", "neutral", "neutral")
    if value >= 2.0:
        return interpretation("暖水储备很强", "warm", "enso_warm", 3)
    if value >= 1.0:
        return interpretation("暖水储备明显偏多", "warm", "enso_warm", 2)
    if value >= 0.5:
        return interpretation("暖水储备偏多", "warm", "enso_warm", 1)
    if value > -0.5:
        return interpretation("中性", "neutral", "neutral")
    if value > -1.0:
        return interpretation("冷水储备偏多", "cool", "enso_cool", 1)
    if value > -2.0:
        return interpretation("冷水储备明显偏多", "cool", "enso_cool", 2)
    return interpretation("冷水储备很强", "cool", "enso_cool", 3)


def classify_iod(value: float | None) -> dict:
    if value is None:
        return interpretation("数据缺失，暂无法解读", "neutral", "neutral")
    if value >= 0.8:
        return interpretation("较强正 IOD", "warm", "iod_positive", 2)
    if value >= 0.4:
        return interpretation("正 IOD 倾向", "warm", "iod_positive", 1)
    if value > -0.4:
        return interpretation("中性", "neutral", "neutral")
    if value > -0.8:
        return interpretation("负 IOD 倾向", "cool", "iod_negative", 1)
    return interpretation("较强负 IOD", "cool", "iod_negative", 2)


def classify_metric(kind: str, metric: dict | None) -> dict:
    value = metric_value(metric)
    if kind in {"nino_weekly", "nino_monthly"}:
        return classify_nino34(value)
    if kind == "soi":
        return classify_soi(value)
    if kind == "eq_soi":
        return classify_soi(value, equatorial=True)
    if kind == "heat":
        return classify_heat_content(value)
    if kind == "iod":
        return classify_iod(value)
    return interpretation("暂无法解读", "neutral", "neutral")


def metric_interpretation(item: dict) -> dict:
    return classify_metric(str(item.get("kind", "")), item.get("metric"))


def support_strength_word(rank: int) -> str:
    if rank >= 3:
        return "较强支持"
    if rank == 2:
        return "明显支持"
    if rank == 1:
        return "偏支持"
    return "支持"


def enso_support_display(result: dict, subject: str) -> str:
    role = result.get("role")
    rank = int(result.get("rank", 0) or 0)
    if role == "enso_warm":
        return f"{subject}{support_strength_word(rank)}厄尔尼诺"
    if role == "enso_cool":
        return f"{subject}{support_strength_word(rank)}拉尼娜"
    return f"{subject}中性"


def metric_status_display_text(item: dict, result: dict) -> str:
    kind = str(item.get("kind", ""))
    text = str(result.get("text", "")).replace("非常强", "超强")
    if "数据缺失" in text or "暂无法" in text:
        return text

    if kind in {"nino_weekly", "nino_monthly"}:
        if text == "中性":
            return "海温中性"
        return text.replace("倾向", "").strip()

    if kind == "soi":
        if text == "中性":
            return "大气响应中性"
        return enso_support_display(result, "大气端")

    if kind == "eq_soi":
        if text == "中性":
            return "赤道大气响应中性"
        return enso_support_display(result, "赤道大气")

    if kind == "heat":
        if text == "中性":
            return "次表层热量中性"
        return enso_support_display(result, "次表层")

    if kind == "iod":
        role = result.get("role")
        rank = int(result.get("rank", 0) or 0)
        if role == "iod_positive":
            return "有利印度季风降雨" if rank >= 2 else "偏有利印度季风降雨"
        if role == "iod_negative":
            return "增加印度季风偏弱风险" if rank >= 2 else "偏增加印度季风偏弱风险"
        return "对印度季风影响中性"

    return text.replace("倾向", "").strip()


def enso_direction(result: dict) -> str:
    role = result.get("role")
    if role == "enso_warm":
        return "warm"
    if role == "enso_cool":
        return "cool"
    return "neutral"


def enso_label(direction: str) -> str:
    if direction == "warm":
        return "厄尔尼诺"
    if direction == "cool":
        return "拉尼娜"
    return "中性"


def subject_value_text(name: str, result: dict) -> str:
    joiner = " 为" if re.search(r"[A-Za-z0-9]$", name) else "为"
    return f"{name}{joiner}{result['text']}"


def pair_interpretation_text(
    first_name: str,
    first_result: dict,
    second_name: str,
    second_result: dict,
) -> str:
    if first_result["text"] == second_result["text"]:
        return f"{first_name}和{second_name}均为{first_result['text']}"
    return (
        f"{subject_value_text(first_name, first_result)}，"
        f"{subject_value_text(second_name, second_result)}"
    )


def build_nino_state(weekly: dict, monthly: dict) -> dict:
    weekly_direction = enso_direction(weekly)
    monthly_direction = enso_direction(monthly)

    if weekly_direction != "neutral" and monthly_direction != "neutral":
        if weekly_direction != monthly_direction:
            return {
                "direction": "mixed",
                "state": "Niño 3.4 周度与月度分歧",
                "rank": 0,
                "consistency": "mixed",
                "detail": pair_interpretation_text("Niño 3.4 周度", weekly, "月度", monthly),
            }
        return {
            "direction": monthly_direction,
            "state": monthly["text"],
            "rank": int(monthly.get("rank", 0)),
            "consistency": "aligned",
            "detail": pair_interpretation_text("Niño 3.4 周度", weekly, "月度", monthly),
        }

    if monthly_direction != "neutral":
        return {
            "direction": monthly_direction,
            "state": monthly["text"],
            "rank": int(monthly.get("rank", 0)),
            "consistency": "partial",
            "detail": pair_interpretation_text("Niño 3.4 周度", weekly, "月度", monthly),
        }

    if weekly_direction != "neutral":
        return {
            "direction": weekly_direction,
            "state": f"短期{weekly['text']}",
            "rank": int(weekly.get("rank", 0)),
            "consistency": "partial",
            "detail": pair_interpretation_text("Niño 3.4 周度", weekly, "月度", monthly),
        }

    return {
        "direction": "neutral",
        "state": "中性",
        "rank": 0,
        "consistency": "neutral",
        "detail": pair_interpretation_text("Niño 3.4 周度", weekly, "月度", monthly),
    }


def component_alignment(direction: str, result: dict) -> str:
    result_direction = enso_direction(result)
    if direction not in {"warm", "cool"} or result_direction == "neutral":
        return "neutral"
    if result_direction == direction:
        return "support"
    return "conflict"


def build_atmosphere_status(direction: str, soi: dict, eq_soi: dict) -> dict:
    alignments = [
        component_alignment(direction, soi),
        component_alignment(direction, eq_soi),
    ]
    support = alignments.count("support")
    conflict = alignments.count("conflict")
    neutral = alignments.count("neutral")
    detail = pair_interpretation_text("SOI 30天", soi, "赤道 SOI", eq_soi)

    if direction not in {"warm", "cool"}:
        text = "大气端不参与主状态定向"
    elif support == 2:
        text = f"大气端与{enso_label(direction)}方向一致"
    elif support == 1 and neutral == 1:
        text = f"大气端部分支持{enso_label(direction)}方向"
    elif neutral == 2:
        text = "大气端中性"
    elif conflict == 1 and support == 1:
        text = "大气端内部出现分歧"
    elif conflict >= 1:
        text = f"大气端与{enso_label(direction)}方向相反"
    else:
        text = "大气端信号不明确"

    return {
        "support": support,
        "conflict": conflict,
        "neutral": neutral,
        "text": text,
        "detail": detail,
    }


def build_heat_status(direction: str, heat: dict) -> dict:
    alignment = component_alignment(direction, heat)
    if direction not in {"warm", "cool"}:
        text = "次表层海洋结构不参与主状态定向"
    elif alignment == "support":
        text = f"次表层海洋结构支持{enso_label(direction)}方向"
    elif alignment == "conflict":
        text = f"次表层海洋结构与{enso_label(direction)}方向相反"
    else:
        text = "次表层海洋结构中性"

    return {
        "alignment": alignment,
        "support": 1 if alignment == "support" else 0,
        "conflict": 1 if alignment == "conflict" else 0,
        "text": text,
        "detail": f"赤道太平洋 0-300m 热含量为{heat['text']}",
    }


def chain_strength_text(score: int) -> str:
    if score <= 2:
        return "偏弱"
    if score == 3:
        return "中等"
    if score <= 5:
        return "中等偏强"
    if score == 6:
        return "强"
    return "很强"


def build_chain_decision(interpretations: dict[str, dict]) -> dict:
    weekly = interpretations.get("nino_weekly", interpretation("数据缺失", "neutral", "neutral"))
    monthly = interpretations.get("nino_monthly", interpretation("数据缺失", "neutral", "neutral"))
    soi = interpretations.get("soi", interpretation("数据缺失", "neutral", "neutral"))
    eq_soi = interpretations.get("eq_soi", interpretation("数据缺失", "neutral", "neutral"))
    heat = interpretations.get("heat", interpretation("数据缺失", "neutral", "neutral"))

    nino = build_nino_state(weekly, monthly)
    direction = nino["direction"]

    if direction == "mixed":
        return {
            "main_state": nino["state"],
            "chain": "Niño 3.4 海温分歧链条",
            "strength": "分歧",
            "basis": f"{nino['detail']}，周度与月度海温方向不一致，暂不判定完整 ENSO 链条。",
        }

    atmosphere = build_atmosphere_status(direction, soi, eq_soi)
    heat_status = build_heat_status(direction, heat)

    if direction == "neutral":
        warm_aux = sum(
            1
            for item in (soi, eq_soi, heat)
            if enso_direction(item) == "warm"
        )
        cool_aux = sum(
            1
            for item in (soi, eq_soi, heat)
            if enso_direction(item) == "cool"
        )
        if warm_aux >= 2 and warm_aux > cool_aux:
            chain = "偏暖背景信号（Niño 3.4 未触发）"
        elif cool_aux >= 2 and cool_aux > warm_aux:
            chain = "偏冷背景信号（Niño 3.4 未触发）"
        else:
            chain = "未触发明确 ENSO 链条"
        return {
            "main_state": "中性",
            "chain": chain,
            "strength": "无明确链条",
            "basis": (
                f"{nino['detail']}，Niño 3.4 尚未越过 ENSO 判定阈值；"
                f"{atmosphere['detail']}；{heat_status['detail']}。"
            ),
        }

    label = enso_label(direction)
    conflict_count = atmosphere["conflict"] + heat_status["conflict"]
    support_count = atmosphere["support"] + heat_status["support"]

    if conflict_count >= 2:
        chain = f"{label}分歧链条"
        strength = "分歧"
    else:
        if nino["consistency"] == "aligned" and atmosphere["support"] > 0 and heat_status["support"]:
            chain = f"{label}完整链条"
        elif nino["consistency"] == "partial" and support_count >= 2:
            chain = f"{label}部分链条"
        elif atmosphere["support"] > 0 and heat_status["alignment"] == "neutral":
            chain = f"{label}海气链条（次表层中性）"
        elif atmosphere["neutral"] == 2 and heat_status["support"]:
            chain = f"{label}海洋链条（大气响应不足）"
        elif atmosphere["support"] > 0 and heat_status["conflict"]:
            chain = f"{label}海气链条，但次表层分歧"
        elif atmosphere["conflict"] > 0 and heat_status["support"]:
            chain = f"{label}海洋链条，但大气分歧"
        else:
            chain = f"{label}海温单项链条"

        score = int(nino.get("rank", 0))
        score += 1 if nino["consistency"] == "aligned" else 0
        score += atmosphere["support"]
        score += heat_status["support"]
        score -= atmosphere["conflict"]
        score -= 2 * heat_status["conflict"]
        if nino["consistency"] == "partial":
            score -= 1
        strength = chain_strength_text(score)

    basis = (
        f"{nino['detail']}；{atmosphere['detail']}，{atmosphere['text']}；"
        f"{heat_status['detail']}，{heat_status['text']}。"
        "链条强度只反映当前海温、大气和次表层海洋结构是否同向。"
    )
    return {
        "main_state": nino["state"],
        "chain": chain,
        "strength": strength,
        "basis": basis,
    }


def build_iod_note(iod: dict) -> str:
    if iod.get("role") == "iod_negative":
        return f"IOD 当前为{iod['text']}，单独提示印度季风偏弱和降雨不足风险。"
    if iod.get("role") == "iod_positive":
        return f"IOD 当前为{iod['text']}，往往有利于印度季风降雨。"
    return f"IOD 当前为{iod['text']}，对印度季风的异常指示暂不明显。"


def decision_direction(decision: dict) -> str:
    text = f"{decision.get('main_state', '')} {decision.get('chain', '')}"
    if "厄尔尼诺" in text or "偏暖" in text:
        return "warm"
    if "拉尼娜" in text or "偏冷" in text:
        return "cool"
    return "neutral"


def sugar_bias(direction: str, strength: str) -> str:
    if strength in {"分歧", "无明确链条"} or direction == "neutral":
        return "中性观望"
    if direction == "warm":
        if strength in {"中等偏强", "强", "很强"}:
            return "偏利多糖价"
        if strength == "中等":
            return "中性偏利多糖价"
        return "轻微利多糖价，仍需观察"
    if direction == "cool":
        if strength in {"中等偏强", "强", "很强"}:
            return "偏利空糖价"
        if strength == "中等":
            return "中性偏利空糖价"
        return "轻微利空糖价，仍需观察"
    return "中性观望"


def build_sugar_impact(decision: dict, iod: dict) -> dict:
    direction = decision_direction(decision)
    strength = str(decision.get("strength", ""))
    bias = sugar_bias(direction, strength)

    if strength == "分歧":
        return {
            "bias": bias,
            "text": (
                "当前 ENSO 链条内部存在分歧，暂不输出明确利多或利空方向。"
                "糖价需要优先跟踪印度、泰国和巴西的实际降雨、压榨进度、出口政策和库存变化。"
            ),
        }

    if direction == "warm":
        if iod.get("role") == "iod_negative":
            iod_modifier = "负 IOD 会进一步增加印度季风偏弱和降雨不足风险，强化亚洲甘蔗减产担忧。"
        elif iod.get("role") == "iod_positive":
            iod_modifier = "正 IOD 往往有利于印度季风降雨，可能部分对冲厄尔尼诺带来的亚洲偏干风险。"
        else:
            iod_modifier = "IOD 当前中性，对印度季风风险没有明显放大或对冲。"
        return {
            "bias": bias,
            "text": (
                f"{decision.get('main_state', '厄尔尼诺倾向')}下，印度、泰国等亚洲季风甘蔗产区偏干风险上升，"
                "甘蔗生长和单产预期容易承压；巴西中南部影响偏混合，需看降雨是否扰动压榨节奏。"
                f"{iod_modifier}整体看，这是糖价的天气风险溢价，{bias}。"
            ),
        }

    if direction == "cool":
        if iod.get("role") == "iod_negative":
            iod_modifier = "但负 IOD 会增加印度季风偏弱风险，可能削弱拉尼娜对亚洲甘蔗产区的利好。"
        elif iod.get("role") == "iod_positive":
            iod_modifier = "正 IOD 往往有利于印度季风降雨，可能进一步改善印度甘蔗产区水分条件。"
        else:
            iod_modifier = "IOD 当前中性，对印度季风风险没有明显放大或对冲。"
        return {
            "bias": bias,
            "text": (
                f"{decision.get('main_state', '拉尼娜倾向')}下，印度、泰国等亚洲季风甘蔗产区水分条件改善概率上升，"
                "有利于甘蔗生长和供应预期；不过过量降雨或洪涝也可能短期扰动收割。"
                f"{iod_modifier}整体看，对糖价的天气风险溢价偏降温，{bias}。"
            ),
        }

    return {
        "bias": bias,
        "text": (
            "当前 Niño 3.4 尚未触发明确 ENSO 主状态，ENSO 对甘蔗供应和糖价的边际指示不强。"
            "糖价更应关注主产区实际降雨、巴西压榨进度、印度出口政策和库存变化。"
        ),
    }


def metric_cards_data(metrics: list[dict]) -> list[dict]:
    return [
        {
            "title": "Niño 3.4 周度",
            "kind": "nino_weekly",
            "metric": find_metric(metrics, ["weekly", "nino"])
            or find_metric(metrics, ["weekly", "niño"]),
            "date_label": "数据时间",
            "note": "",
            "explanation": (
                "反映赤道中东太平洋 Niño 3.4 区域的一周平均海表温度距平，主要用于观察厄尔尼诺/拉尼娜状态的短期变化和转折信号。\n"
                "-0.5°C 到 +0.5°C 为中性；\n"
                "+0.5°C 到 +0.9°C 表示弱厄尔尼诺倾向；\n"
                "+1.0°C 到 +1.4°C 表示中等厄尔尼诺倾向；\n"
                "+1.5°C 到 +1.9°C 表示强厄尔尼诺倾向；\n"
                "+2.0°C 以上表示超强厄尔尼诺倾向；\n"
                "-0.5°C 到 -0.9°C 表示弱拉尼娜倾向；\n"
                "-1.0°C 到 -1.4°C 表示中等拉尼娜倾向；\n"
                "-1.5°C 到 -1.9°C 表示强拉尼娜倾向；\n"
                "低于 -2.0°C 表示超强拉尼娜倾向。"
            ),
        },
        {
            "title": "SOI 30天",
            "kind": "soi",
            "metric": find_metric(metrics, ["soi", "海平面"]) or find_metric(metrics, ["soi"]),
            "date_label": "数据时间",
            "note": "",
            "explanation": (
                "反映 Tahiti 与 Darwin 两地海平面气压差的标准化异常，主要用于判断大气端是否和海温变化状态一致。\n"
                "-0.5 到 +0.5 为中性；\n"
                "-0.5 到 -1.0 表示偏厄尔尼诺型大气响应；\n"
                "低于 -1.0 表示明显厄尔尼诺型大气响应；\n"
                "低于 -1.5 表示较强厄尔尼诺型大气响应；\n"
                "+0.5 到 +1.0 表示偏拉尼娜型大气响应；\n"
                "高于 +1.0 表示明显拉尼娜型大气响应；\n"
                "高于 +1.5 表示较强拉尼娜型大气响应。"
            ),
        },
        {
            "title": "赤道太平洋 0-300m 次表层水温",
            "kind": "heat",
            "metric": find_metric(metrics, ["heatcentra"]) or find_metric(metrics, ["0-300m"]),
            "date_label": "数据时间",
            "note": "区域：160E-80W",
            "explanation": (
                "反映赤道太平洋上层 300 米海洋平均温度相对常年的偏离程度，主要用于判断赤道太平洋海表偏暖或偏冷背后是否有海洋内部热量支撑。\n"
                "-0.5°C 到 +0.5°C 为中性；\n"
                "+0.5°C 到 +1.0°C 表示暖水储备偏多，当前海表偏暖有一定内部支撑；\n"
                "+1.0°C 到 +2.0°C 表示暖水储备明显偏多，当前厄尔尼诺倾向的内部支撑较强；\n"
                "高于 +2.0°C 表示暖水储备很强，当前厄尔尼诺链条的海洋内部结构较强；\n"
                "-0.5°C 到 -1.0°C 表示冷水储备偏多，当前海表偏冷有一定内部支撑；\n"
                "-1.0°C 到 -2.0°C 表示冷水储备明显偏多，当前拉尼娜倾向的内部支撑较强；\n"
                "低于 -2.0°C 表示冷水储备很强，当前拉尼娜链条的海洋内部结构较强。"
            ),
        },
        {
            "title": "Niño 3.4 月度",
            "kind": "nino_monthly",
            "metric": find_metric(metrics, ["niño", "月度"]) or find_metric(metrics, ["nino", "月度"]),
            "date_label": "数据月份",
            "note": "",
            "explanation": (
                "反映赤道中东太平洋 Niño 3.4 区域的月平均海表温度距平，主要用于判断厄尔尼诺/拉尼娜状态的月度背景强弱。\n"
                "-0.5°C 到 +0.5°C 为中性；\n"
                "+0.5°C 到 +0.9°C 表示弱厄尔尼诺倾向；\n"
                "+1.0°C 到 +1.4°C 表示中等厄尔尼诺倾向；\n"
                "+1.5°C 到 +1.9°C 表示强厄尔尼诺倾向；\n"
                "+2.0°C 以上表示超强厄尔尼诺倾向；\n"
                "-0.5°C 到 -0.9°C 表示弱拉尼娜倾向；\n"
                "-1.0°C 到 -1.4°C 表示中等拉尼娜倾向；\n"
                "-1.5°C 到 -1.9°C 表示强拉尼娜倾向；\n"
                "低于 -2.0°C 表示超强拉尼娜倾向。"
            ),
        },
        {
            "title": "赤道 SOI",
            "kind": "eq_soi",
            "metric": find_metric(metrics, ["equatorial", "soi"]) or find_metric(metrics, ["赤道", "soi"]),
            "date_label": "数据月份",
            "note": "",
            "explanation": (
                "反映赤道太平洋附近海平面气压差的标准化异常，主要用于判断赤道太平洋的大气环流是否和海温变化状态一致。\n"
                "-0.5 到 +0.5 为中性；\n"
                "-0.5 到 -1.0 表示偏厄尔尼诺型赤道大气响应；\n"
                "低于 -1.0 表示明显厄尔尼诺型赤道大气响应；\n"
                "低于 -1.5 表示较强厄尔尼诺型赤道大气响应；\n"
                "+0.5 到 +1.0 表示偏拉尼娜型赤道大气响应；\n"
                "高于 +1.0 表示明显拉尼娜型赤道大气响应；\n"
                "高于 +1.5 表示较强拉尼娜型赤道大气响应。"
            ),
        },
        {
            "title": "IOD",
            "kind": "iod",
            "metric": find_metric(metrics, ["iod"]),
            "date_label": "数据时间",
            "note": "",
            "explanation": (
                "反映热带印度洋西部和东部海温距平的差值，主要用于判断印度洋海温分布是否异常。\n"
                "-0.4°C 到 +0.4°C 为中性；\n"
                "+0.4°C 到 +0.8°C 表示正 IOD 倾向；\n"
                "高于 +0.8°C 表示较强正 IOD；\n"
                "-0.4°C 到 -0.8°C 表示负 IOD 倾向；\n"
                "低于 -0.8°C 表示较强负 IOD。\n"
                "正 IOD 往往有利于印度季风降雨，负 IOD 则可能增加印度季风偏弱和降雨不足的风险。"
            ),
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
.metrics-grid, .weather-grid, .forecast-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.forecast-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.metric-card, .country-section, .weather-card, .footer {
  background: rgba(255,255,255,.94); border: 1px solid var(--border); box-shadow: 0 12px 28px rgba(18,115,156,.08);
}
.metric-card { min-height: 154px; padding: 22px 20px; border-radius: 16px; text-align: center; border-top: 5px solid var(--accent); }
.metric-name {
  min-height: 38px; display: flex; align-items: center; justify-content: center;
  flex-wrap: wrap; gap: 2px; color: var(--muted); font-weight: 800; font-size: 16px;
}
.metric-status { color: #587482; font-size: 13px; font-weight: 850; }
.metric-status.warm { color: #9A5A17; }
.metric-status.cool { color: #166D8F; }
.metric-status.neutral { color: #587482; }
.metric-value { margin: 8px 0 12px; color: var(--primary); font-size: clamp(31px, 3vw, 44px); line-height: 1; font-weight: 850; }
.metric-date { color: #7EA2B3; font-size: 13px; line-height: 1.45; }
.metric-note { margin-top: 6px; color: #2E8DB4; font-size: 12px; font-weight: 700; }
.metric-explanation { margin-top: 12px; color: #4F7081; font-size: 12px; line-height: 1.65; text-align: left; white-space: pre-line; }
.summary-panel {
  margin: 18px 0 0; padding: 18px 22px; border-radius: 16px;
  background: rgba(255,255,255,.96); border: 1px solid var(--border);
  border-left: 5px solid var(--accent); box-shadow: 0 12px 28px rgba(18,115,156,.07);
}
.summary-label { color: var(--primary); font-size: 15px; line-height: 1.4; font-weight: 850; }
.summary-lines { margin-top: 9px; display: grid; gap: 5px; color: #4F7081; font-size: 13px; line-height: 1.65; }
.summary-line strong { color: var(--primary); font-weight: 850; }
.summary-value { font-weight: 850; }
.summary-value.warm, .summary-value.bullish { color: #C43D2F; }
.summary-value.cool, .summary-value.bearish { color: #166D8F; }
.summary-value.neutral { color: #587482; }
.summary-text { margin-top: 9px; color: #4F7081; font-size: 13px; line-height: 1.7; }
.forecast-key-grid {
  margin-top: 13px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px; padding-bottom: 13px; border-bottom: 1px solid var(--border);
}
.forecast-key-item { min-width: 0; }
.forecast-key-label { color: #7EA2B3; font-size: 12px; font-weight: 850; }
.forecast-key-value { margin-top: 4px; color: var(--primary); font-size: 18px; line-height: 1.25; font-weight: 900; }
.forecast-key-value.warm, .forecast-key-value.bullish { color: #C43D2F; }
.forecast-key-value.cool, .forecast-key-value.bearish { color: #166D8F; }
.forecast-key-value.neutral { color: #587482; }
.forecast-key-detail { margin-top: 4px; color: #587482; font-size: 12px; line-height: 1.45; }
.forecast-segments { margin-top: 14px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.forecast-segment {
  padding: 10px 11px 11px; border-radius: 10px; border: 1px solid var(--border);
  background: #F8FDFF;
}
.forecast-segment-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.forecast-period { color: var(--primary); font-size: 15px; line-height: 1.25; font-weight: 900; }
.forecast-level { color: #C43D2F; font-size: 12px; line-height: 1.3; font-weight: 900; text-align: right; }
.forecast-probs { margin-top: 8px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px 8px; }
.forecast-prob { color: #4F7081; font-size: 12px; line-height: 1.35; white-space: nowrap; }
.forecast-prob strong { color: #1C6F95; font-weight: 900; }
.forecast-segment-note { margin-top: 8px; color: #7EA2B3; font-size: 11px; line-height: 1.45; }
.summary-panel + .forecast-grid, .summary-panel + .metrics-grid { margin-top: 18px; }
.country-section { margin-top: 22px; padding: 20px; border-radius: 18px; }
.country-header { display: flex; justify-content: space-between; gap: 20px; margin-bottom: 16px; }
.country-header h3 { margin: 0 0 6px; color: var(--primary); font-size: 24px; }
.country-header p { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.6; }
.country-badge { align-self: flex-start; padding: 7px 11px; border-radius: 999px; background: #E7F8FF; color: var(--primary); font-size: 13px; font-weight: 700; }
.weather-card { margin: 0; overflow: hidden; border-radius: 14px; }
.weather-image-wrap { padding: 11px 11px 0; background: linear-gradient(180deg, #FFFFFF, #F4FCFF); }
.weather-card img { display: block; width: 100%; aspect-ratio: 16 / 10; object-fit: contain; border: 1px solid var(--border); border-radius: 10px; background: #FFFFFF; }
.forecast-grid .weather-card img { aspect-ratio: 16 / 9; }
figcaption { padding: 12px 14px 15px; }
.image-title { margin-bottom: 6px; color: var(--primary); font-weight: 800; font-size: 15px; line-height: 1.45; }
.image-period { margin-bottom: 6px; color: #2E8DB4; font-size: 12px; font-weight: 700; line-height: 1.55; }
.image-date { color: #8AA9B8; font-size: 11px; line-height: 1.45; }
.weather-legend {
  margin: 9px 0 4px; padding: 7px 8px; border: 1px solid var(--border);
  border-radius: 8px; background: #FFFFFF;
}
.weather-card .weather-legend img {
  width: 100%; height: auto; aspect-ratio: auto; object-fit: contain;
  border: 0; border-radius: 0; background: transparent;
}
.weather-legend-note { margin-top: 5px; color: #8AA9B8; font-size: 10px; line-height: 1.35; }
.footer { margin-top: 28px; padding: 16px 20px; border-radius: 14px; color: var(--muted); font-size: 13px; line-height: 1.7; }
@media (max-width: 1120px) {
  .metrics-grid, .weather-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .forecast-segments { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .page { width: min(100% - 28px, 1480px); padding-top: 18px; }
  .hero, .country-header { flex-direction: column; align-items: flex-start; }
  .hero-meta { text-align: left; }
  .pill { justify-self: start; }
  .metrics-grid, .weather-grid, .forecast-grid { grid-template-columns: 1fr; }
  .forecast-key-grid, .forecast-segments { grid-template-columns: 1fr; }
  .country-section { padding: 15px; }
}
"""


def metric_card(item: dict) -> str:
    metric = item["metric"]
    result = metric_interpretation(item)
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
      <div class="metric-name">
        <span>{escape(item["title"])}</span><span class="metric-status {escape(result["tone"])}">（{escape(metric_status_display_text(item, result))}）</span>
      </div>
      <div class="metric-value">{escape(value_text)}</div>
      <div class="metric-date">{escape(date_text)}</div>
      {note_html}
      {explanation_html}
    </article>
    """


def display_main_state(text: str) -> str:
    return str(text or "").replace("倾向", "").strip()


def chain_alignment_summary(decision: dict) -> str:
    chain = str(decision.get("chain", ""))
    strength = str(decision.get("strength", ""))
    direction = decision_direction(decision)

    if strength == "分歧" or "分歧" in chain:
        return "多指标存在分歧"
    if direction in {"warm", "cool"}:
        label = enso_label(direction)
        if "完整链条" in chain:
            return f"{label}多指标相符"
        if "部分链条" in chain:
            return f"{label}多指标部分相符"
        if "海气链条" in chain:
            return f"{label}海温与大气相符"
        if "海洋链条" in chain:
            return f"{label}海温与次表层相符"
        if "海温单项链条" in chain:
            return f"{label}主要由海温触发"
        return f"{label}信号占优"
    if "偏暖" in chain:
        return "偏暖背景信号，但海温未触发"
    if "偏冷" in chain:
        return "偏冷背景信号，但海温未触发"
    return "多指标未形成明确方向"


def summary_tone_class(direction: str) -> str:
    if direction == "warm":
        return "warm"
    if direction == "cool":
        return "cool"
    return "neutral"


def sugar_tone_class(bias: str) -> str:
    if "利多" in bias:
        return "bullish"
    if "利空" in bias:
        return "bearish"
    return "neutral"


def summary_value(text: str, tone: str) -> str:
    return f'<span class="summary-value {escape(tone)}">{escape(text)}</span>'


def metric_summary_panel(cards: list[dict]) -> str:
    interpretations = {
        str(item.get("kind", "")): metric_interpretation(item)
        for item in cards
    }
    iod = interpretations.get("iod", interpretation("数据缺失", "neutral", "neutral"))
    decision = build_chain_decision(interpretations)
    sugar_impact = build_sugar_impact(decision, iod)
    direction = decision_direction(decision)
    main_state = display_main_state(decision["main_state"])
    main_state_html = summary_value(main_state, summary_tone_class(direction))
    chain_summary = chain_alignment_summary(decision)
    sugar_bias_html = summary_value(sugar_impact["bias"], sugar_tone_class(sugar_impact["bias"]))

    return f"""
    <section class="summary-panel">
      <div class="summary-label">ENSO 链条判定</div>
      <div class="summary-lines">
        <div class="summary-line"><strong>当前 ENSO 主状态：</strong>{main_state_html}</div>
        <div class="summary-line"><strong>多指标判断：</strong>{escape(chain_summary)}</div>
        <div class="summary-line"><strong>指标强度：</strong>{escape(decision["strength"])}</div>
        <div class="summary-line"><strong>糖价影响倾向：</strong>{sugar_bias_html}</div>
      </div>
    </section>
    """


def image_card(title: str, period: str, path: Path) -> str:
    img_src = image_file_to_data_uri(path if path.exists() else None, title, period)
    image_date = f"本地图片更新时间：{file_mtime(path)}" if path.exists() else "图片日期：占位图"
    legend_html = imd_rainfall_legend_html(path)
    return f"""
    <figure class="weather-card">
      <div class="weather-image-wrap">
        <img src="{img_src}" alt="{escape(title)}" loading="lazy" />
      </div>
      <figcaption>
        <div class="image-title">{escape(title)}</div>
        <div class="image-period">{escape(period)}</div>
        <div class="image-date">{escape(image_date)}</div>
        {legend_html}
      </figcaption>
    </figure>
    """


def forecast_images() -> list[tuple[str, str, Path]]:
    return [
        ("Nino3.4预测", "来源：NOAA CPC CFSv2 Niño 3.4 月度预测图", NINO34_FORECAST_OUT),
        ("厄尔尼诺强度概率预测", "来源：NOAA CPC ENSO Strength Probabilities", ENSO_STRENGTH_PROB_OUT),
    ]


def forecast_key_item(label: str, value: str, detail: str, tone: str = "") -> str:
    value_class = f"forecast-key-value {tone}".strip()
    return f"""
        <div class="forecast-key-item">
          <div class="forecast-key-label">{escape(label)}</div>
          <div class="{escape(value_class)}">{escape(value)}</div>
          <div class="forecast-key-detail">{escape(detail)}</div>
        </div>
    """


def forecast_segment_html(segment: dict) -> str:
    prob_html = "\n".join(
        f'          <span class="forecast-prob">{escape(label)} <strong>{value}%</strong></span>'
        for label, value in segment["probabilities"]
    )
    return f"""
      <div class="forecast-segment">
        <div class="forecast-segment-head">
          <span class="forecast-period">{escape(segment["period"])}</span>
          <span class="forecast-level">{escape(segment["level"])}</span>
        </div>
        <div class="forecast-probs">
{prob_html}
        </div>
        <div class="forecast-segment-note">
          强+超强 {segment["strong_plus"]}%；总厄尔尼诺 {segment["total"]}%
        </div>
      </div>
    """


def forecast_summary_panel() -> str:
    payload = latest_enso_strength_probabilities()
    if payload is None:
        return """
    <section class="summary-panel">
      <div class="summary-label">NOAA CPC 强度概率解读</div>
      <div class="summary-lines">
        <div class="summary-line"><strong>预测结论：</strong>NOAA CPC 强度概率表暂未抓取成功</div>
      </div>
      <div class="summary-text">图片仍会展示；强度概率结论将在下次成功读取表格后自动恢复。</div>
    </section>
    """

    analysis = analyze_enso_strength_forecast(payload)
    sugar_tone = sugar_tone_class(analysis["sugar_bias"])
    key_html = "\n".join(
        [
            forecast_key_item(
                "厄尔尼诺起始",
                analysis["start"]["period"],
                analysis["start"]["detail"],
            ),
            forecast_key_item(
                "最强预测",
                analysis["peak"]["period"],
                (
                    f"{analysis['peak']['level']}；强+超强 {analysis['peak']['strong_plus']}%，"
                    f"超强 {analysis['peak']['super']}%"
                ),
                "warm",
            ),
            forecast_key_item(
                "糖价影响",
                analysis["sugar_bias"],
                analysis["sugar_logic"],
                sugar_tone,
            ),
        ]
    )
    segments_html = "\n".join(forecast_segment_html(segment) for segment in analysis["segments"])

    return f"""
    <section class="summary-panel">
      <div class="summary-label">NOAA CPC 强度概率解读</div>
      <div class="forecast-key-grid">
{key_html}
      </div>
      <div class="summary-lines">
        <div class="summary-line"><strong>分段预测：</strong>按当前月份每隔两个月抽取一个 3 个月窗口，展示中性、弱、中等、强、超强概率。</div>
      </div>
      <div class="forecast-segments">
{segments_html}
      </div>
      <div class="summary-lines">
        <div class="summary-line"><strong>回落：</strong>{escape(analysis["decline"]["period"])}；{escape(analysis["decline"]["detail"])}</div>
        <div class="summary-line"><strong>预测结论：</strong>{escape(analysis["conclusion"])}</div>
        <div class="summary-line"><strong>重点关注：</strong>{escape(analysis["focus"])}</div>
      </div>
      <div class="summary-text">{escape(analysis["method_text"])}</div>
    </section>
    """


def forecast_section() -> str:
    summary = forecast_summary_panel()
    cards = "\n".join(image_card(title, period, path) for title, period, path in forecast_images())
    return f"""
    <div class="section-title">
      <h2>厄尔尼诺指标预测</h2>
      <span class="rule"></span>
    </div>

    {summary}

    <section class="forecast-grid">
      {cards}
    </section>
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


def strip_trailing_line_whitespace(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def build_html(metrics: list[dict]) -> str:
    generated_at = now_beijing().strftime("%Y-%m-%d %H:%M")
    metrics_saved_at = format_timestamp_beijing(METRICS_PAYLOAD_JSON_PATH.stat().st_mtime)

    metric_items = metric_cards_data(metrics)
    metric_cards = "\n".join(metric_card(item) for item in metric_items)
    metric_summary = metric_summary_panel(metric_items)
    forecast_html = forecast_section()
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
        <span>页面生成时间（北京时间）：{escape(generated_at)}</span>
        <span>指标保存时间（北京时间）：{escape(metrics_saved_at)}</span>
      </div>
    </header>

    {forecast_html}

    <div class="section-title">
      <h2>核心海气指标</h2>
      <span class="rule"></span>
    </div>

    {metric_summary}

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
    download_forecast_images()
    download_cpc_images()
    download_mausam_sw_monsoon()
    download_imd_rainfall_legend()
    run_browser_capture()
    note_browser_assets()

    html = strip_trailing_line_whitespace(build_html(metrics))
    OUTPUT_HTML.write_text(html, encoding="utf-8")

    print(f"HTML 已生成：{OUTPUT_HTML}")
    print(f"运行资产目录：{ASSETS_DIR}")
    if warnings:
        print("运行提示：")
        for item in warnings:
            print(f"- {item}")


if __name__ == "__main__":
    main()
