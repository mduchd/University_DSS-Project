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
import ssl
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, quote, quote_plus, unquote, urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "data" / "master" / "master_admission.csv"
OUTPUT_PATH = ROOT / "data" / "master" / "university_logos.csv"
ASSET_DIR = ROOT / "static" / "img" / "universities"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 "
    "LaBanDaiHocLogoAudit/1.0"
)
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
    "HYD": "https://vutm.edu.vn/",
    "CSH": "https://hvcsnd.edu.vn/",
    "DKK": "https://uneti.edu.vn/",
    "LAH": "https://www.sqlq1.edu.vn/",
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
    "DTS": "https://tnue.edu.vn/",
    "LCH": "https://daihocchinhtri.edu.vn/",
    "TCT": "https://www.ctu.edu.vn/",
    "DKS": "https://kiemsat.edu.vn/",
    "BPH": "https://hvbp.edu.vn/",
    "QHL": "https://law.vnu.edu.vn/",
    "DHS": "https://dhsphue.edu.vn/",
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
    "DDY": "https://smp.udn.vn/",
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
    "DKT": "https://uhd.edu.vn/",
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
    "DCV": "https://www.iuv.edu.vn/",
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
    "DHI": "http://huis.hueuni.edu.vn/",
    "CMC": "https://cmc-u.edu.vn/",
    "NTT": "https://ntt.edu.vn/",
    "DHK": "https://hce.edu.vn/",
    "DHD": "http://huht.hueuni.edu.vn/",
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
    "DDB": "https://thanhdong.edu.vn/",
    "DHA": "https://hule.edu.vn/",
    "DYD": "https://yersin.edu.vn/",
    "TDD": "https://thanhdo.edu.vn/",
    "DBD": "https://bdu.edu.vn/",
    "DTV": "https://ltvu.edu.vn/",
    "VJU": "https://vju.ac.vn/",
    "BVU": "https://bvu.edu.vn/",
    "DHN": "https://www.nghethuathue.edu.vn/",
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
    "THU": "https://tokyo-human.edu.vn/",
    "DCD": "https://dntu.edu.vn/",
    "EIU": "https://eiu.edu.vn/",
    "TDB": "https://tdttbacninh.edu.vn/",
    "DHE": "https://huet.hueuni.edu.vn/",
    "DTB": "https://tbuniversity.edu.vn/",
    "DHT": "https://husc.hueuni.edu.vn/",
    "DTZ": "https://tnus.edu.vn/",
    "HDT": "https://hdu.edu.vn/",
    "DNU": "https://dnpu.edu.vn/",
    "DVB": "https://tuetech.edu.vn/",
    "DTM": "https://hcmunre.edu.vn/",
    "NTU": "https://nguyentrai.edu.vn/",
    "CCM": "https://hict.edu.vn/",
    "VUI": "https://vui.edu.vn/",
    "DHL": "https://huaf.edu.vn/",
    "DTQ": "https://is.tnu.edu.vn/",
    "SIU": "https://siu.edu.vn/",
    "DCA": "https://chuvanan.edu.vn/",
    "DLA": "https://daihoclongan.edu.vn/",
    "DBH": "https://biu.edu.vn/",
    "SKN": "https://nute.edu.vn/",
    "DTN": "https://tuaf.edu.vn/",
    "UMT": "https://umt.edu.vn/",
    "DCQ": "https://unihub.edu.vn/",
    "DHQ": "https://quangtri.hueuni.edu.vn/",
    "TBD": "https://tbd.edu.vn/",
    "DHV": "https://dhv.edu.vn/",
    "DPX": "https://phuxuan.edu.vn/",
    "HPU": "https://hpu.edu.vn/",
    "MTU": "https://mtu.edu.vn/",
    "VHD": "https://viu.edu.vn/",
    "UFA": "https://dhtckt.edu.vn/",
    "GDU": "https://gdu.edu.vn/",
    "DDM": "https://qui.edu.vn/",
    "XDT": "https://muce.edu.vn/",
    "DSG": "https://stu.edu.vn/",
    "DBG": "https://nlbg.edu.vn/",
    "TTB": "https://utb.edu.vn/",
    "TDL": "https://dlu.edu.vn/",
    "TQU": "https://tqu.edu.vn/",
    "TKG": "https://tuk.edu.vn/",
    "DVD": "https://dvtdt.edu.vn/",
    "DNB": "http://hluv.edu.vn/",
    "NVH": "https://vnam.edu.vn/",
    "NVS": "https://hcmcons.vn/",
    "DVX": "https://vux.edu.vn/",
    "DHH": "https://hahoatien.edu.vn/",
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
    "DHC": "https://fpe.hueuni.edu.vn/",
    "DLS": "https://ulsa2.edu.vn/",
    "HGH": "https://hvph.edu.vn/",
    "TGH": "https://tctt.edu.vn/",
    "TTD": "https://dsu.edu.vn/",
    "SNH": "https://www.tsqcb.edu.vn/",
    "HCB": "https://dhkthc.edu.vn/",
    "HCN": "https://dhkthc.edu.vn/",
    "PBH": "https://phao-binh.edu.vn/",
    "DFA": "https://ufba.edu.vn/",
    "DDV": "https://vnuk.udn.vn/",
    "HVD": "https://hvdt.edu.vn/",
    "LNS": "https://vnuf.edu.vn/",
    "QSP": "https://vnuhcm-cbt.edu.vn/",
    "NLG": "https://hcmuaf.edu.vn/",
    "DTP": "https://laocai.tnu.edu.vn/",
    "DTG": "https://hagiang.tnu.edu.vn/",
    "LBS": "https://www.daihocnguyenhue.edu.vn/",
    "YHT": "https://hmu.edu.vn/",
    "VPH": "https://tdn.edu.vn/",
    "DDG": "https://fpe.udn.vn/?Page=home",
    "XDN": "https://muce.edu.vn/",
    "LNA": "https://vnuf.edu.vn/",
    "NHP": "https://hvnh.edu.vn/",
}

COMMON_SCHOOL_WORDS = {
    "truong", "dai", "hoc", "vien", "khoa", "phan", "hieu", "co", "so",
    "he", "quan", "su", "viet", "nam", "va", "tai", "tp", "thanh", "pho",
}
PARTNER_MARKERS = {
    "sponsor", "partner", "doi tac", "tai tro", "quang cao", "qc", "swiper slide",
    "khach hang", "doanh nghiep", "lien ket", "bgdvadt", "bo giao duc",
    "facebook", "youtube", "zalo", "linkedin", "goertek", "tma binhdinh", "logo vla",
    "bulsan", "strive", "cea saigon", "logo vnpt", "khoavnh", "nghean gov",
    "nxb thong tin", "publisher", "thiet ke logo", "banner", "tuyen sinh",
    "tin tuc", "news", "article", "eventnews", "thumb", "viettel",
    "long van", "iso 9001", "jste", "tap chi", "top 501",
}

# Official files that are more reliable than the corresponding home page.
# These cover sites whose HTML prominently exposes ministry, partner or news
# images before the actual institutional mark.
KNOWN_LOGO_URLS = {
    "NTH": "https://hanoidep.vn/wp-content/uploads/2025/11/FTU_logo_2020.svg_1_-1200x1200.png",
    "NTS": "https://hanoidep.vn/wp-content/uploads/2025/11/FTU_logo_2020.svg_1_-1200x1200.png",
    "ANH": "https://congan.gialai.gov.vn/uploads/about/logo-hoc-vien-annd-c500.jpg",
    "ANS": "https://congan.gialai.gov.vn/uploads/about/logo-dai-hoc-annd.jpg",
    "GTS": "https://icons.duckduckgo.com/ip3/ut.edu.vn.ico",
    "PKH": "https://edus3.leaderbook.com/prod/upload/img/656d80c9104e6700468c5f28-logo-hoc-vien-phong-khong-khong-quan-emxRdzHz.webp",
    "KHA": "https://neu.edu.vn/wp-content/uploads/2026/01/neu_new-1-scaled-180x180.webp",
    "DKH": "https://hup.edu.vn/data/orgs/2/2/1/images/logo-vi.png",
    "CSS": "https://dhcsnd.edu.vn/_next/image?url=%2Flogo_new.png&w=256&q=90",
    "HVN": "https://vnua.edu.vn/Portals/0/logoHVNN.ico?ver=2018-12-25-093425-527",
    "HBT": "https://ajc.edu.vn/SMPT_Publishing_UC/TinTuc/AnhSEO.ashx?u=https%3a%2f%2fajc.edu.vn%2fContent%2fimages%2flogonew.png",
    "QHS": "https://education.vnu.edu.vn/images/uncategorised/logo_goc_08-08-2019__File_d__n_n___n_trong_su___t_.png",
    "QHF": "https://ulis.vnu.edu.vn/files/uploads/2026/03/LOGO-NGUYEN-BAN-TRUONG-DHNN-DHQGHN4-1024x1024.png",
    "BVS": "https://ptit.edu.vn/wp-content/uploads/2024/05/logo-ptit-1.svg",
    "YKV": "https://x.onednn.com/img.thumb/png-180x0-0-74/cdn/vmu/logo-vmu.png",
    "HCH": "https://apag.edu.vn/Content/publishing_home/imgAPAG/logo-apag.png",
    "SPD": "https://dthu.edu.vn/img/logo_icon.png",
    "NHS": "https://fileserver2.hub.edu.vn/IMAGES/2025/01/04/20250104204622hublog.jpg",
    "VKU": "https://vku.udn.vn/wp-content/uploads/2023/08/Logo.svg",
    "DTD": "https://tdu.edu.vn/storage/images/ic-logos/ic-logo-full.png",
    "DVH": "https://vhu.edu.vn/Resources/Images/SubDomain/HomePage/Logo/1Logo_VHU.png",
    "LAH": "https://static.wixstatic.com/media/9d8ed5_50954bfc7e34403eb4f0566751e4b07b~mv2.jpg",
    "SNH": "https://www.tsqcb.edu.vn/assets/images/logo.png",
    "LBS": "https://cdn.thuvienphapluat.vn/uploads/Hoidapphapluat/2026/NNL/0703/nhch1055.jpg",
    "DCV": "http://www.iuv.edu.vn/cms/static/site/sale_cnvinh/template/default/images/logo.png",
    "VHD": "https://viu.edu.vn/media/XrayXMjDbzu62ldU1rHdDH66infa-zGGZjFzt_UWdfMMbnsONPkZLC3vZg_YedLO.jpg",
    "DDG": "https://fpe.udn.vn/Content/Image/logo_fpe.png",
    "DHN": "https://www.nghethuathue.edu.vn/wp-content/uploads/2022/03/cropped-cropped-LOGO-DHNT-270x270.png",
    "DHE": "https://huet.hueuni.edu.vn/wp-content/uploads/2026/10/bb3.png",
    "HDT": "https://knn.hdu.edu.vn/Content/images/hdu1.png",
    "MTS": "https://static.wixstatic.com/media/c0d3eb_ea05cc3035ef42dbb6c313be95659281~mv2.png",
    "NHB": "https://hvnh.edu.vn/medias/hvnh/vi/08.2025/hvnh.admin/album/BAV%20LOGO.png",
    "DLS": "https://ulsa.edu.vn/wp-content/uploads/2023/06/logo-footer.png",
    "DKS": "https://copyshop.vn/wp-content/uploads/2025/02/Logo-truong-dai-hoc-kiem-sat-Ha-Noi.jpg",
    "DHS": "https://tckhgd.dhsphue.edu.vn/public/site/logo_dhsp.png",
    "HTA": "https://cdn.haitrieu.com/wp-content/uploads/2021/11/Logo-Hoc-Vien-Toa-An-Viet-Nam-HVTA.png",
    "HTN": "https://cdn.haitrieu.com/wp-content/uploads/2022/08/logo-hoc-vien-thanh-thieu-nien-viet-nam-vya.png",
    "YQH": "https://edus3.leaderbook.com/prod/upload/img/6566e4eee10b2a0052ef4074-logo-hoc-vien-quan-y-he-quan-su-st85ds7b.webp",
    "QHY": "https://cdnportal.vnu.edu.vn/data/upload/2010/08/14002/image/VNU-UMP-logo.jpg",
    "BPH": "https://edus3.leaderbook.com/prod/upload/img/6566e50de10b2a0052ef4312-logo-hoc-vien-bien-phong-8wNZPhSb.webp",
    "TGH": "https://edus3.leaderbook.com/prod/upload/img/6566e4f2e10b2a0052ef40c5-logo-truong-si-quan-tang-thiet-giap-nzWNtehp.webp",
    "HGH": "https://navigates.vn/wp-content/uploads/2023/10/truong-si-quan-phong-hoa-1.jpg",
    "VPH": "https://edus3.leaderbook.com/prod/upload/img/6566e4ede10b2a0052ef4066-logo-truong-si-quan-ki-thuat-quan-su-he-dan-su-dai-hoc-tran-dai-nghia-ql07BiCN.webp",
    "PBH": "https://cdn.thuvienphapluat.vn/uploads/Hoidapphapluat/2025/NNL/01082025/siquanphaobinh.jpg",
    "HVC": "https://edus3.leaderbook.com/prod/upload/img/6566ea7ce10b2a0052ef528b-logo-hoc-vien-can-bo-tp-hcm-pO69j1Kt.webp",
    "STS": "https://cdn.haitrieu.com/wp-content/uploads/2022/11/Logo-Truong-DH-Su-pham-The-duc-The-thao-TPHCM-635x635.png",
    "HVQ": "https://navigates.vn/wp-content/uploads/2023/05/logo-hoc-vien-quan-ly-giao-duc-1.jpg",
    "DPC": "https://pctu.edu.vn/vnt_upload/weblink/logo.png",
    "DCL": "https://lms.mku.edu.vn/pluginfile.php/1/theme_edumy/footerlogo1/1740739461/Logo_Tr%C6%B0%E1%BB%9Dng_%C4%90%E1%BA%A1i_h%E1%BB%8Dc_C%E1%BB%ADu_Long.svg.png",
    "DPT": "https://edus3.leaderbook.com/prod/upload/img/6566e504e10b2a0052ef4242-logo-dai-hoc-phan-thiet-II53mzB8.webp",
    "UKB": "https://cdn.ketnoibongda.vn/upload/images/team/logo-dai-hoc-kinh-bac-2025-04-01.webp",
    "LDA": "https://copyshop.vn/wp-content/uploads/2023/05/logo-truong-dai-hoc-cong-doan-1024x983.png",
    "LBH": "https://cdn.thuvienphapluat.vn/uploads/Hoidapphapluat/2026/NNL/0703/nhch1055.jpg",
    "DDY": "https://smp.udn.vn/public/uploads/file/giaodientrangchu/logo/logoUD-SMPTOP.png",
    "QHK": "https://sis.vnu.edu.vn/images/VNU-SIS-logo%28vns%29.png",
    "DHC": "https://fpe.hueuni.edu.vn/images/thechat_logo.jpg",
    "DTY": "https://cdn.haitrieu.com/wp-content/uploads/2022/11/Logo-Truong-Dai-hoc-Y-Duoc-Dai-hoc-Thai-Nguyen-635x635.png",
    "DMT": "https://hunre.edu.vn/media/cache/data/banner/LOGO_hunre_1.jpg-cr-1200x630.png",
    "HLU": "https://uhl.edu.vn/FileUploaded/Upload/Images/4d7fdd8b-6bd5-4483-adad-cf3dc94eff4dLOGO%20TIENG%20VIET-02.jpg",
    "DHI": "http://huis.hueuni.edu.vn/logo.png",
    "DHD": "http://huht.hueuni.edu.vn/wp-content/uploads/2021/03/Logo-Transparency-1.png",
    "HCB": "https://congan.gialai.gov.vn/uploads/about/logo-daihoc-kythuat-hau-can-cand.jpg",
    "HCN": "https://congan.gialai.gov.vn/uploads/about/logo-daihoc-kythuat-hau-can-cand.jpg",
    "QHD": "https://cdnportal.vnu.edu.vn/data/0/images/2025/05/08/upload_2/logo-hsb.jpg?dpi=72&w=1920",
    "PCS": "https://congan.gialai.gov.vn/uploads/about/logo-dai-hoc-pccc.jpg",
    "PCH": "https://congan.gialai.gov.vn/uploads/about/logo-dai-hoc-pccc.jpg",
    "DHA": "https://tuyensinh.hul.edu.vn/images/logo2024.png",
    "DKB": "https://elearning.ktkt.edu.vn/pluginfile.php/1/theme_academi/logo/1701695417/betu-logo.png",
    "DQT": "https://qtuupload.s3.ap-southeast-1.amazonaws.com/2025/06/aeoZWqPL-logo-qtu-form-26.png",
    "TDB": "https://gddt.edu.vn/media/0/2023/07/logo-dai-hoc-the-duc-the-thao-bac-ninh.jpg",
    "DTB": "https://tbu.edu.vn/Themes/TH1062/Assets/images/tbu.jpg",
    "NTU": "https://cdn.haitrieu.com/wp-content/uploads/2022/12/Logo-Dai-Hoc-Nguyen-Trai-Text.png",
    "DVP": "https://edus3.leaderbook.com/prod/upload/img/6566e501e10b2a0052ef41f8-logo-dai-hoc-trung-vuong-_zlri26K.webp",
    "DBH": "https://icons.duckduckgo.com/ip3/biu.edu.vn.ico",
    "DHQ": "https://hueuni.edu.vn/portal/vi/templates/logo.png",
    "DVB": "https://tuetech.edu.vn/img/logovb.png",
    "UFA": "https://cdn.haitrieu.com/wp-content/uploads/2022/11/Logo-Truong-Dai-Hoc-Tai-Chinh-Ke-Toan.png",
    "GDU": "https://vieclamsv.giadinh.edu.vn/uploads/logos/573a6301-2aec-457f-b881-fd861f2bef33.png",
    "DBG": "https://edus3.leaderbook.com/prod/upload/img/6566e50ce10b2a0052ef42f9-logo-dai-hoc-nong-lam-bac-giang-rkGlqxJu.webp",
    "TKG": "https://vnkgu.edu.vn/public/images/logo.png",
    "DVD": "https://cdn.haitrieu.com/wp-content/uploads/2021/12/Logo-DH-Van-Hoa-The-Thao-Va-Du-Lich-Thanh-Hoa-TUCST.png",
    "TQU": "https://cdn.haitrieu.com/wp-content/uploads/2022/12/Logo-Dai-Hoc-Tan-Trao.png",
    "DVX": "https://edus3.leaderbook.com/prod/upload/img/6566ea81e10b2a0052ef52ef-logo-dai-hoc-cong-nghe-van-xuan--1eAc8hB.webp",
    "DNV": "https://cdn.haitrieu.com/wp-content/uploads/2022/08/logo-truong-dai-hoc-noi-vu-ha-noi-huha.png",
    "KGH": "https://static.wixstatic.com/media/9d8ed5_3a1809edd15c469fbbee2e164190800d~mv2.jpg",
    "DCH": "https://static.wixstatic.com/media/9d8ed5_c410865cbdac491589560d390bd92628~mv2.jpg",
    "HHK": "https://vau.edu.vn/wp-content/uploads/2026/08/cropped-Logo_VAA-2026-vuong-270x270.png",
    "KSA": "https://ueh.edu.vn/images/logo-ueh-deparment-blue.png",
    "TTN": "https://www.ttn.edu.vn/images/Icon/logo.png",
    "MTU": "https://www.mtu.edu.vn/Resources/Images/logomtu2016SM.png",
    "SKN": "https://nute.edu.vn/uploads/logos/NUTE_LOGO.png",
    "YHB": "https://hmu.edu.vn/img/logo/favicon.png?v=2",
    "YHT": "https://hmu.edu.vn/img/logo/favicon.png?v=2",
    "HSU": "https://copyshop.vn/wp-content/uploads/2022/12/logo-dh-hoa-sen-vn.png",
    "DLA": "https://daihoclongan.edu.vn/templates/dla122020/img/dla/logo.png",
    "MHN": "https://upload.wikimedia.org/wikipedia/commons/9/95/Logo_Tr%C6%B0%E1%BB%9Dng_%C4%90%E1%BA%A1i_h%E1%BB%8Dc_M%E1%BB%9F_H%C3%A0_N%E1%BB%99i.png",
    "KSV": "https://ueh.edu.vn/images/logo-ueh-deparment-blue.png",
    "PKA": "https://aihackathon.phenikaa-uni.edu.vn/logo-phenikaa.png",
    "LCH": "https://static.wixstatic.com/media/9d8ed5_e456305c94f4437a874b9a8fd072ce35~mv2.jpg",
    "YTC": "https://huph.edu.vn/upload/images/logo/logo-huph-2.jpg",
    "LNH": "https://vnuf.edu.vn/wp-content/uploads/2024/01/cropped-logo-footer-2024-270x270.png",
    "LNS": "https://vnuf.edu.vn/wp-content/uploads/2024/01/cropped-logo-footer-2024-270x270.png",
    "DCD": "https://dntu.edu.vn/images/layouts/VnLogo.svg",
    "QSA": "https://edus3.leaderbook.com/prod/upload/img/65938bf94153e400529cf9b2-logo-truong-dai-hoc-an-giang-dhqg-tphcm.png",
    "DTN": "https://tuaf.edu.vn/images/2023/6/30/20230630024430logo-dhnl-jpg.jpg",
    "KTA": "https://navigates.vn/wp-content/uploads/2023/06/dai-hoc-kien-truc-ha-noi.jpg",
    "YDS": "https://ump.edu.vn/uploads/ckeditor/images/LOGO-DHYD-400.jpg",
    "GNT": "https://spnttw.edu.vn/wp-content/themes/main/assets/images/logotruong.jpg",
    "SDU": "https://saodo.edu.vn/uploads/logo_dhsd_2.png",
    "SKV": "http://vuted.edu.vn/Resources/Images/News/-1/2026/8/vutech-logo.jpg",
    "DVL": "https://upload.wikimedia.org/wikipedia/commons/d/d1/Logo_VLU_2022.png",
    "NVH": "https://cdn.haitrieu.com/wp-content/uploads/2022/11/Logo-Hoc-Vien-Am-Nhac-Quoc-Gia-Viet-Nam-VNAM-Blue.png",
    "DPQ": "https://cdn.haitrieu.com/wp-content/uploads/2021/11/Logo-Dai-Hoc-Pham-Van-Dong-PDU.png",
    "THV": "https://navigates.vn/wp-content/uploads/2023/04/Logo_of_Hung_Vuong_University_Phu_Tho_Province-1.jpg",
    "KMA": "https://sdh.actvn.edu.vn/images/logo.png?v=Z3AMegORhUTX5sk7LtIWRtY6cX0q7uO6Cj176wvdyPY",
    "DFA": "https://edus3.leaderbook.com/prod/upload/img/6588e999b715ef004674c59f-logo-dai-hoc-tai-chinh-quan-tri-kinh-doanh.png",
    "FBU": "https://edus3.leaderbook.com/prod/upload/img/6566ea80e10b2a0052ef52de-logo-dai-hoc-tai-chinh-ngan-hang-ha-noi-lxzwPNAJ.webp",
    "DDQ": "https://qldt.ute.udn.vn/images/link/Logo_DUE.jpg",
    "DTS": "https://tnue.edu.vn/Data/Sites/1/logos/8ae6fae9-0e1e-49dc-a2eb-37e09ff35aa7.png",
    "VJU": "https://vju.ac.vn/wp-content/uploads/2024/06/LOGO-600x597.png",
    "QSQ": "https://edus3.leaderbook.com/prod/upload/img/659521a001f46a0052c1b3f1-logo-dai-hoc-quoc-te-dhqg-tphcm.png",
}

# A small number of legacy institutions no longer publish a usable standalone
# mark. Keep a clearly labelled local wordmark instead of borrowing an image
# from a similarly named (but unrelated) organisation.
KNOWN_LOCAL_ASSETS = {
    "DHH": ("DHH.svg", "generated_wordmark_fallback"),
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
        elif tag == "img" and any(values.get(key) for key in ("src", "data-src", "data-lazy-src", "data-original")):
            marker = " ".join(values.get(k, "") for k in ("alt", "title", "class", "id")).lower()
            source = next(
                values[key]
                for key in ("src", "data-src", "data-lazy-src", "data-original")
                if values.get(key)
            )
            self.images.append((marker, source))


def request_bytes(url: str, timeout: int = 12) -> tuple[bytes, str]:
    url = quote(url, safe=":/?=&%#+,;@[]!$'()*")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read(MAX_BYTES + 1), response.headers.get_content_type()
    except (ssl.SSLCertVerificationError, URLError) as error:
        reason = getattr(error, "reason", error)
        if not isinstance(reason, ssl.SSLCertVerificationError):
            raise
        # Several official Vietnamese university sites serve an incomplete
        # certificate chain. Retry only that specific validation failure.
        context = ssl._create_unverified_context()
        with urlopen(request, timeout=timeout, context=context) as response:
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


def _ascii_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _school_tokens(school_name: str) -> set[str]:
    return {
        word
        for word in _ascii_text(school_name).split()
        if len(word) > 2 and word not in COMMON_SCHOOL_WORDS
    }


def candidate_image_urls(
    page_url: str,
    body: bytes,
    school_name: str = "",
    school_code: str = "",
) -> list[str]:
    """Return likely brand assets from an official page, best candidates first.

    The previous crawler accepted favicons before inspecting unlabelled image
    paths.  That made small browser icons look like school logos, and missed
    legitimate assets such as ``/assets/img/logo/logo4.png``.  Prefer explicit
    logo/brand files, then other header assets, then icons only as a final
    fallback.
    """
    parser = PageParser()
    parser.feed(body.decode("utf-8", errors="ignore"))
    ranked: dict[str, int] = {}

    def add(value: str, score: int) -> None:
        absolute = urljoin(page_url, value)
        if urlparse(page_url).scheme == "https" and absolute.startswith("http://"):
            absolute = "https://" + absolute[len("http://"):]
        if urlparse(absolute).scheme not in {"http", "https"}:
            return
        ranked[absolute] = max(score, ranked.get(absolute, -999))

    school_tokens = _school_tokens(school_name)
    for index, (marker, value) in enumerate(parser.images):
        value = value.replace("\\", "/")
        decoded_value = unquote(unquote(value))
        path = urlparse(decoded_value).path
        haystack = _ascii_text(f"{marker} {decoded_value}")
        basename = Path(path).stem.lower()
        basename_ascii = _ascii_text(basename)
        score = max(0, 50 - index)
        is_brand_candidate = False
        if "logo" in haystack or "brand" in haystack:
            score += 100
            is_brand_candidate = True
        if "logo" in haystack:
            score += 800
        if "header" in haystack or "trang chu" in haystack:
            score += 70
            is_brand_candidate = True
        if (
            re.fullmatch(r"(?:(?:header|footer) )?logo(?: (?:image|img|icon|new|vi|vn|en|ph|\d+))*", basename_ascii)
            or (basename_ascii.startswith("logo ") and len(basename_ascii) <= 24)
        ):
            score += 140
            is_brand_candidate = True
        if "footer logo" in haystack:
            score += 100
        overlap = school_tokens.intersection(haystack.split())
        score += 35 * len(overlap)
        if len(overlap) >= min(2, len(school_tokens)) and overlap:
            score += 100
        if school_code and school_code.lower() in haystack.split():
            score += 60
            is_brand_candidate = True
        if any(partner_marker in haystack for partner_marker in PARTNER_MARKERS):
            score -= 1200
        if is_brand_candidate and score > 20:
            add(value, score)

    # Icons are usable if an official site publishes no logo asset, but they
    # must never win over an actual logo image.
    for rel, value in parser.links:
        if "icon" in rel or "apple-touch-icon" in rel:
            add(value, 20)
    for key, value in parser.meta:
        if key in {"og:image", "twitter:image"}:
            score = 10
            if "logo" in _ascii_text(unquote(unquote(urlparse(value).path))):
                score += 800
            add(value, score)
    add("/favicon.ico", 0)
    return [url for url, _ in sorted(ranked.items(), key=lambda item: item[1], reverse=True)]


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


def write_asset(target: Path, body: bytes) -> bool:
    """Write a crawled asset, tolerating short-lived Windows file locks."""
    for attempt in range(3):
        try:
            target.write_bytes(body)
            return True
        except OSError:
            if attempt == 2:
                return False
            time.sleep(0.05)
    return False


def crawl_school(school: dict[str, str], allow_search: bool = True) -> dict[str, str]:
    code, name = school["school_code"], school["school_name"]
    row = {**school, "official_url": "", "source_url": "", "logo_path": "", "alt_text": f"Logo {name}", "status": "not_found"}
    official_url = official_url_for_school(school, allow_search=allow_search)
    if not official_url:
        return row
    row["official_url"] = official_url
    local_asset = KNOWN_LOCAL_ASSETS.get(code)
    if local_asset:
        filename, status = local_asset
        target = ASSET_DIR / filename
        if target.is_file():
            row["source_url"] = official_url
            row["logo_path"] = f"/static/img/universities/{filename}"
            row["status"] = status
            return row
    known_logo_url = KNOWN_LOGO_URLS.get(code)
    if known_logo_url:
        downloaded = download_image(known_logo_url)
        if downloaded:
            body, extension = downloaded
            target = ASSET_DIR / f"{code}.{extension}"
            if not write_asset(target, body):
                return row
            row["source_url"] = known_logo_url
            row["logo_path"] = f"/static/img/universities/{target.name}"
            row["status"] = "downloaded_official_logo"
            return row
    try:
        page_body, _ = request_bytes(official_url)
    except Exception:
        page_body = b""
        row["status"] = "official_site_unreachable"
    for image_url in candidate_image_urls(official_url, page_body, name, code):
        downloaded = download_image(image_url)
        if not downloaded:
            continue
        body, extension = downloaded
        target = ASSET_DIR / f"{code}.{extension}"
        if not write_asset(target, body):
            row["status"] = "asset_write_failed"
            return row
        row["source_url"] = image_url
        row["logo_path"] = f"/static/img/universities/{target.name}"
        row["status"] = (
            "downloaded_official_icon"
            if "favicon" in image_url.lower() or "icon" in urlparse(image_url).path.lower()
            else "downloaded_official_logo"
        )
        return row
    proxy = download_proxy_favicon(official_url)
    if proxy:
        body, extension = proxy
        target = ASSET_DIR / f"{code}.{extension}"
        if not write_asset(target, body):
            row["status"] = "asset_write_failed"
            return row
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
    parser.add_argument(
        "--codes",
        default="",
        help="Comma-separated school codes to refresh while preserving all other metadata rows.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="With --codes, replace an existing row whenever the refreshed crawl found an asset.",
    )
    args = parser.parse_args()
    schools = load_schools()
    requested_codes = {code.strip().upper() for code in args.codes.split(",") if code.strip()}
    if requested_codes:
        schools = [school for school in schools if school["school_code"] in requested_codes]
        unknown_codes = requested_codes - {school["school_code"] for school in schools}
        if unknown_codes:
            raise SystemExit(f"Unknown school codes: {', '.join(sorted(unknown_codes))}")
    if args.max_schools > 0:
        schools = schools[: args.max_schools]
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = ["school_code", "school_name", "official_url", "source_url", "logo_path", "alt_text", "status"]
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(crawl_school, school, not args.no_search): school
            for school in schools
        }
        crawled_rows: dict[str, dict[str, str]] = {}
        for index, future in enumerate(as_completed(futures), start=1):
            row = future.result()
            crawled_rows[row["school_code"]] = row
            print(f"[{index}/{len(schools)}] {row['school_code']} {row['status']}", flush=True)
            if args.delay:
                time.sleep(max(0.0, args.delay))

    if requested_codes and OUTPUT_PATH.exists():
        with OUTPUT_PATH.open(encoding="utf-8-sig", newline="") as file:
            rows_to_write = list(csv.DictReader(file))
        # A refresh must never erase a working logo because a school's site is
        # temporarily unavailable.  Replace an existing row only with an
        # asset of equal or better quality.
        quality = {
            "not_found": 0,
            "official_site_unreachable": 0,
            "logo_not_found": 0,
            "generated_avatar": 1,
            "downloaded_favicon_proxy": 2,
            "downloaded_official_icon": 3,
            "downloaded": 3,
            "downloaded_official_logo": 4,
        }

        def select_refresh(existing: dict[str, str]) -> dict[str, str]:
            refreshed = crawled_rows.get(existing["school_code"])
            if not refreshed or not refreshed.get("logo_path"):
                return existing
            if args.force_refresh:
                return refreshed
            if quality.get(refreshed.get("status", ""), 0) < quality.get(existing.get("status", ""), 0):
                return existing
            return refreshed

        rows_to_write = [select_refresh(row) for row in rows_to_write]
    else:
        rows_to_write = [crawled_rows[school["school_code"]] for school in schools]

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_to_write)


if __name__ == "__main__":
    main()
