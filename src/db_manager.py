import os
import psycopg2
from qdrant_client import QdrantClient
from qdrant_client.http import models
from dotenv import load_dotenv

# Load configuration from system.env
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "system.env"))

class DatabaseManager:
    def __init__(self):
        # Postgres Config
        self.pg_user = os.getenv("POSTGRES_USER")
        self.pg_password = os.getenv("POSTGRES_PASSWORD")
        self.pg_db = os.getenv("POSTGRES_DB")
        self.pg_host = os.getenv("POSTGRES_HOST", "localhost")
        self.pg_port = os.getenv("POSTGRES_PORT", "5432")

        # Qdrant Config
        self.qd_host = os.getenv("QDRANT_HOST", "localhost")
        self.qd_port = int(os.getenv("QDRANT_PORT", "6333"))
        self.collection_name = os.getenv("QDRANT_COLLECTION_NAME", "user_faces")
        self.vector_size = int(os.getenv("FACE_VECTOR_SIZE", "512"))

        self.pg_conn = None
        self.qdrant_client = None

    def ensure_pg_connection(self):
        """Kiểm tra kết nối PG còn sống không, nếu không thì reconnect."""
        try:
            if self.pg_conn:
                self.pg_conn.cursor().execute('SELECT 1')
                return True
        except Exception:
            self.pg_conn = None
        return self.connect_postgres()

    def ensure_qdrant_connection(self):
        """Kiểm tra kết nối Qdrant còn sống không, nếu không thì reconnect."""
        try:
            if self.qdrant_client:
                self.qdrant_client.get_collections()
                return True
        except Exception:
            self.qdrant_client = None
        return self.connect_qdrant()

    def connect_postgres(self):
        try:
            self.pg_conn = psycopg2.connect(
                dbname=self.pg_db,
                user=self.pg_user,
                password=self.pg_password,
                host=self.pg_host,
                port=self.pg_port,
                connect_timeout=3
            )
            return True
        except Exception as e:
            try:
                log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "debug_log.txt")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[FATAL] DB Connection Error: {e}\n")
            except: pass
            print(f"PostgreSQL Connection Error: {e}")
            return False

    def connect_qdrant(self):
        try:
            self.qdrant_client = QdrantClient(host=self.qd_host, port=self.qd_port, timeout=3)
            self.qdrant_client.get_collections()
            print("--- Connected to Qdrant ---")
            return True
        except Exception as e:
            print(f"Qdrant Connection Error: {e}")
            return False

    def init_db(self):
        """Khởi tạo các cột mở rộng nếu chưa có (Dành cho việc nâng cấp hệ thống mà không mất dữ liệu cũ)."""
        if self.ensure_pg_connection():
            try:
                cur = self.pg_conn.cursor()
                # 🟢 TỰ ĐỘNG NÂNG CẤP BẢNG USERS
                cur.execute("ALTER TABLE parking_users ADD COLUMN IF NOT EXISTS face_url TEXT;")
                cur.execute("ALTER TABLE parking_users ADD COLUMN IF NOT EXISTS face_public_id VARCHAR(255);")
                
                # 🟢 TỰ ĐỘNG NÂNG CẤP BẢNG LOGS
                cur.execute("ALTER TABLE parking_logs ADD COLUMN IF NOT EXISTS face_url TEXT;")
                cur.execute("ALTER TABLE parking_logs ADD COLUMN IF NOT EXISTS plate_url TEXT;")
                cur.execute("ALTER TABLE parking_logs ADD COLUMN IF NOT EXISTS face_public_id VARCHAR(255);")
                cur.execute("ALTER TABLE parking_logs ADD COLUMN IF NOT EXISTS plate_public_id VARCHAR(255);")
                cur.execute("ALTER TABLE parking_logs ADD COLUMN IF NOT EXISTS parking_fee INTEGER DEFAULT 0;")
                
                # 🟢 THÊM DÒNG NÀY ĐỂ LƯU PHÍ THÁNG CỦA HỘ GIA ĐÌNH
                cur.execute("ALTER TABLE families ADD COLUMN IF NOT EXISTS monthly_fee INTEGER DEFAULT 0;")
                
                self.pg_conn.commit()
                cur.close()
                print("--- Database Schema Verified & Up-to-date ---")
            except Exception as e:
                print(f"Lỗi khi kiểm tra Schema: {e}")
                self.pg_conn.rollback()
        
        self.ensure_qdrant_connection()

    def log_event(self, session_id, user_id, plate_detected, similarity, action_type, status, face_url=None, plate_url=None, face_public_id=None, plate_public_id=None, parking_fee=0):
        """Ghi nhật ký vào SQL kèm theo Tiền phí gửi xe."""
        if not self.ensure_pg_connection(): return
        try:
            db_id = None
            if user_id:
                try: db_id = int(user_id)
                except: pass

            cur = self.pg_conn.cursor()
            cur.execute(
                """INSERT INTO parking_logs 
                   (session_id, user_id, plate_detected, face_similarity, action_type, status, face_url, plate_url, face_public_id, plate_public_id, parking_fee) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (session_id, db_id, plate_detected, float(similarity) if similarity is not None else 0.0, 
                 action_type, status, face_url, plate_url, face_public_id, plate_public_id, parking_fee)
            )
            self.pg_conn.commit()
            cur.close()
        except Exception as e:
            print(f"SQL Log Error: {e}")
            if self.pg_conn: self.pg_conn.rollback()
            raise Exception(f"Database Error: {e}")

    def get_user_id_by_face(self, face_id):
        """Lấy user_id (Số) từ face_id (Chuỗi) trong SQL."""
        if not self.ensure_pg_connection(): return None
        try:
            cur = self.pg_conn.cursor()
            cur.execute("SELECT user_id FROM parking_users WHERE face_id = %s", (str(face_id),))
            res = cur.fetchone()
            cur.close()
            return res[0] if res else None
        except: return None

    def register_user(self, face_id, plate_number, full_name, vector):
        """Đăng ký cư dân vào cả SQL và Qdrant."""
        if not self.ensure_pg_connection() or not self.ensure_qdrant_connection(): return None
        try:
            # 1. SQL
            cur = self.pg_conn.cursor()
            cur.execute(
                "INSERT INTO parking_users (face_id, plate_number, full_name) VALUES (%s, %s, %s) RETURNING user_id",
                (face_id, plate_number, full_name)
            )
            user_id = cur.fetchone()[0]
            self.pg_conn.commit()
            cur.close()

            # 2. Qdrant
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=[models.PointStruct(id=user_id, vector=vector, payload={"name": full_name, "plate": plate_number})]
            )
            return user_id
        except Exception as e:
            print(f"Registration Error: {e}")
            if self.pg_conn: self.pg_conn.rollback()
            return None

    def register_resident(self, room_number, face_id, full_name, vector, face_url=None, face_public_id=None):
        """
        Đăng ký Khuôn mặt cho Cư Dân. 
        LƯU Ý: Không lưu biển số vào Qdrant, chỉ lưu tên và role.
        """
        if not self.ensure_pg_connection() or not self.ensure_qdrant_connection(): return None
        try:
            cur = self.pg_conn.cursor()
            
            # 1. Tìm ID hộ gia đình dựa trên Số phòng
            cur.execute("SELECT family_id FROM families WHERE room_number = %s", (room_number,))
            fam_res = cur.fetchone()
            if not fam_res:
                print("Lỗi: Không tìm thấy số phòng này!")
                return None
            family_id = fam_res[0]

            # 2. Lưu vào SQL (Bổ sung face_url và face_public_id)
            cur.execute(
                "INSERT INTO parking_users (face_id, full_name, family_id, role, face_url, face_public_id) VALUES (%s, %s, %s, 'resident', %s, %s) RETURNING user_id",
                (face_id, full_name, family_id, face_url, face_public_id)
            )
            user_id = cur.fetchone()[0]
            self.pg_conn.commit()
            cur.close()

            # 3. Lưu vào Qdrant (PAYLOAD SẠCH SẼ - KHÔNG CÓ BIỂN SỐ)
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=[models.PointStruct(
                    id=user_id, 
                    vector=vector, 
                    payload={
                        "name": full_name, 
                        "role": "resident", 
                        "family_id": family_id
                    }
                )]
            )
            return user_id
        except Exception as e:
            print(f"Lỗi đăng ký Cư dân: {e}")
            if self.pg_conn: self.pg_conn.rollback()
            return None

    def search_face(self, vector, threshold=0.35):
        if not self.ensure_qdrant_connection(): return None
        try:
            hits = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                limit=1,
                score_threshold=threshold
            )
            return hits[0] if hits else None
        except: return None

    def search_face_extended(self, vector, yellow_threshold=0.60):
        """
        Tìm kiếm khuôn mặt với ngưỡng thấp hơn để phát hiện VÙNG VÀNG.
        Trả về (hit, zone) trong đó zone là 'green', 'yellow', hoặc 'red'.
        """
        if not self.ensure_qdrant_connection(): return None, 'red'
        try:
            GREEN_THRESHOLD = float(os.getenv("FACE_SIMILARITY_THRESHOLD", 0.75))
            hits = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                limit=1,
                score_threshold=yellow_threshold  # Tìm kiếm từ ngưỡng thấp hơn
            )
            if not hits:
                return None, 'red'
            hit = hits[0]
            if hit.score >= GREEN_THRESHOLD:
                return hit, 'green'   # Vùng xanh: Tự động cho qua
            else:
                return hit, 'yellow'  # Vùng vàng: Yêu cầu bảo vệ xác nhận
        except: return None, 'red'

    def get_last_action(self, user_id):
        if not self.ensure_pg_connection() or user_id is None: return "CHECK_OUT"
        try:
            cur = self.pg_conn.cursor()
            cur.execute("SELECT action_type FROM parking_logs WHERE user_id = %s ORDER BY timestamp DESC LIMIT 1", (user_id,))
            res = cur.fetchone()
            cur.close()
            return res[0] if res else "CHECK_OUT"
        except: return "CHECK_OUT"

    def get_family_by_plate(self, plate_number):
        """
        Kiểm tra biển số có thuộc hộ gia đình nào không.
        Chuẩn hóa biển số: bỏ TẤT CẢ ký tự không phải chữ/số trước khi so sánh.
        VD: "59-S2 165.55" → "59S216555" khớp với "59S216555" trong DB.
        Trả về family_id nếu có, None nếu xe chưa đăng ký.
        """
        if not self.ensure_pg_connection() or not plate_number: return None
        try:
            cur = self.pg_conn.cursor()
            cur.execute(
                """SELECT family_id FROM family_vehicles 
                   WHERE REGEXP_REPLACE(UPPER(plate_number), '[^A-Z0-9]', '', 'g')
                       = REGEXP_REPLACE(UPPER(%s), '[^A-Z0-9]', '', 'g')
                   LIMIT 1""",
                (plate_number.strip(),)
            )
            res = cur.fetchone()
            cur.close()
            return res[0] if res else None
        except Exception as e:
            print(f"Lỗi get_family_by_plate: {e}")
            return None

    def get_plate_last_action(self, plate_number):
        """Lấy trạng thái cuối cùng của biển số."""
        if not self.ensure_pg_connection() or not plate_number: return "CHECK_OUT"
        try:
            cur = self.pg_conn.cursor()
            cur.execute("""
                SELECT action_type 
                FROM parking_logs 
                WHERE plate_detected = %s AND status = 'SUCCESS'
                ORDER BY timestamp DESC LIMIT 1
            """, (plate_number,))
            res = cur.fetchone()
            cur.close()
            return res[0] if res else "CHECK_OUT"
        except: return "CHECK_OUT"

    def get_user_by_id(self, user_id):
        """Lấy thông tin chủ xe ban đầu từ SQL dựa trên ID của AI."""
        if not self.ensure_pg_connection() or not user_id: return None
        try:
            cur = self.pg_conn.cursor()
            cur.execute("SELECT full_name, plate_number FROM parking_users WHERE user_id = %s", (int(user_id),))
            res = cur.fetchone()
            cur.close()
            return {"name": res[0], "plate": res[1]} if res else None
        except: return None

    def update_user_plate(self, user_id, new_plate):
        """Cập nhật biển số mới nhất cho khách quen khi họ đổi xe đi vào bãi."""
        if not self.ensure_pg_connection() or not user_id: return False
        try:
            cur = self.pg_conn.cursor()
            cur.execute("UPDATE parking_users SET plate_number = %s WHERE user_id = %s", (new_plate, int(user_id)))
            self.pg_conn.commit()
            
            # Đồng bộ lại Payload sang Qdrant để đối soát nhất quán
            user_info = self.get_user_by_id(user_id)
            if self.ensure_qdrant_connection() and user_info:
                self.qdrant_client.set_payload(
                    collection_name=self.collection_name,
                    payload={"plate": new_plate},
                    points=[int(user_id)]
                )
            cur.close()
            return True
        except Exception as e:
            print(f"Lỗi cập nhật biển số: {e}")
            if self.pg_conn: self.pg_conn.rollback()
            return False

    def check_user_access(self, current_user_id, plate_number):
        """
        [LOGIC LÀN RA MỚI] Đối soát 2 cửa ải:
        Cửa 1: Có đúng là người dắt vào không? (Dành cho Khách + Tự lái)
        Cửa 2: Có cùng chung mã Hộ gia đình không? (Dành cho Người nhà dắt chéo)
        """
        if not self.ensure_pg_connection() or not current_user_id: return False
        try:
            cur = self.pg_conn.cursor()
            
            # 1. Tìm xem ai là người đã dắt chiếc xe này VÀO bãi gần nhất
            cur.execute("""
                SELECT user_id, action_type 
                FROM parking_logs 
                WHERE plate_detected = %s AND status = 'SUCCESS'
                ORDER BY timestamp DESC LIMIT 1
            """, (plate_number,))
            res = cur.fetchone()
            
            if not res:
                cur.close()
                return False # Xe không có trong bãi
                
            last_user_id, last_action = res
            
            # Nếu trạng thái xe không phải là IN, từ chối luôn
            if last_action not in ['IN', 'CHECK_IN']:
                cur.close()
                return False

            # ==========================================
            # CỬA ẢI 1: CHỦ TRỰC TIẾP (Khách / Tự dắt tự lấy) -> O(1) Siêu nhanh
            # ==========================================
            if last_user_id == int(current_user_id):
                cur.close()
                return True 
                
            # ==========================================
            # CỬA ẢI 2: NGƯỜI NHÀ DẮT HỘ (Kiểm tra Hộ gia đình)
            # ==========================================
            # Làm sạch biển số đầu vào (Xóa dấu gạch, chấm, khoảng trắng)
            clean_plate = plate_number.replace("-", "").replace(".", "").replace(" ", "").upper()
            
            # Làm sạch luôn biển số trong Database lúc so sánh bằng SQL (Linh hoạt định dạng)
            cur.execute("""
                SELECT f.family_id 
                FROM families f
                JOIN parking_users u ON f.family_id = u.family_id
                JOIN family_vehicles v ON f.family_id = v.family_id
                WHERE u.user_id = %s 
                AND REPLACE(REPLACE(REPLACE(UPPER(v.plate_number), '-', ''), '.', ''), ' ', '') = %s
            """, (int(current_user_id), clean_plate))
            
            family_match = cur.fetchone()
            cur.close()
            
            if family_match:
                # Trùng khớp mã Hộ gia đình -> Cho phép lấy xe chéo!
                return True
                
            # Rớt cả 2 cửa ải -> Báo động Kẻ gian!
            return False
            
        except Exception as e:
            print(f"Lỗi đối soát quyền sở hữu: {e}")
            return False

    def clear_all_data(self):
        """Xóa sạch sành sanh dữ liệu ở cả SQL và Qdrant."""
        try:
            # 1. SQL
            if self.ensure_pg_connection():
                cur = self.pg_conn.cursor()
                # Xóa sạch các bảng theo thứ tự để tránh lỗi khóa ngoại
                cur.execute("TRUNCATE TABLE parking_logs RESTART IDENTITY CASCADE;")
                cur.execute("TRUNCATE TABLE family_vehicles RESTART IDENTITY CASCADE;")
                cur.execute("TRUNCATE TABLE families RESTART IDENTITY CASCADE;")
                cur.execute("TRUNCATE TABLE parking_users RESTART IDENTITY CASCADE;")
                self.pg_conn.commit()
                cur.close()
                print("--- SQL Data Wiped (Families & Vehicles included) ---")
            
            # 2. Qdrant
            if self.ensure_qdrant_connection():
                self.qdrant_client.delete_collection(self.collection_name)
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(size=self.vector_size, distance=models.Distance.COSINE),
                )
                print("--- Qdrant Collection Reset ---")
            return True
        except Exception as e:
            print(f"Clear All Data Error: {e}")
            return False

    def get_checkin_time(self, plate_number):
        """Lấy thời gian IN gần nhất của biển số để tính tiền gửi xe.
        Lưu ý: action_type có thể là 'IN' hoặc 'CHECK_IN' tùy lịch sử ghi log.
        """
        if not self.ensure_pg_connection() or not plate_number: return None
        try:
            cur = self.pg_conn.cursor()
            cur.execute("""
                SELECT timestamp 
                FROM parking_logs 
                WHERE plate_detected = %s AND action_type IN ('IN', 'CHECK_IN') AND status = 'SUCCESS'
                ORDER BY timestamp DESC LIMIT 1
            """, (plate_number,))
            res = cur.fetchone()
            cur.close()
            return res[0] if res else None
        except Exception as e:
            print(f"Lỗi get_checkin_time: {e}")
            return None

if __name__ == "__main__":
    db = DatabaseManager()
    db.init_db()
