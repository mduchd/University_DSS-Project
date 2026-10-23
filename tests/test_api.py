import unittest
import json
from app import app

class TestDSSAPI(unittest.TestCase):
    def setUp(self):
        # Khởi tạo client test giả lập của Flask
        self.client = app.test_client()
        self.client.testing = True

    def test_health_check(self):
        """Test API Health Check xem server có đang chạy không"""
        response = self.client.get('/api/health')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['data']['data_cached'])

    def test_recommend_success(self):
        """Test gửi payload chuẩn xem có trả về kết quả 200 OK không"""
        valid_payload = {
            "scores": {"toan": 8.0, "nguvan": 7.5, "ngoaingu": 8.2},
            "combination": "D01",
            "interest": "Công nghệ thông tin",
            "region": "Hồ Chí Minh",
            "priorities": {
                "admission": 5, "interest": 4, "job_market": 4,
                "salary": 3, "location": 2
            }
        }
        response = self.client.post(
            '/api/recommend',
            data=json.dumps(valid_payload),
            content_type='application/json'
        )
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'success')
        self.assertIn('ranking', data['data']) # Kiểm tra xem có field ranking theo quy ước team không

    def test_recommend_validation_error(self):
        """Test cố tình gửi điểm Toán = 11 xem hệ thống có bắt lỗi 400 không"""
        invalid_payload = {
            "scores": {"toan": 11.0, "nguvan": 7.5}, # Lỗi điểm > 10
            "combination": "D01",
            "priorities": {"admission": -1} # Lỗi số âm
        }
        response = self.client.post(
            '/api/recommend',
            data=json.dumps(invalid_payload),
            content_type='application/json'
        )
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 400)
        self.assertEqual(data['status'], 'error')
        # Phải bắt được đúng 2 lỗi
        self.assertEqual(len(data['errors']), 2) 

if __name__ == '__main__':
    unittest.main()