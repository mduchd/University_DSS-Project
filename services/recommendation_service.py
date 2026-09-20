import logging
from services.data_repository import data_repo

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

class RecommendationEngine:
    def __init__(self):
        # Lấy dữ liệu đã nạp sẵn trên RAM từ Phase 2
        self.exam_data = data_repo.get_exam_data()
        self.master_data = data_repo.get_master_data()

    def process_recommendation(self, user_payload):
        """
        Nhận payload từ người dùng, gọi các module AI và trả về kết quả chuẩn.
        """
        logging.info(f"Đang xử lý hồ sơ ưu tiên khối {user_payload.get('combination')} - {user_payload.get('interest')}")
        
        # ---------------------------------------------------------
        # TÍCH HỢP MÔ HÌNH (Giai đoạn này dùng Mock chờ team ráp code)
        # ---------------------------------------------------------
        
        # 1. Gọi module ML (Người 2)
        mock_prediction = {"chance_of_admission": 0.85, "predicted_score": 26.5}
        mock_shap = [
            {"feature": "toan", "impact": "+0.5"}, 
            {"feature": "nguvan", "impact": "-0.2"}
        ]
        
        # 2. Gọi module AHP/TOPSIS (Người 4, 5)
        mock_weights = {"admission": 0.3, "interest": 0.3, "job_market": 0.4}
        mock_ranking = [
            {
                "ma_truong": "BKA",
                "ten_truong": "Đại học Bách khoa Hà Nội",
                "match_score": 92.5
            },
            {
                "ma_truong": "QGH",
                "ten_truong": "ĐHQG Hà Nội",
                "match_score": 88.0
            }
        ]
        
        # 3. Gọi module RAG/LLM (Người 1)
        mock_career_context = ["Nhu cầu nhân lực ngành này dự kiến tăng 15% trong 3 năm tới."]
        mock_advice = "Điểm Toán và Ngoại ngữ của bạn rất lợi thế, nên đặt BKA ở nguyện vọng 1."

        # ---------------------------------------------------------
        # ĐÓNG GÓI JSON RESPONSE 
        # ---------------------------------------------------------
        response = {
            "ranking": mock_ranking,
            "criteria_weights": mock_weights,
            "prediction": mock_prediction,
            "shap_explanations": mock_shap,
            "career_context": mock_career_context,
            "advice": mock_advice,
            "what_if": {} 
        }
        
        return response

# Khởi tạo instance toàn cục
recommendation_engine = RecommendationEngine()