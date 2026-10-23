import jwt
import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text
from services.data_repository import get_db_connection
import os

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "chuoi_bao_mat_cua_nhom_dss")

def register_user(username, password):
    conn = get_db_connection()
    if not conn: return {"error": "Lỗi kết nối CSDL"}, 500
    
    try:
        # Kiểm tra user tồn tại
        result = conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username}).fetchone()
        if result: return {"error": "Tài khoản đã tồn tại"}, 400
        
        # Mã hóa mật khẩu và lưu
        hashed_pw = generate_password_hash(password)
        conn.execute(text("INSERT INTO users (username, password_hash) VALUES (:u, :p)"), 
                     {"u": username, "p": hashed_pw})
        conn.commit()
        return {"message": "Đăng ký thành công"}, 201
    finally:
        conn.close()

def login_user(username, password):
    conn = get_db_connection()
    if not conn: return {"error": "Lỗi kết nối CSDL"}, 500
    
    try:
        user = conn.execute(text("SELECT id, password_hash FROM users WHERE username = :u"), {"u": username}).fetchone()
        if not user or not check_password_hash(user[1], password):
            return {"error": "Sai tài khoản hoặc mật khẩu"}, 401
        
        # Tạo JWT Token
        token = jwt.encode({
            "user_id": user[0],
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7) # Token sống 7 ngày
        }, SECRET_KEY, algorithm="HS256")
        
        return {"token": token, "message": "Đăng nhập thành công"}, 200
    finally:
        conn.close()