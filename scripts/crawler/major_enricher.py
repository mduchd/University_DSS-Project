"""
Major Knowledge Enricher
Enriches university admission records with:
1. Mô tả ngành (Major Description)
2. Chương trình đào tạo (Training Program / Curriculum)
3. Cơ hội nghề nghiệp (Career Opportunities)

Based on the Ministry of Education & Training standard major taxonomy (Circular 09/2022/TT-BGDĐT)
and comprehensive career orientation data.
"""

import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from .config import MAJOR_CATALOG_FILE


class MajorEnricher:
    def __init__(self, catalog_path: Optional[Path] = None):
        self.catalog_path = catalog_path or MAJOR_CATALOG_FILE
        self.catalog: Dict[str, Dict] = {}
        self._load_or_create_catalog()

    def enrich(self, major_code: str, major_name: str) -> Dict[str, str]:
        """
        Enriches a major record with description, training program, and career opportunities.
        """
        clean_code = self._clean_code(major_code)
        clean_name = self._clean_name(major_name)

        # 1. Direct code lookup
        if clean_code and clean_code in self.catalog:
            entry = self.catalog[clean_code]
            return {
                "major_description": entry["description"],
                "curriculum": entry["curriculum"],
                "career_opportunities": entry["career_opportunities"],
                "major_group": entry.get("major_group", ""),
            }

        # 2. Lookup by major name match in catalog
        for code, entry in self.catalog.items():
            entry_name = self._clean_name(entry.get("name", ""))
            if entry_name and (entry_name in clean_name or clean_name in entry_name):
                return {
                    "major_description": entry["description"],
                    "curriculum": entry["curriculum"],
                    "career_opportunities": entry["career_opportunities"],
                    "major_group": entry.get("major_group", ""),
                }

        # 3. Lookup by major group prefix (e.g. 748, 734, 752...)
        prefix = clean_code[:4] if len(clean_code) >= 4 else clean_code[:3]
        if prefix:
            for code, entry in self.catalog.items():
                if code.startswith(prefix):
                    group = entry.get("major_group", "")
                    return {
                        "major_description": f"Ngành đào tạo chuyên sâu thuộc nhóm ngành {group}, trang bị nền tảng lý thuyết và kỹ năng thực hành hiện đại đáp ứng nhu cầu doanh nghiệp.",
                        "curriculum": entry.get("curriculum", "Thời gian đào tạo 4 năm (125-140 tín chỉ) gồm khối kiến thức đại cương, cơ sở ngành và chuyên ngành thực tập doanh nghiệp."),
                        "career_opportunities": entry.get("career_opportunities", "Cơ hội việc làm đa dạng tại các doanh nghiệp trong nước, tập đoàn đa quốc gia và viện nghiên cứu chuyên ngành."),
                        "major_group": group,
                    }

        # 4. Fallback based on name keyword heuristics
        fallback = self._heuristic_fallback(clean_name)
        return fallback

    def _clean_code(self, code: str) -> str:
        """Strips non-digits or trailing letters for standard 7-digit mapping."""
        if not code:
            return ""
        # Extract digits
        digits = re.sub(r"\D", "", code)
        return digits

    def _clean_name(self, name: str) -> str:
        if not name:
            return ""
        # Remove parenthesized notes like (CLC), (Chất lượng cao), (Tiếng Anh)
        cleaned = re.sub(r"\(.*?\)", "", name)
        return cleaned.strip().lower()

    def _heuristic_fallback(self, name: str) -> Dict[str, str]:
        name_lower = name.lower()
        if any(w in name_lower for w in ["kinh tế", "tài chính", "ngân hàng", "kế toán", "quản trị", "marketing"]):
            return {
                "major_description": f"Đào tạo cử nhân {name.title()} có kiến thức vững chắc về kinh tế, thị trường tài chính, kỹ năng quản trị và năng lực giải quyết vấn đề thực tiễn.",
                "curriculum": "Thời gian đào tạo 4 năm (khoảng 130 tín chỉ) gồm kiến thức đại cương kinh tế, kỹ năng số, chuyên môn quản trị - tài chính và đồ án tốt nghiệp.",
                "career_opportunities": "Chuyên viên phân tích, quản lý dự án, kế toán - tài chính, tư vấn giải pháp tại các doanh nghiệp, ngân hàng thương mại và tổ chức kinh tế.",
                "major_group": "Kinh doanh và quản lý",
            }
        elif any(w in name_lower for w in ["công nghệ", "phần mềm", "máy tính", "tin học", "dữ liệu", "trí tuệ nhân tạo"]):
            return {
                "major_description": f"Trang bị nền tảng khoa học máy tính, kỹ thuật lập trình, thuật toán và phát triển ứng dụng công nghệ trong lĩnh vực {name.title()}.",
                "curriculum": "Thời gian đào tạo 4-4.5 năm (135-150 tín chỉ) với trọng tâm thực hành đồ án, kiến trúc hệ thống, an ninh thông tin và thực tập doanh nghiệp công nghệ.",
                "career_opportunities": "Kỹ sư phần mềm, chuyên viên phân tích hệ thống, kỹ sư dữ liệu, quản trị mạng và chuyên viên bảo mật tại các tập đoàn công nghệ toàn cầu.",
                "major_group": "Máy tính và công nghệ thông tin",
            }
        elif any(w in name_lower for w in ["kỹ thuật", "cơ khí", "điện", "điện tử", "tự động"]):
            return {
                "major_description": f"Đào tạo kỹ sư {name.title()} có tư duy thiết kế, vận hành, bảo trì và tích hợp các hệ thống kỹ thuật hiện đại.",
                "curriculum": "Thời gian đào tạo 4.5-5 năm (khoảng 150 tín chỉ) gồm toán - lý kỹ thuật, thí nghiệm chuyên ngành, CAD/CAM/PLC và đồ án kỹ thuật.",
                "career_opportunities": "Kỹ sư thiết kế, kỹ sư vận hành nhà máy, quản lý dự án kỹ thuật, nghiên cứu và phát triển sản phẩm (R&D) tại các tập đoàn sản xuất.",
                "major_group": "Kỹ thuật và công nghệ kỹ thuật",
            }
        elif any(w in name_lower for w in ["ngôn ngữ", "tiếng", "ngoại ngữ"]):
            return {
                "major_description": f"Trang bị năng lực ngoại ngữ bậc cao kết hợp kiến thức sâu rộng về văn hóa, xã hội và kỹ năng biên phiên dịch, thương mại quốc tế.",
                "curriculum": "Thời gian đào tạo 4 năm (130 tín chỉ) gồm 4 kỹ năng ngôn ngữ chuyên sâu, văn hóa - văn học và nghiệp vụ biên phiên dịch/thương mại.",
                "career_opportunities": "Biên dịch viên, phiên dịch viên, chuyên viên đối ngoại, điều phối dự án quốc tế, giảng dạy ngoại ngữ và chuyên viên xuất nhập khẩu.",
                "major_group": "Nhân văn và ngôn ngữ",
            }
        else:
            return {
                "major_description": f"Ngành {name.title()} đào tạo nguồn nhân lực chất lượng cao, nắm vững lý thuyết nền tảng và kỹ năng tác nghiệp chuyên nghiệp theo chuẩn quốc tế.",
                "curriculum": "Thời gian đào tạo 4 năm (120-140 tín chỉ) gồm khối kiến thức đại cương, cơ sở ngành, chuyên sâu và kỳ thực tập nghề nghiệp.",
                "career_opportunities": "Đảm nhiệm các vị trí chuyên môn, quản lý và nghiên cứu tại các cơ quan, tổ chức, doanh nghiệp trong nước và quốc tế.",
                "major_group": "Đào tạo đại học",
            }

    def _load_or_create_catalog(self):
        if self.catalog_path.exists():
            try:
                with open(self.catalog_path, "r", encoding="utf-8") as f:
                    self.catalog = json.load(f)
                return
            except Exception:
                pass

        # Built-in Master Catalog conforming to Circular 09/2022/TT-BGDĐT
        self.catalog = {
            # === KHỐI CÔNG NGHỆ THÔNG TIN & MÁY TÍNH (748xxxx) ===
            "7480201": {
                "name": "Công nghệ thông tin",
                "major_group": "Máy tính và công nghệ thông tin",
                "description": "Đào tạo kiến thức nền tảng và chuyên sâu về thiết kế, phát triển, triển khai và bảo trì các hệ thống phần mềm, mạng máy tính, cơ sở dữ liệu và ứng dụng thông minh.",
                "curriculum": "Thời gian đào tạo 4 năm (135 tín chỉ). Gồm: Lập trình hướng đối tượng, Cấu trúc dữ liệu và giải thuật, Cơ sở dữ liệu, Mạng máy tính, Phát triển ứng dụng Web/Mobile, Điện toán đám mây và Đồ án tốt nghiệp.",
                "career_opportunities": "Kỹ sư phát triển phần mềm (Frontend, Backend, Fullstack), Kỹ sư DevOps, Chuyên viên quản trị cơ sở dữ liệu, Chuyên viên quản trị mạng tại các công ty công nghệ, ngân hàng và doanh nghiệp đa quốc gia.",
            },
            "7480101": {
                "name": "Khoa học máy tính",
                "major_group": "Máy tính và công nghệ thông tin",
                "description": "Nghiên cứu các nguyên lý nền tảng của tính toán, thuật toán phức tạp, cấu trúc dữ liệu, trí tuệ nhân tạo, đồ họa máy tính và xử lý ngôn ngữ tự nhiên.",
                "curriculum": "Thời gian đào tạo 4 năm (135 tín chỉ). Gồm: Toán rời rạc, Lý thuyết tính toán, Học máy (Machine Learning), Xử lý ảnh số, Thị giác máy tính, Xử lý ngôn ngữ tự nhiên và Trí tuệ nhân tạo.",
                "career_opportunities": "Kỹ sư AI/Machine Learning, Nhà khoa học dữ liệu (Data Scientist), Kỹ sư nghiên cứu & phát triển (R&D), Kỹ sư thiết kế thuật toán tối ưu tại các viện nghiên cứu và tập đoàn công nghệ lớn.",
            },
            "7480103": {
                "name": "Kỹ thuật phần mềm",
                "major_group": "Máy tính và công nghệ thông tin",
                "description": "Tập trung vào quy trình kỹ thuật sản xuất phần mềm chuyên nghiệp, quản lý vòng đời dự án phần mềm, kiểm thử và đảm bảo chất lượng phần mềm quy mô lớn.",
                "curriculum": "Thời gian đào tạo 4 năm (132 tín chỉ). Gồm: Công nghệ phần mềm, Kiểm thử phần mềm (QA/QC), Kiến trúc phần mềm, Quản lý dự án Agile/Scrum, An toàn phần mềm và Đồ án capstone.",
                "career_opportunities": "Kỹ sư phần mềm, Quản lý dự án (Project Manager / Scrum Master), Kỹ sư kiểm thử (QA/QC Engineer), Kỹ sư kiến trúc phần mềm (Software Architect).",
            },
            "7480202": {
                "name": "An toàn thông tin",
                "major_group": "Máy tính và công nghệ thông tin",
                "description": "Trang bị kiến thức và kỹ năng bảo vệ hệ thống thông tin, phân tích mã độc, đánh giá an ninh mạng, mật mã học và ứng phó sự cố an ninh số.",
                "curriculum": "Thời gian đào tạo 4 năm (135 tín chỉ). Gồm: Mật mã học, An toàn mạng, Kiểm thử xâm nhập (Penetration Testing), Điều tra số (Digital Forensics), Kỹ thuật dịch ngược mã độc và Quản trị an ninh mạng.",
                "career_opportunities": "Chuyên viên an ninh mạng (SOC Analyst), Kỹ sư bảo mật hệ thống, Chuyên viên kiểm thử xâm nhập (Ethical Hacker), Chuyên viên ứng cứu sự cố bảo mật tại các ngân hàng, tập đoàn viễn thông và cơ quan chính phủ.",
            },
            "7480104": {
                "name": "Hệ thống thông tin",
                "major_group": "Máy tính và công nghệ thông tin",
                "description": "Giao thoa giữa công nghệ thông tin và quản trị kinh doanh, tập trung vào thiết kế, vận hành và khai thác các hệ thống thông tin quản lý doanh nghiệp.",
                "curriculum": "Thời gian đào tạo 4 năm (130 tín chỉ). Gồm: Phân tích & thiết kế hệ thống, Hệ thống hoạch định nguồn lực doanh nghiệp (ERP), Kho dữ liệu (Data Warehouse), Thương mại điện tử và Business Intelligence.",
                "career_opportunities": "Chuyên viên phân tích nghiệp vụ (Business Analyst - BA), Chuyên viên tư vấn triển khai ERP, Chuyên viên quản trị dữ liệu kinh doanh, Quản trị hệ thống thông tin doanh nghiệp.",
            },
            "7480109": {
                "name": "Khoa học dữ liệu",
                "major_group": "Máy tính và công nghệ thông tin",
                "description": "Kết hợp toán thống kê, khoa học máy tính và tri thức chuyên ngành để thu thập, làm sạch, phân tích và trích xuất tri thức từ dữ liệu lớn phục vụ ra quyết định.",
                "curriculum": "Thời gian đào tạo 4 năm (135 tín chỉ). Gồm: Xác suất thống kê ứng dụng, Trực quan hóa dữ liệu, Khai phá dữ liệu (Data Mining), Xử lý dữ liệu lớn (Big Data: Hadoop/Spark), Mô hình hóa dự báo.",
                "career_opportunities": "Data Analyst, Data Scientist, Data Engineer, Chuyên viên phân tích định lượng tại các quỹ đầu tư, tập đoàn bán lẻ, viễn thông và công nghệ tài chính (Fintech).",
            },
            "7480107": {
                "name": "Trí tuệ nhân tạo",
                "major_group": "Máy tính và công nghệ thông tin",
                "description": "Đào tạo chuyên sâu về học máy, học sâu, mạng nơ-ron, nhận dạng mẫu, người máy thông minh và các giải pháp tự động hóa tạo sinh.",
                "curriculum": "Thời gian đào tạo 4 năm (140 tín chỉ). Gồm: Đại số tuyến tính nâng cao, Học sâu (Deep Learning), Mô hình tạo sinh (Generative AI), Robot học nhận thức và Hệ thống tự hành.",
                "career_opportunities": "Kỹ sư AI/ML, Kỹ sư thị giác máy tính, Kỹ sư xử lý ngôn ngữ tự nhiên (NLP), Chuyên gia giải pháp AI doanh nghiệp.",
            },

            # === KHỐI KINH DOANH & QUẢN LÝ (734xxxx) ===
            "7340101": {
                "name": "Quản trị kinh doanh",
                "major_group": "Kinh doanh và quản lý",
                "description": "Trang bị kiến thức tổng hợp về điều hành doanh nghiệp, hoạch định chiến lược, quản trị tài chính, nhân sự, chuỗi cung ứng và phát triển thương hiệu.",
                "curriculum": "Thời gian đào tạo 4 năm (128 tín chỉ). Gồm: Quản trị học, Quản trị chiến lược, Quản trị Marketing, Quản trị nhân lực, Hành vi tổ chức, Đàm phán kinh doanh và Khởi sự doanh nghiệp.",
                "career_opportunities": "Chuyên viên phát triển kinh doanh, Trợ lý ban giám đốc, Quản lý dự án, Chuyên viên nhân sự, Giám đốc điều hành chi nhánh, Nhà sáng lập doanh nghiệp/startup.",
            },
            "7340115": {
                "name": "Marketing",
                "major_group": "Kinh doanh và quản lý",
                "description": "Nghiên cứu hành vi người tiêu dùng, nghiên cứu thị trường, chiến lược định giá, truyền thông thương hiệu và tiếp thị kỹ thuật số hiện đại.",
                "curriculum": "Thời gian đào tạo 4 năm (128 tín chỉ). Gồm: Nghiên cứu thị trường, Digital Marketing, Quản trị thương hiệu, Quan hệ công chúng (PR), Marketing nội dung, Sáng tạo thông điệp quảng cáo.",
                "career_opportunities": "Chuyên viên Marketing (Digital/Content/Trade), Quản lý thương hiệu (Brand Manager), Chuyên viên truyền thông quảng cáo, Account Executive tại các Agency quảng cáo.",
            },
            "7340201": {
                "name": "Tài chính - Ngân hàng",
                "major_group": "Kinh doanh và quản lý",
                "description": "Đào tạo kiến thức chuyên sâu về thị trường tiền tệ, thị trường chứng khoán, quản trị ngân hàng thương mại, định giá tài sản và tài chính doanh nghiệp.",
                "curriculum": "Thời gian đào tạo 4 năm (130 tín chỉ). Gồm: Tài chính doanh nghiệp, Ngân hàng thương mại, Thị trường chứng khoán, Định giá tài sản, Phân tích báo cáo tài chính, Quản trị rủi ro tài chính.",
                "career_opportunities": "Chuyên viên tín dụng ngân hàng, Chuyên viên phân tích đầu tư chứng khoán, Chuyên viên quản lý danh mục đầu tư, Chuyên viên thẩm định giá tại ngân hàng và quỹ đầu tư.",
            },
            "7340301": {
                "name": "Kế toán",
                "major_group": "Kinh doanh và quản lý",
                "description": "Trang bị phương pháp thu thập, xử lý, kiểm tra và cung cấp thông tin tài chính - kế toán theo chuẩn mực kế toán Việt Nam và quốc tế (VAS, IFRS).",
                "curriculum": "Thời gian đào tạo 4 năm (128 tín chỉ). Gồm: Nguyên lý kế toán, Kế toán tài chính, Kế toán quản trị, Thuế và kế toán thuế, Hệ thống thông tin kế toán, Phân tích tài chính.",
                "career_opportunities": "Kế toán viên tổng hợp, Kế toán thuế, Chuyên viên kế toán quản trị, Kế toán trưởng tại các doanh nghiệp, tổ chức tài chính hoặc cơ quan nhà nước.",
            },
            "7340302": {
                "name": "Kiểm toán",
                "major_group": "Kinh doanh và quản lý",
                "description": "Đào tạo quy trình và kỹ năng kiểm tra, xác nhận tính trung thực, hợp lý của báo cáo tài chính và hệ thống kiểm soát nội bộ của tổ chức.",
                "curriculum": "Thời gian đào tạo 4 năm (130 tín chỉ). Gồm: Lý thuyết kiểm toán, Kiểm toán tài chính, Kiểm toán hoạt động, Kiểm toán nội bộ, Gian lận và phòng chống gian lận.",
                "career_opportunities": "Trợ lý kiểm toán, Kiểm toán viên tại các công ty kiểm toán độc lập (Big 4 và các hãng kiểm toán), Chuyên viên kiểm soát nội bộ doanh nghiệp.",
            },
            "7340122": {
                "name": "Thương mại điện tử",
                "major_group": "Kinh doanh và quản lý",
                "description": "Đào tạo kỹ năng vận hành kinh doanh trực tuyến, quản lý sàn thương mại điện tử, thanh toán điện tử, tiếp thị số và logistics trong nền kinh tế số.",
                "curriculum": "Thời gian đào tạo 4 năm (130 tín chỉ). Gồm: Vận hành sàn TMĐT, Thanh toán điện tử, Digital Marketing cho TMĐT, Quản trị trải nghiệm khách hàng số, Pháp luật trong TMĐT.",
                "career_opportunities": "Chuyên viên vận hành sàn TMĐT (Shopee, Lazada, TikTok Shop), Quản lý kênh bán hàng trực tuyến, Chuyên viên phát triển kinh doanh số tại các tập đoàn bán lẻ.",
            },
            "7340120": {
                "name": "Kinh doanh quốc tế",
                "major_group": "Kinh doanh và quản lý",
                "description": "Trang bị kiến thức về thương mại toàn cầu, đầu tư quốc tế, đàm phán hợp đồng ngoại thương và quản trị chuỗi cung ứng đa quốc gia.",
                "curriculum": "Thời gian đào tạo 4 năm (130 tín chỉ). Gồm: Thương mại quốc tế, Thanh toán quốc tế, Giao nhận vận tải quốc tế, Đàm phán kinh doanh quốc tế, Luật thương mại quốc tế.",
                "career_opportunities": "Chuyên viên xuất nhập khẩu, Chuyên viên thanh toán quốc tế, Quản lý mua hàng quốc tế (Procurement), Chuyên viên phát triển thị trường nước ngoài.",
            },
            "7340116": {
                "name": "Bất động sản",
                "major_group": "Kinh doanh và quản lý",
                "description": "Trang bị kiến thức pháp lý đất đai, định giá bất động sản, quản lý dự án phát triển và môi giới, đầu tư bất động sản.",
                "curriculum": "Thời gian đào tạo 4 năm (126 tín chỉ). Gồm: Luật đất đai & nhà ở, Định giá bất động sản, Quản trị kinh doanh bất động sản, Phân tích dự án đầu tư BĐS, Marketing BĐS.",
                "career_opportunities": "Chuyên viên thẩm định giá BĐS, Chuyên viên phát triển dự án tại các tập đoàn BĐS, Chuyên viên quản lý vận hành tòa nhà, Môi giới và tư vấn đầu tư.",
            },
            "7340204": {
                "name": "Bảo hiểm",
                "major_group": "Kinh doanh và quản lý",
                "description": "Đào tạo chuyên sâu về quản trị rủi ro tài chính, định phí bảo hiểm nhân thọ và phi nhân thọ, thẩm định bồi thường và pháp luật kinh doanh bảo hiểm.",
                "curriculum": "Thời gian đào tạo 4 năm (128 tín chỉ). Gồm: Nguyên lý bảo hiểm, Bảo hiểm thương mại, Bảo hiểm xã hội, Định phí bảo hiểm (Actuary), Thẩm định bồi thường, Pháp luật bảo hiểm.",
                "career_opportunities": "Chuyên viên định phí bảo hiểm (Actuary), Chuyên viên thẩm định hồ sơ bảo hiểm, Chuyên viên giám định bồi thường tại các tổng công ty bảo hiểm và môi giới bảo hiểm.",
            },
            "7510605": {
                "name": "Logistics và Quản lý chuỗi cung ứng",
                "major_group": "Sản xuất và chế biến",
                "description": "Tập trung vào tối ưu hóa dòng chảy hàng hóa, nguyên vật liệu, thông tin từ khâu thu mua, vận tải, lưu kho đến phân phối tới tay người tiêu dùng cuối cùng.",
                "curriculum": "Thời gian đào tạo 4 năm (130 tín chỉ). Gồm: Quản trị kho bãi, Quản trị vận tải đa phương thức, Quản trị chuỗi cung ứng toàn cầu, Thu mua & quản lý tồn kho, Công nghệ thông tin trong Logistics.",
                "career_opportunities": "Chuyên viên Logistics, Chuyên viên điều phối vận tải, Quản lý kho hàng thông minh, Chuyên viên hoạch định chuỗi cung ứng tại các công ty 3PL/4PL và tập đoàn đa quốc gia.",
            },

            # === KHỐI KỸ THUẬT & CÔNG NGHỆ (752xxxx / 751xxxx) ===
            "7520216": {
                "name": "Kỹ thuật Điều khiển và Tự động hóa",
                "major_group": "Kỹ thuật",
                "description": "Thiết kế, chế tạo và vận hành các hệ thống tự động hóa công nghiệp, robot, hệ thống điều khiển thông minh và dây chuyền sản xuất số hóa.",
                "curriculum": "Thời gian đào tạo 4.5 năm (150 tín chỉ). Gồm: Lý thuyết điều khiển tự động, Cảm biến & đo lường, Vi điều khiển & PLC, Robot công nghiệp, SCADA/DCS và Thị giác máy tính công nghiệp.",
                "career_opportunities": "Kỹ sư tự động hóa, Kỹ sư thiết kế hệ thống PLC/SCADA, Kỹ sư Robot tại các nhà máy sản xuất tự động, tập đoàn công nghiệp chế tạo (Samsung, VinFast, LG...).",
            },
            "7520207": {
                "name": "Kỹ thuật Điện tử - Viễn thông",
                "major_group": "Kỹ thuật",
                "description": "Nghiên cứu và phát triển phần cứng điện tử, thiết kế vi mạch bán dẫn, hệ thống thông tin không dây (5G/6G), xử lý tín hiệu và mạng viễn thông thế hệ mới.",
                "curriculum": "Thời gian đào tạo 4.5 năm (150 tín chỉ). Gồm: Kỹ thuật mạch điện tử, Thiết kế vi mạch (VLSI/FPGA), Hệ thống viễn thông, Xử lý tín hiệu số (DSP), Ăng ten & truyền sóng, Mạng 5G.",
                "career_opportunities": "Kỹ sư thiết kế vi mạch bán dẫn, Kỹ sư phần cứng điện tử, Kỹ sư mạng viễn thông, Chuyên viên tối ưu mạng tại các tập đoàn công nghệ và bán dẫn (Viettel, Intel, Synopsys...).",
            },
            "7520114": {
                "name": "Kỹ thuật Cơ điện tử",
                "major_group": "Kỹ thuật",
                "description": "Tích hợp đa ngành giữa cơ khí chính xác, điện tử thông minh và phần mềm điều khiển để tạo ra các sản phẩm thông minh và robot hiện đại.",
                "curriculum": "Thời gian đào tạo 4.5 năm (150 tín chỉ). Gồm: Cơ học máy, Điện tử công suất, Kỹ thuật vi điều khiển, Hệ thống nhúng, Thiết kế hệ thống cơ điện tử và Điều khiển Robot.",
                "career_opportunities": "Kỹ sư cơ điện tử, Kỹ sư thiết kế hệ thống nhúng (Embedded Engineer), Kỹ sư vận hành dây chuyền tự động hóa, Chuyên viên R&D sản phẩm thông minh.",
            },
            "7520130": {
                "name": "Kỹ thuật Ô tô",
                "major_group": "Kỹ thuật",
                "description": "Đào tạo kiến thức chuyên sâu về kết cấu, nguyên lý làm việc, thiết kế, sản xuất và công nghệ ô tô hiện đại, bao gồm xe điện và xe tự hành.",
                "curriculum": "Thời gian đào tạo 4.5 năm (150 tín chỉ). Gồm: Động cơ đốt trong, Khung gầm ô tô, Hệ thống điện - điện tử ô tô, Công nghệ xe điện và pin, Chẩn đoán kỹ thuật ô tô.",
                "career_opportunities": "Kỹ sư thiết kế ô tô, Kỹ sư phát triển phần mềm ô tô (Automotive Embedded), Kỹ sư kiểm tra chất lượng (QA/QC ô tô), Cố vấn dịch vụ tại các hãng xe hàng đầu.",
            },

            # === KHỐI NGÔN NGỮ & NHÂN VĂN (722xxxx) ===
            "7220201": {
                "name": "Ngôn ngữ Anh",
                "major_group": "Nhân văn",
                "description": "Trang bị năng lực tiếng Anh đạt chuẩn quốc tế, kiến thức về văn hóa - xã hội các nước nói tiếng Anh và kỹ năng nghiệp vụ sư phạm, biên phiên dịch, thương mại.",
                "curriculum": "Thời gian đào tạo 4 năm (130 tín chỉ). Gồm: Ngữ âm - Âm vị học, Cú pháp học, Lý thuyết dịch thuật, Biên dịch nâng cao, Phiên dịch hội thảo, Tiếng Anh thương mại.",
                "career_opportunities": "Biên phiên dịch viên, Chuyên viên truyền thông quốc tế, Chuyên viên quan hệ công chúng, Giảng viên tiếng Anh, Chuyên viên điều phối tại các tổ chức phi chính phủ (NGOs).",
            },

            # === KHỐI LUẬT (738xxxx) ===
            "7380101": {
                "name": "Luật",
                "major_group": "Pháp luật",
                "description": "Đào tạo hệ thống kiến thức pháp luật toàn diện về luật hiến pháp, hành chính, dân sự, hình sự, tố tụng và kỹ năng tư vấn pháp lý.",
                "curriculum": "Thời gian đào tạo 4 năm (128 tín chỉ). Gồm: Lý luận nhà nước và pháp luật, Luật Dân sự, Luật Hình sự, Luật Tố tụng dân sự, Luật Tố tụng hình sự, Kỹ năng hành nghề luật.",
                "career_opportunities": "Luật sư, Thẩm phán, Kiểm sát viên, Công chứng viên, Chuyên viên pháp lý (Legal Officer) tại các doanh nghiệp và cơ quan nhà nước.",
            },
            "7380107": {
                "name": "Luật kinh tế",
                "major_group": "Pháp luật",
                "description": "Tập trung vào khung pháp lý điều chỉnh hoạt động kinh doanh, thương mại, đầu tư, cạnh tranh và giải quyết tranh chấp thương mại quốc tế.",
                "curriculum": "Thời gian đào tạo 4 năm (128 tín chỉ). Gồm: Luật Doanh nghiệp, Luật Thương mại, Luật Đầu tư, Luật Cạnh tranh, Pháp luật về hợp đồng thương mại, Trọng tài thương mại.",
                "career_opportunities": "Chuyên viên pháp chế doanh nghiệp (In-house Counsel), Luật sư tư vấn đầu tư, Trọng tài viên, Chuyên viên tư vấn M&A tại các công ty luật và tập đoàn kinh tế.",
            },

            # === KHỐI Y - DƯỢC (772xxxx) ===
            "7720101": {
                "name": "Y khoa",
                "major_group": "Sức khỏe",
                "description": "Đào tạo bác sĩ đa khoa có y đức vững vàng, kiến thức y học toàn diện và kỹ năng lâm sàng khám chữa bệnh cho cộng đồng.",
                "curriculum": "Thời gian đào tạo 6 năm (khoảng 200 tín chỉ). Gồm: Giải phẫu học, Sinh lý học, Bệnh học nội - ngoại - sản - nhi, Dược lý học, Thực hành lâm sàng tại bệnh viện.",
                "career_opportunities": "Bác sĩ điều trị tại các bệnh viện công lập và tư nhân, Bác sĩ gia đình, Giảng viên tại các trường đại học y dược, Nghiên cứu viên y học lâm sàng.",
            },
            "7720201": {
                "name": "Dược học",
                "major_group": "Sức khỏe",
                "description": "Trang bị kiến thức khoa học về thuốc, bào chế dược phẩm, dược lâm sàng, kiểm nghiệm thuốc và quản trị kinh doanh dược phẩm.",
                "curriculum": "Thời gian đào tạo 5 năm (khoảng 160 tín chỉ). Gồm: Hóa dược, Dược liệu, Bào chế và sinh dược học, Dược lý học, Dược lâm sàng, Quản lý và kinh tế dược.",
                "career_opportunities": "Dược sĩ lâm sàng tại bệnh viện, Kỹ sư nghiên cứu bào chế thuốc (R&D Dược), Chuyên viên kiểm nghiệm thuốc, Quản lý sản xuất tại nhà máy dược phẩm chuẩn GMP.",
            },
        }

        # Save to master catalog file
        try:
            self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.catalog_path, "w", encoding="utf-8") as f:
                json.dump(self.catalog, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Warning: Could not save default catalog: {e}")
