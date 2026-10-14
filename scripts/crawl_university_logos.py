"""Crawl and download university logos from official university websites.

Run from the project root:
    python scripts/crawl_university_logos.py
    python scripts/crawl_university_logos.py --max-schools 10 --delay 0.5
"""

from __future__ import annotations

import argparse
import csv
from html.parser import HTMLParser
import html
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "data" / "master" / "master_admission.csv"
OUTPUT_PATH = ROOT / "data" / "master" / "university_logos.csv"
ASSET_DIR = ROOT / "static" / "img" / "universities"
USER_AGENT = "LaBanDaiHoc-logo-crawler/1.0"
MAX_BYTES = 4 * 1024 * 1024

# Stable official domains for the most common schools in the current dataset.
# The search fallback is still used for codes not listed here.
KNOWN_DOMAINS = {
    "KHA": "https://neu.edu.vn/",
    "BKA": "https://hust.edu.vn/",
    "HTC": "https://hvtc.edu.vn/",
    "NHH": "https://hvnh.edu.vn/",
    "NTH": "https://ftu.edu.vn/",
    "YHB": "https://hmu.edu.vn/",
    "BVH": "https://ptit.edu.vn/",
    "SPH": "https://hnue.edu.vn/",
    "TMU": "https://tmu.edu.vn/",
    "SPS": "https://hcmue.edu.vn/",
    "YDS": "https://ump.edu.vn/",
    "QHI": "https://uet.vnu.edu.vn/",
    "GHA": "https://utc.edu.vn/",
    "YTB": "https://tbump.edu.vn/",
    "KMA": "https://actvn.edu.vn/",
    "DCN": "https://haui.edu.vn/",
    "YPB": "https://hpmu.edu.vn/",
    "IUH": "https://iuh.edu.vn/",
    "DKH": "https://hup.edu.vn/",
    "DCT": "https://huit.edu.vn/",
    "TLA": "https://tlu.edu.vn/",
    "VHH": "https://huc.edu.vn/",
    "HVN": "https://vnua.edu.vn/",
    "DDF": "https://ufl.udn.vn/",
    "XDA": "https://huce.edu.vn/",
    "DAD": "https://donga.edu.vn/",
    "FPT": "https://daihoc.fpt.edu.vn/",
    "UEF": "https://uef.edu.vn/",
    "DUT": "https://dut.udn.vn/",
}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: list[tuple[str, str]] = []
        self.links: list[tuple[str, str]] = []
        self.images: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(k).lower(): str(v or "") for k, v in attrs}
        tag = tag.lower()
        if tag == "meta":
            key = values.get("property") or values.get("name") or ""
            if key and values.get("content"):
                self.meta.append((key.lower(), values["content"]))
        elif tag == "link" and values.get("href"):
            self.links.append((values.get("rel", "").lower(), values["href"]))
        elif tag == "img" and values.get("src"):
            marker = " ".join(values.get(k, "") for k in ("alt", "title", "class", "id")).lower()
            self.images.append((marker, values["src"]))


def request_bytes(url: str, timeout: int = 12) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(request, timeout=timeout) as response:
        return response.read(MAX_BYTES + 1), response.headers.get_content_type()


def official_search_url(school_name: str) -> str | None:
    query = f'"{school_name}" website chính thức logo'
    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
    try:
        body, _ = request_bytes(url)
    except Exception:
        return None
    text = body.decode("utf-8", errors="ignore")
    matches = re.findall(r'class="result__a"[^>]+href="([^"]+)"', text)
    blocked = {"facebook.com", "youtube.com", "instagram.com", "linkedin.com", "wikipedia.org", "wikimedia.org"}
    for raw in matches:
        candidate = html.unescape(raw)
        values = parse_qs(urlparse(candidate).query)
        candidate = unquote(values.get("uddg", [candidate])[0])
        parsed = urlparse(candidate)
        host = parsed.netloc.lower().split(":")[0]
        if not host or any(host == item or host.endswith("." + item) for item in blocked):
            continue
        if host.endswith(".edu.vn") or host.endswith(".edu"):
            return f"{parsed.scheme or 'https'}://{host}/"
    return None


def official_url_for_school(school: dict[str, str], allow_search: bool = True) -> str | None:
    known = KNOWN_DOMAINS.get(school["school_code"])
    return known or (official_search_url(school["school_name"]) if allow_search else None)


def candidate_image_urls(page_url: str, body: bytes) -> list[str]:
    parser = PageParser()
    parser.feed(body.decode("utf-8", errors="ignore"))
    raw_urls: list[str] = []
    raw_urls.extend(value for marker, value in parser.images if "logo" in marker or "brand" in marker or "header" in marker)
    raw_urls.extend(value for rel, value in parser.links if "icon" in rel or "apple-touch-icon" in rel)
    raw_urls.extend(value for key, value in parser.meta if key in {"og:image", "twitter:image"})
    raw_urls.append("/favicon.ico")
    result: list[str] = []
    for value in raw_urls:
        absolute = urljoin(page_url, value)
        if absolute not in result and urlparse(absolute).scheme in {"http", "https"}:
            result.append(absolute)
    return result


def download_image(url: str) -> tuple[bytes, str] | None:
    try:
        body, content_type = request_bytes(url)
    except Exception:
        return None
    if not 128 <= len(body) <= MAX_BYTES:
        return None
    is_svg = body.lstrip().startswith(b"<svg") or b"<svg" in body[:500].lower()
    if not is_svg and not content_type.startswith("image/"):
        return None
    if is_svg:
        return body, "svg"
    if body.startswith(b"\x89PNG"):
        return body, "png"
    if body.startswith(b"\xff\xd8\xff"):
        return body, "jpg"
    if body.startswith(b"GIF8"):
        return body, "gif"
    if body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return body, "webp"
    if body.startswith(b"\x00\x00\x01\x00"):
        return body, "ico"
    subtype = content_type.split("/", 1)[-1].split(";", 1)[0].lower()
    return body, {"jpeg": "jpg", "x-icon": "ico", "vnd.microsoft.icon": "ico", "webp": "webp"}.get(subtype, "png")


def load_schools() -> list[dict[str, str]]:
    with MASTER_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        unique: dict[str, dict[str, str]] = {}
        for row in csv.DictReader(file):
            code = str(row.get("university_admission_code", "")).strip().upper()
            name = str(row.get("university_name", "")).strip()
            if code and name:
                unique.setdefault(code, {"school_code": code, "school_name": name})
        return list(unique.values())


def crawl_school(school: dict[str, str], allow_search: bool = True) -> dict[str, str]:
    code, name = school["school_code"], school["school_name"]
    row = {**school, "official_url": "", "source_url": "", "logo_path": "", "alt_text": f"Logo {name}", "status": "not_found"}
    official_url = official_url_for_school(school, allow_search=allow_search)
    if not official_url:
        return row
    row["official_url"] = official_url
    try:
        page_body, _ = request_bytes(official_url)
    except Exception:
        row["status"] = "official_site_unreachable"
        return row
    for image_url in candidate_image_urls(official_url, page_body):
        downloaded = download_image(image_url)
        if not downloaded:
            continue
        body, extension = downloaded
        target = ASSET_DIR / f"{code}.{extension}"
        target.write_bytes(body)
        row["source_url"] = image_url
        row["logo_path"] = f"/static/img/universities/{target.name}"
        row["status"] = "downloaded"
        return row
    row["status"] = "logo_not_found"
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-schools", type=int, default=0)
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--no-search", action="store_true", help="Only crawl explicitly known official domains")
    args = parser.parse_args()
    schools = load_schools()
    if args.max_schools > 0:
        schools = schools[: args.max_schools]
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = ["school_code", "school_name", "official_url", "source_url", "logo_path", "alt_text", "status"]
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for index, school in enumerate(schools, start=1):
            row = crawl_school(school, allow_search=not args.no_search)
            writer.writerow(row)
            file.flush()
            print(f"[{index}/{len(schools)}] {row['school_code']} {row['status']}", flush=True)
            time.sleep(max(0.0, args.delay))


if __name__ == "__main__":
    main()
