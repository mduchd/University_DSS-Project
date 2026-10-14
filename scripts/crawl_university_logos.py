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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    "HNM": "https://hnmu.edu.vn/",
    "HPN": "https://hvpnvn.edu.vn/",
    "ANH": "https://hvann.edu.vn/",
    "DKY": "https://hmtu.edu.vn/",
    "GTS": "https://ut.edu.vn/",
    "HYD": "https://hvydhct.edu.vn/",
    "CSH": "https://hvcsnd.edu.vn/",
    "DKK": "https://uneti.edu.vn/",
    "LAH": "https://tcu.edu.vn/",
    "HHK": "https://vaa.edu.vn/",
    "PKA": "https://phenikaa-uni.edu.vn/",
    "PKH": "https://pkka.edu.vn/",
    "CSS": "https://dhcsnd.edu.vn/",
    "NHF": "https://hanu.vn/",
    "KQH": "https://mta.edu.vn/",
    "YTC": "https://huph.edu.vn/",
    "HQT": "https://dav.edu.vn/",
    "ANS": "https://dhannd.edu.vn/",
    "YCT": "https://ctump.edu.vn/",
    "TDM": "https://tdmu.edu.vn/",
    "TYS": "https://pnt.edu.vn/",
    "DTL": "https://thanglong.edu.vn/",
    "QST": "https://hcmus.edu.vn/",
    "DTT": "https://tdtu.edu.vn/",
    "QHX": "https://ussh.vnu.edu.vn/",
    "LPH": "https://hlu.edu.vn/",
    "QHF": "https://ulis.vnu.edu.vn/",
    "HBT": "https://ajc.hcma.vn/",
    "QHT": "https://hus.vnu.edu.vn/",
    "QHE": "https://ueb.vnu.edu.vn/",
    "QSX": "https://hcmussh.edu.vn/",
    "DTS": "https://dts.tnu.edu.vn/",
    "LCH": "https://daihocchinhtri.edu.vn/",
    "TCT": "https://www.ctu.edu.vn/",
    "DKS": "https://tks.edu.vn/",
    "BPH": "https://hvbp.edu.vn/",
    "QHL": "https://law.vnu.edu.vn/",
    "DHS": "https://dhsphue.hueuni.edu.vn/",
    "QSC": "https://uit.edu.vn/",
    "SGD": "https://sgu.edu.vn/",
    "NQH": "https://hvkhqs.edu.vn/",
    "NTS": "https://cs2.ftu.edu.vn/",
    "HTA": "https://hvta.toaan.gov.vn/",
    "DDS": "https://ued.udn.vn/",
    "SP2": "https://hpu2.edu.vn/",
    "QHS": "https://education.vnu.edu.vn/",
    "VHS": "https://hcmuc.edu.vn/",
    "SPK": "https://hcmute.edu.vn/",
    "HTN": "https://hvtnvn.edu.vn/",
    "YQH": "https://hvqy.vn/",
    "QSK": "https://uel.edu.vn/",
    "HEH": "https://hocvienhaucan.edu.vn/",
    "LPS": "https://hcmulaw.edu.vn/",
    "KSA": "https://ueh.edu.vn/",
    "QHY": "https://med.vnu.edu.vn/",
    "DDK": "https://dut.udn.vn/",
    "DHF": "https://huflis.hueuni.edu.vn/",
    "DMS": "https://ufm.edu.vn/",
    "GSA": "https://utc2.edu.vn/",
    "TSN": "https://ntu.edu.vn/",
    "BVS": "https://hcm.ptit.edu.vn/",
    "YKV": "https://vmu.edu.vn/",
    "YDN": "https://dhktyduocdn.edu.vn/",
    "DTY": "https://tnmc.edu.vn/",
    "DHY": "https://huemed-univ.edu.vn/",
    "DDY": "https://yds.danang.gov.vn/",
    "KTS": "https://uah.edu.vn/",
    "HCA": "https://hvctcand.edu.vn/",
    "QSY": "https://uhsvnu.edu.vn/",
    "QSQ": "https://hcmiu.edu.vn/",
    "THV": "https://hvu.edu.vn/",
    "THP": "https://dhhp.edu.vn/",
    "HCP": "https://apd.edu.vn/",
    "MHN": "https://hou.edu.vn/",
    "LDA": "https://dhcd.edu.vn/",
    "HHA": "https://vimaru.edu.vn/",
    "KTA": "https://hau.edu.vn/",
    "TDV": "https://vinhuni.edu.vn/",
    "QSA": "https://agu.edu.vn/",
    "HCH": "https://apag.edu.vn/",
    "SPD": "https://dthu.edu.vn/",
    "QHK": "https://sisa.vnu.edu.vn/",
    "TTN": "https://ttn.edu.vn/",
    "DQN": "https://qnu.edu.vn/",
    "GNT": "https://spnttw.edu.vn/",
    "DDQ": "https://due.udn.vn/",
    "VKU": "https://vku.udn.vn/",
    "DTF": "https://sfl.tnu.edu.vn/",
    "HLU": "https://daihochalong.edu.vn/",
    "DKT": "https://hdu.edu.vn/",
    "DQB": "https://quangbinhuni.edu.vn/",
    "DPQ": "https://pdu.edu.vn/",
    "HHT": "https://htu.edu.vn/",
    "DMT": "https://humt.edu.vn/",
    "HCS": "https://hcma.vn/",
    "NHS": "https://hub.edu.vn/",
    "DLX": "https://ulsa.edu.vn/",
    "DBL": "https://blu.edu.vn/",
    "DQU": "https://qnamuni.edu.vn/",
    "DPY": "https://pyu.edu.vn/",
    "DDP": "https://kontum.udn.vn/",
    "TDH": "https://upes1.edu.vn/",
    "KCC": "https://ctuet.edu.vn/",
    "QHQ": "https://is.vnu.edu.vn/",
    "KCN": "https://usth.edu.vn/",
    "DCV": "https://vui.edu.vn/",
    "DVT": "https://tvu.edu.vn/",
    "NLS": "https://hcmuaf.edu.vn/",
    "HVC": "https://hcmca.edu.vn/",
    "SKH": "https://utehy.edu.vn/",
    "MBS": "https://ou.edu.vn/",
    "FBU": "https://fbu.edu.vn/",
    "GTA": "https://utt.edu.vn/",
    "MDA": "https://humg.edu.vn/",
    "DDL": "https://epu.edu.vn/",
    "TDS": "https://upes.edu.vn/",
    "DPD": "https://phuongdong.edu.vn/",
    "VLU": "https://vlute.edu.vn/",
    "KTD": "https://dau.edu.vn/",
    "DQK": "https://hubt.edu.vn/",
    "DTK": "https://tnut.edu.vn/",
    "STS": "https://hcmupes.edu.vn/",
    "UKH": "https://ukh.edu.vn/",
    "DSK": "https://ute.udn.vn/",
    "NHB": "https://bni.edu.vn/",
    "DHI": "https://kqt.hueuni.edu.vn/",
    "CMC": "https://cmc-u.edu.vn/",
    "NTT": "https://ntt.edu.vn/",
    "DHK": "https://hce.edu.vn/",
    "DHD": "https://htdl.hueuni.edu.vn/",
    "KGH": "https://pkka.edu.vn/",
    "DTC": "https://ictu.edu.vn/",
    "HVQ": "https://iem.edu.vn/",
    "DDT": "https://duytan.edu.vn/",
    "DNC": "https://nctu.edu.vn/",
    "HIU": "https://hiu.vn/",
    "TTU": "https://ttu.edu.vn/",
    "DCL": "https://cku.edu.vn/",
    "DVL": "https://vanlanguni.edu.vn/",
    "DPC": "https://ptu.edu.vn/",
    "UKB": "https://kbac.edu.vn/",
    "ETU": "https://daihochoabinh.edu.vn/",
    "DDN": "https://dainam.edu.vn/",
    "VTT": "https://vttu.edu.vn/",
    "DCH": "https://daihocdackong.edu.vn/",
    "KSV": "https://ueh.edu.vn/",
    "QHD": "https://qtkd.vnu.edu.vn/",
    "VGU": "https://vgu.edu.vn/",
    "TLS": "https://tlu.edu.vn/",
    "SDU": "https://saodo.edu.vn/",
    "PCS": "https://dhpccc.edu.vn/",
    "PCH": "https://dhpccc.edu.vn/",
    "NLN": "https://hcmuaf.edu.vn/",
    "DTD": "https://tdu.edu.vn/",
    "DKC": "https://hutech.edu.vn/",
    "DDU": "https://ddu.edu.vn/",
    "DLH": "https://lhu.edu.vn/",
    "DDB": "https://thanhdo.edu.vn/",
    "DHA": "https://hule.edu.vn/",
    "DYD": "https://yersin.edu.vn/",
    "TDD": "https://thanhdo.edu.vn/",
    "DBD": "https://bdu.edu.vn/",
    "DTV": "https://ltvu.edu.vn/",
    "VJU": "https://vju.ac.vn/",
    "BVU": "https://bvu.edu.vn/",
    "DHN": "https://hueuni.edu.vn/",
    "MIT": "https://mit.vn/",
    "DKB": "https://ktktbinhduong.edu.vn/",
    "TTG": "https://tgu.edu.vn/",
    "DTE": "https://tueba.edu.vn/",
    "PVU": "https://pvu.edu.vn/",
    "DNT": "https://huflit.edu.vn/",
    "SKV": "https://vuted.edu.vn/",
    "CEA": "https://naue.edu.vn/",
    "LNH": "https://vnuf.edu.vn/",
    "DVH": "https://vhu.edu.vn/",
    "DQT": "https://qu.edu.vn/",
    "HSU": "https://www.hoasen.edu.vn/",
    "DPT": "https://phtu.edu.vn/",
    "DVP": "https://trungvuong.edu.vn/",
    "YDD": "https://ndun.edu.vn/",
    "THU": "https://vju.ac.vn/",
    "DCD": "https://dntu.edu.vn/",
    "EIU": "https://eiu.edu.vn/",
    "TDB": "https://tdttbacninh.edu.vn/",
    "DHE": "https://hueuni.edu.vn/",
    "DTB": "https://tbuniversity.edu.vn/",
    "DHT": "https://husc.hueuni.edu.vn/",
    "DTZ": "https://tnus.edu.vn/",
    "HDT": "https://hdu.edu.vn/",
    "DNU": "https://dnu.edu.vn/",
    "DTM": "https://hcmunre.edu.vn/",
    "NTU": "https://nguyentrai.edu.vn/",
    "CCM": "https://hict.edu.vn/",
    "VUI": "https://vui.edu.vn/",
    "DHL": "https://huaf.edu.vn/",
    "DTQ": "https://is.tnu.edu.vn/",
    "SIU": "https://siu.edu.vn/",
    "DCA": "https://chuvanan.edu.vn/",
    "DLA": "https://dlu.edu.vn/",
    "DBH": "https://dbu.edu.vn/",
    "SKN": "https://spkt.namdinhuni.edu.vn/",
    "DTN": "https://tuaf.edu.vn/",
    "UMT": "https://umt.edu.vn/",
    "DCQ": "https://unihub.edu.vn/",
    "DHQ": "https://quangtri.hueuni.edu.vn/",
    "TBD": "https://tbd.edu.vn/",
    "DHV": "https://hvu.edu.vn/",
    "DPX": "https://phuxuan.edu.vn/",
    "HPU": "https://hpu.edu.vn/",
    "MTU": "https://mtu.edu.vn/",
    "VHD": "https://vhu.edu.vn/",
    "UFA": "https://dhtckt.edu.vn/",
    "GDU": "https://gdu.edu.vn/",
    "DDM": "https://qui.edu.vn/",
    "XDT": "https://mtu.edu.vn/",
    "DSG": "https://stu.edu.vn/",
    "DBG": "https://nlbg.edu.vn/",
    "TTB": "https://utb.edu.vn/",
    "TDL": "https://dlu.edu.vn/",
    "TQU": "https://tqu.edu.vn/",
    "TKG": "https://tuk.edu.vn/",
    "DVD": "https://dvtdt.edu.vn/",
    "DNB": "https://hlu.edu.vn/",
    "NVH": "https://vnam.edu.vn/",
    "NVS": "https://hcmcons.vn/",
    "DVX": "https://vux.edu.vn/",
    "DHH": "https://hht.edu.vn/",
    "MTS": "https://mythuat.edu.vn/",
    "MTH": "https://mythuatvietnam.edu.vn/",
    "SKD": "https://skda.edu.vn/",
    "ZNH": "https://vnq.edu.vn/",
    "DNV": "https://truongnoivu.edu.vn/",
    "DDA": "https://eaut.edu.vn/",
    "BMU": "https://bmtu.edu.vn/",
    "HQH": "https://hocvienhaiquan.edu.vn/",
    "TTH": "https://tcu.edu.vn/",
    "LBH": "https://tcu2.edu.vn/",
    "DHC": "https://khoagddc.hueuni.edu.vn/",
    "DLS": "https://ulsa2.edu.vn/",
    "HGH": "https://hvph.edu.vn/",
    "TGH": "https://tctt.edu.vn/",
    "TTD": "https://dsu.edu.vn/",
    "SNH": "https://tcu.edu.vn/",
    "HCB": "https://dhkthc.edu.vn/",
    "HCN": "https://dhkthc.edu.vn/",
    "PBH": "https://phao-binh.edu.vn/",
    "DFA": "https://ufba.edu.vn/",
    "DDV": "https://vnuk.udn.vn/",
    "HVD": "https://hvdt.edu.vn/",
    "LNS": "https://vnuf.edu.vn/",
    "QSP": "https://vnu.edu.vn/",
    "NLG": "https://hcmuaf.edu.vn/",
    "DTP": "https://laocai.tnu.edu.vn/",
    "DTG": "https://hagiang.tnu.edu.vn/",
    "LBS": "https://tcu.edu.vn/",
    "YHT": "https://hmu.edu.vn/",
    "VPH": "https://tdn.edu.vn/",
    "DDG": "https://ued.udn.vn/",
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


def download_proxy_favicon(official_url: str) -> tuple[bytes, str] | None:
    """Use Google's favicon resolver only when the official site blocks direct access."""
    proxy_url = "https://www.google.com/s2/favicons?domain_url=" + official_url + "&sz=128"
    return download_image(proxy_url)


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
        page_body = b""
        row["status"] = "official_site_unreachable"
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
    proxy = download_proxy_favicon(official_url)
    if proxy:
        body, extension = proxy
        target = ASSET_DIR / f"{code}.{extension}"
        target.write_bytes(body)
        row["source_url"] = official_url
        row["logo_path"] = f"/static/img/universities/{target.name}"
        row["status"] = "downloaded_favicon_proxy"
        return row
    if row["status"] != "official_site_unreachable":
        row["status"] = "logo_not_found"
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-schools", type=int, default=0)
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--workers", type=int, default=8)
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
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {
                executor.submit(crawl_school, school, not args.no_search): school
                for school in schools
            }
            for index, future in enumerate(as_completed(futures), start=1):
                row = future.result()
                writer.writerow(row)
                file.flush()
                print(f"[{index}/{len(schools)}] {row['school_code']} {row['status']}", flush=True)
                if args.delay:
                    time.sleep(max(0.0, args.delay))


if __name__ == "__main__":
    main()
