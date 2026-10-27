import csv
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from scripts.crawl_university_logos import candidate_image_urls


ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = ROOT / "data" / "master" / "university_logos.csv"
MASTER_PATH = ROOT / "data" / "master" / "master_admission.csv"


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_every_school_has_one_existing_logo_asset():
    logo_rows = _read_rows(METADATA_PATH)
    master_codes = {row["university_admission_code"] for row in _read_rows(MASTER_PATH)}
    logo_codes = [row["school_code"] for row in logo_rows]

    assert len(logo_codes) == len(set(logo_codes))
    assert set(logo_codes) == master_codes
    assert all(row["logo_path"] for row in logo_rows)
    assert all(row["status"] not in {"not_found", "logo_not_found", "official_site_unreachable"} for row in logo_rows)

    for row in logo_rows:
        asset = ROOT / row["logo_path"].lstrip("/")
        assert asset.is_file(), f"Missing logo asset for {row['school_code']}: {asset}"
        assert asset.stat().st_size >= 128, f"Empty logo asset for {row['school_code']}"


def test_every_logo_asset_is_readable():
    for row in _read_rows(METADATA_PATH):
        asset = ROOT / row["logo_path"].lstrip("/")
        if asset.suffix.lower() == ".svg":
            assert ET.parse(asset).getroot().tag.endswith("svg")
            continue
        with Image.open(asset) as image:
            image.verify()
        with Image.open(asset) as image:
            width, height = image.size
        assert width >= 16 and height >= 16, f"Logo is too small for {row['school_code']}: {width}x{height}"


def test_known_false_positive_sources_do_not_return():
    rows = {row["school_code"]: row for row in _read_rows(METADATA_PATH)}
    forbidden = {
        "HHK": ("logo-b.r", "iso-9001"),
        "KSA": ("logo-header", "top-501"),
        "KSV": ("logo-header", "top-501"),
        "TTN": ("logots", "tuyen-sinh"),
        "DLA": ("long-van",),
        "MTU": ("jste", "tap-chi"),
        "SKN": ("viettel",),
        "MHN": ("favicon", "wordpress"),
        "DDQ": ("coventry",),
        "DTS": ("favicon",),
        "DTN": ("voyage",),
    }
    for code, markers in forbidden.items():
        source = rows[code]["source_url"].lower()
        assert not any(marker in source for marker in markers), (code, source)


def test_unrelated_schools_do_not_share_the_same_logo_asset():
    rows = {row["school_code"]: row for row in _read_rows(METADATA_PATH)}

    def digest(code: str) -> str:
        asset = ROOT / rows[code]["logo_path"].lstrip("/")
        return hashlib.sha256(asset.read_bytes()).hexdigest()

    # These pairs were previously mapped to the same unrelated university
    # website, which made the crawler persist a plausible-looking wrong logo.
    unrelated_pairs = (
        ("LAH", "TTH"),
        ("SNH", "TTH"),
        ("DCV", "VUI"),
        ("DVH", "VHD"),
        ("DDS", "DDG"),
        ("DHN", "DHQ"),
        ("DHE", "DHQ"),
    )
    for left, right in unrelated_pairs:
        assert digest(left) != digest(right), (left, right)


def test_partner_logo_is_ranked_below_the_school_logo():
    html = b"""
        <html><body>
          <img src="/uploads/ads/logo-viettel-moi.png" alt="doi tac Viettel">
          <img src="/uploads/logos/NUTE_LOGO.png" alt="Truong Dai hoc Su pham Ky thuat Nam Dinh">
        </body></html>
    """
    ranked = candidate_image_urls(
        "https://nute.edu.vn/",
        html,
        "Truong Dai hoc Su pham Ky thuat Nam Dinh",
        "SKN",
    )
    assert ranked[0] == "https://nute.edu.vn/uploads/logos/NUTE_LOGO.png"
    assert "https://nute.edu.vn/uploads/ads/logo-viettel-moi.png" not in ranked
