# 1. kích hoạt ai gợi ý & dự đoán (main endpoint)
**endpoint:** `post /api/recommend`

### request body (đầu vào)
```json
{
  "scores": {
    "toan": 8.0, 
    "nguvan": 7.5, 
    "ngoaingu": 8.2
  },
  "combination": "d01",
  "interest": "công nghệ thông tin",
  "region": "hồ chí minh",
  "priorities": {
    "admission": 5,
    "interest": 4,
    "job_market": 4,
    "salary": 3,
    "location": 2
  }
}
{
  "status": "success",
  "data": {
    "ranking": [], 
    "criteria_weights": {}, 
    "prediction": {}, 
    "shap_explanations": [], 
    "career_context": [], 
    "advice": "Chuỗi tư vấn sinh ra từ LLM...", 
    "what_if": {}
  },
  "errors": null
}
{
  "status": "error",
  "data": null,
  "errors": [
    {"field": "scores.toan", "message": "Điểm không hợp lệ (vượt quá 10)"}
  ]
}