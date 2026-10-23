from sqlalchemy import text
from services.data_repository import get_db_connection

def create_user_table():
    conn = get_db_connection()
    if conn:
        with conn.begin():
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
        print("✅ Đã tạo bảng users thành công!")
        conn.close()

if __name__ == "__main__":
    create_user_table()