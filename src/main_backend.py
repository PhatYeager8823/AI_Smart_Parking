from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List
import os
import psycopg2
import base64
import json
import requests
import time
import cv2
import numpy as np
import uuid
from dotenv import load_dotenv
from db_manager import DatabaseManager
import shutil
from datetime import datetime
import asyncio
import cloudinary
import cloudinary.uploader
import threading

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "system.env"))

# Cloudinary Setup
cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET")
)

app = FastAPI(title="Smart Parking Orchestrator")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.join(BASE_DIR, "..")
DASHBOARD_DIR = os.path.join(ROOT_DIR, "dashboard")
LOG_FILE = os.path.join(ROOT_DIR, "logs", "logs.json")
DEBUG_LOG_FILE = os.path.join(ROOT_DIR, "logs", "debug_orchestrator.txt")
ERROR_LOG_FILE = os.path.join(ROOT_DIR, "logs", "error_log.txt")
STATE_FILE = os.path.join(DASHBOARD_DIR, "state.json")
PLATE_DEST = os.path.join(DASHBOARD_DIR, "last_plate.jpg")
FACE_DEST = os.path.join(DASHBOARD_DIR, "last_face.jpg")

os.makedirs(DASHBOARD_DIR, exist_ok=True)

def write_debug(msg):
    """Ghi log an toàn vào file debug_orchestrator.txt"""
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except:
        pass 
    print(f"DEBUG: {msg}")

def write_error(msg, service="BACKEND"):
    """Ghi log lỗi vào file error_log.txt"""
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{service}] ERROR: {msg}\n")
    except:
        pass
    print(f"ERROR: [{service}] {msg}")

# Ghi log bắt đầu hệ thống
write_debug("=== HE THONG KHOI DONG ===")
PLATE_API_URL = os.getenv("PLATE_API_URL", "http://localhost:8001")
FACE_API_URL = os.getenv("FACE_API_URL", "http://localhost:8002")

db_manager = DatabaseManager()
# Ở chế độ hybrid, ta chỉ kiểm tra kết nối, không tự tạo bảng
db_manager.init_db()

# --- CLOUDINARY LOGGING TASK ---
def archive_images(plate_text, name, session_id=None):
    """Đẩy ảnh lên Cloudinary và cập nhật Database với URL & Public ID."""
    def task():
        try:
            face_url = None
            plate_url = None
            face_pid = None
            plate_pid = None
            
            # Đã bổ sung thư mục con storage để phân loại ảnh giao dịch
            folder = datetime.now().strftime("smart_parking/storage/%d-%m-%Y")
            
            # 1. Upload ảnh khuôn mặt
            if os.path.exists(FACE_DEST):
                with open(FACE_DEST, "rb") as f:
                    res = cloudinary.uploader.upload(f, folder=folder, public_id=f"face_{int(time.time())}_{plate_text}")
                    face_url = res.get("secure_url")
                    face_pid = res.get("public_id")
            
            # 2. Upload ảnh biển số
            if os.path.exists(PLATE_DEST):
                with open(PLATE_DEST, "rb") as f:
                    res = cloudinary.uploader.upload(f, folder=folder, public_id=f"plate_{int(time.time())}_{plate_text}")
                    plate_url = res.get("secure_url")
                    plate_pid = res.get("public_id")

            # 3. Cập nhật vào SQL Log (Nếu có session_id)
            if session_id:
                try:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE parking_logs SET face_url = %s, plate_url = %s, face_public_id = %s, plate_public_id = %s WHERE session_id = %s",
                        (face_url, plate_url, face_pid, plate_pid, session_id)
                    )
                    conn.commit()
                    cur.close()
                    conn.close()
                    write_debug(f"☁️ [Cloudinary] Đã lưu URL & ID cho phiên {session_id}")
                except Exception as db_e:
                    write_error(f"Lỗi cập nhật URL vào Log: {db_e}")

        except Exception as e:
            write_error(f"Lỗi Cloudinary Task: {e}")
            
    threading.Thread(target=task).start()


# Serve static files
app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR), name="dashboard")

# --- WEBSOCKET REAL-TIME MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)  # Đánh dấu connection đã chết
        for dead in dead_connections:
            self.active_connections.remove(dead)  # Dọn sạch connection chết

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def update_state(action, status, plate="Chưa có", name="Chưa biết", time_str="---", msg="", lane="ALL", fee=""):
    state = {
        "action": action,
        "status": status,
        "plate": plate,
        "name": name,
        "time": time_str,
        "message": msg,
        "lane": lane,
        "fee": fee # Gửi phí lên Web
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    await manager.broadcast({"type": "state", "data": state})
    write_debug(f"Trạng thái: {action} | {status} | Biển: {plate} | Phí: {fee}")

def save_log(log):
    try:
        data = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
        data.insert(0, log)
        with open(LOG_FILE, "w", encoding='utf-8') as f:
            json.dump(data[:50], f, indent=4, ensure_ascii=False)
    except Exception as e:
        write_debug(f"Error saving log: {e}")

def notify_log_update():
    """Thông báo cho Web biết có nhật ký mới để load lại"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(manager.broadcast({"type": "log_update"}))
    except:
        pass

def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB", "smart_parking"),
            user=os.getenv("POSTGRES_USER", "parking_admin"),
            password=os.getenv("POSTGRES_PASSWORD", "parking_password123"),
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432")
        )
        return conn
    except Exception as e:
        print(f"DB Connection Error: {e}")
        return None

@app.get("/api/stats")
def get_stats():
    """Lấy số liệu thống kê thực tế từ PostgreSQL."""
    conn = get_db_connection()
    if not conn:
        return {"total": 0, "in": 0, "out": 0, "current": 0}
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM parking_logs WHERE status = 'SUCCESS'")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM parking_logs WHERE action_type = 'CHECK_IN' AND status = 'SUCCESS'")
        count_in = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM parking_logs WHERE action_type = 'CHECK_OUT' AND status = 'SUCCESS'")
        count_out = cur.fetchone()[0]
        cur.close()
        conn.close()
        return {
            "total": total,
            "in": count_in,
            "out": count_out,
            "current": max(0, count_in - count_out)
        }
    except:
        return {"total": 0, "in": 0, "out": 0, "current": 0}

@app.get("/api/logs")
def get_logs(limit: int = 50):
    """Chỉ đọc nhật ký trực tiếp từ PostgreSQL."""
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        try:
            # Truy vấn đầy đủ (có cột face_url, plate_url sau khi đã chạy ALTER TABLE)
            cur.execute("""
                SELECT l.plate_detected, u.full_name, l.action_type, l.status, l.timestamp, l.face_url, l.plate_url
                FROM parking_logs l
                LEFT JOIN parking_users u ON l.user_id = u.user_id
                ORDER BY l.timestamp DESC LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
            has_url_cols = True
        except Exception:
            # Fallback: Nếu chưa chạy ALTER TABLE, dùng query không có 2 cột mới
            conn.rollback()
            cur.execute("""
                SELECT l.plate_detected, u.full_name, l.action_type, l.status, l.timestamp
                FROM parking_logs l
                LEFT JOIN parking_users u ON l.user_id = u.user_id
                ORDER BY l.timestamp DESC LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
            has_url_cols = False

        logs = []
        for r in rows:
            # 🔴 BỘ DỊCH THUẬT TIẾNG VIỆT
            raw_status = r[3]
            vn_status = raw_status
            if raw_status == "SUCCESS": vn_status = "THÀNH CÔNG"
            elif raw_status == "FAILED_WRONG_OWNER": vn_status = "SAI CHỦ XE"
            elif raw_status == "FAILED_UNKNOWN_FACE": vn_status = "KẺ GIAN"
            
            logs.append({
                "plate": r[0] or "N/A",
                "name": r[1] if r[1] else "Khách Vãng Lai",
                "action": r[2], 
                "status": vn_status,
                "time": r[4].strftime("%H:%M:%S - %d/%m"),
                "face_url": r[5] if has_url_cols and r[5] else "",
                "plate_url": r[6] if has_url_cols and r[6] else ""
            })
        cur.close()
        conn.close()
        return logs
    except Exception as e:
        write_debug(f"Lỗi truy vấn SQL: {e}")
        if conn: conn.close()
        return []

def get_official_face_url(user_id, plate_text):
    """Lấy ảnh hồ sơ để đối chiếu trong Vùng Vàng:
    1. Ảnh đăng ký chính thức của Cư dân (parking_users.face_url)
    2. Ảnh lần vào gần nhất theo user_id (parking_logs.face_url)
    3. Ảnh lần vào gần nhất theo biển số (parking_logs.face_url)
    """
    conn = get_db_connection()
    if not conn: return None
    try:
        cur = conn.cursor()
        
        # [ƯU TIÊN 1]: Ảnh đăng ký chính thức (Cư dân đã có face_url trong parking_users)
        if user_id:
            cur.execute("SELECT face_url FROM parking_users WHERE user_id = %s AND face_url IS NOT NULL", (user_id,))
            row = cur.fetchone()
            if row and row[0]:
                cur.close(); conn.close()
                return row[0]
        
        # [ƯU TIÊN 2]: Ảnh lần vào gần nhất theo user_id (GUEST đã từng vào và được archive)
        if user_id:
            cur.execute("""
                SELECT face_url FROM parking_logs
                WHERE user_id = %s AND face_url IS NOT NULL
                ORDER BY timestamp DESC LIMIT 1
            """, (user_id,))
            row = cur.fetchone()
            if row and row[0]:
                cur.close(); conn.close()
                return row[0]
        
        # [ƯU TIÊN 3]: Ảnh lần vào gần nhất theo biển số (fallback cuối)
        cur.execute("""
            SELECT face_url FROM parking_logs
            WHERE plate_detected = %s AND face_url IS NOT NULL
            ORDER BY timestamp DESC LIMIT 1
        """, (plate_text,))
        row = cur.fetchone()
        
        cur.close(); conn.close()
        return row[0] if row else None
    except Exception as e:
        write_debug(f"Lỗi lấy ảnh official: {e}")
        if conn: conn.close()
        return None

@app.get("/api/debug-logs")
def get_debug_logs():
    """Lấy 50 dòng log cuối cùng để hiển thị trên Dashboard"""
    try:
        if not os.path.exists(DEBUG_LOG_FILE):
             return []
        with open(DEBUG_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return lines[-50:] # Trả về 50 dòng cuối
    except Exception as e:
        return [f"Error reading debug log: {str(e)}"]

# Bộ nhớ tạm để lưu thông tin từ bước 1 (Biển số qua Mobile/Nhập tay)
# Cấu trúc: { "IN": { "sess_id": { data } }, "OUT": { ... } }
pending_sessions = {
    "IN": {},
    "OUT": {}
}

async def cleanup_expired_sessions():
    """Tiến trình ngầm: Tự động xóa các phiên chờ quá 5 phút (300 giây)"""
    while True:
        try:
            await asyncio.sleep(10) # Quét mỗi 10 giây một lần
            now = time.time()
            for lane in ["IN", "OUT"]:
                to_delete = []
                for sess_id, data in pending_sessions[lane].items():
                    # Xóa phiên nếu quá 300 giây (5 phút) không hoạt động
                    if now - data.get("timestamp", 0) > 300:
                        to_delete.append(sess_id)
                
                for sess_id in to_delete:
                    del pending_sessions[lane][sess_id]
                    write_debug(f"HẾT HẠN: Đã xóa phiên {sess_id} tại làn {lane} do quá 5 phút.")
                    # Thông báo cho Dashboard xóa thẻ xe
                    await manager.broadcast({
                        "type": "session_expired",
                        "lane": lane,
                        "session_id": sess_id
                    })
        except Exception as e:
            write_debug(f"Lỗi Cleanup Task: {e}")

@app.on_event("startup")
async def startup_event():
    # Khởi chạy tiến trình dọn dẹp ngầm
    asyncio.create_task(cleanup_expired_sessions())
    write_debug("Hệ thống Cleanup Thread đã được kích hoạt.")

@app.post("/api/reset")
async def reset_system():
    """Xóa sạch sành sanh dữ liệu để demo từ đầu."""
    try:
        write_debug("=== YÊU CẦU RESET TOÀN BỘ HỆ THỐNG ===")
        
        # 1. Xóa dữ liệu Database (SQL + Vector)
        success = db_manager.clear_all_data()
        
        # 2. Xóa hàng chờ Session trong RAM
        global pending_sessions
        pending_sessions = {"IN": {}, "OUT": {}}
        
        # 3. Xóa các file ảnh tạm, logs và file trạng thái
        files_to_delete = [
            PLATE_DEST, FACE_DEST, LOG_FILE, STATE_FILE, DEBUG_LOG_FILE,
            os.path.join(ROOT_DIR, "logs", "debug_face.txt"),
            os.path.join(ROOT_DIR, "logs", "debug_plate.txt"),
            os.path.join(ROOT_DIR, "logs", "error_log.txt")
        ]
        for f in files_to_delete:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass
        
        if success:
            await manager.broadcast({"type": "state", "data": {"action": "READY", "message": "Hệ thống đã Reset sạch sẽ", "plate": "---", "lane": "ALL"}})
            write_debug("--- HE THONG DA DUOC RESET SACH SE (SQL + LOGS + CACHE) ---")
            return {"status": "success", "message": "Đã xóa sạch dữ liệu."}
        else:
            return {"status": "error", "message": "Lỗi khi xóa CSDL"}
    except Exception as e:
        write_debug(f"LỖI RESET: {e}")
        return {"status": "error", "message": str(e)}

class MobilePayload(BaseModel):
    image: str
    lane: str = "IN" # Mặc định là IN nếu mobile cũ chưa cập nhật

@app.post("/api/upload_mobile_plate")
async def upload_mobile_plate(payload: MobilePayload):
    """BƯỚC 1: Nhận diện biển số từ điện thoại."""
    try:
        header, encoded = payload.image.split(",", 1)
        img_data = base64.b64decode(encoded)
        nparr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None: return {"status": "error", "message": "Ảnh không hợp lệ"}

        lane = payload.lane.upper()
        write_debug(f"Nhận ảnh từ Mobile cho làn {lane}. Đang chạy pipeline...")

        # 🔴 BẢN VÁ: CHỈ GỌI API AI ĐỌC BIỂN SỐ 1 LẦN DUY NHẤT Ở ĐÂY
        res = await run_ai_pipeline_legacy(frame, source="MOBILE", lane=lane)
        
        if res.get("status") == "success":
            plate_text = res["plate"]

            # [BẢO VỆ SỚM] Kiểm tra logic cho LÀN RA
            if lane == "OUT":
                last_action = db_manager.get_plate_last_action(plate_text)
                if last_action not in ["IN", "CHECK_IN"]:
                    write_debug(f"TỪ CHỐI SỚM (Mobile OUT): Biển {plate_text} chưa vào bãi!")
                    await update_state(
                        "CẢNH BÁO", "XE CHƯA VÀO BÃI",
                        plate=plate_text, lane=lane,
                        time_str=time.strftime("%H:%M:%S"),
                        msg=f"Biển số {plate_text} chưa được ghi nhận vào bãi!"
                    )
                    return {"status": "error", "message": f"Biển {plate_text} chưa vào bãi, không thể Check-OUT!"}

            # [BẢO VỆ SỚM] Kiểm tra logic cho LÀN VÀO
            elif lane == "IN":
                last_action = db_manager.get_plate_last_action(plate_text)
                if last_action in ["IN", "CHECK_IN"]:
                    write_debug(f"TỪ CHỐI SỚM (Mobile IN): Biển {plate_text} đang trong bãi!")
                    await update_state(
                        "CẢNH BÁO", "XE ĐÃ TRONG BÃI",
                        plate=plate_text, lane=lane,
                        time_str=time.strftime("%H:%M:%S"),
                        msg=f"Biển số {plate_text} đã vào bãi rồi, chưa ra!"
                    )
                    return {"status": "error", "message": f"Biển {plate_text} đang trong bãi, không thể Check-IN lại!"}
            
            # ==============================================================
            # Đã vượt qua kiểm tra logic -> Xử lý đưa vào hàng chờ
            # ==============================================================
            
            # [LỚP PHÒNG NGỰ 1] CHẶN SPAM HÀNG CHỜ (RAM)
            for existing_sid, data in pending_sessions[lane].items():
                if data.get("plate") == plate_text:
                    existing_status = data.get("status", "WAITING")
                    # Các trạng thái tạm thời -> cho phép gửi lại mà không chặn
                    soft_fail_statuses = ["WAITING", "NO_FACE", "KHÔNG THẤY MẶT", "RETRY"]
                    if existing_status not in soft_fail_statuses:
                        write_debug(f"CHẶN SPAM: Biển số {plate_text} đã có trong hàng chờ {lane} (trạng thái: {existing_status}).")
                        return {"status": "error", "message": f"Biển số {plate_text} đang chờ quét mặt rồi!"}
                    else:
                        write_debug(f"CHO PHÉP QUÉT LẠI: {plate_text} có phiên cũ trạng thái '{existing_status}', cho phép tạo phiên mới.")

            # Tạo Session ID duy nhất cho lượt quét này
            session_id = f"sess_{int(time.time())}_{str(uuid.uuid4())[:4]}"
            
            write_debug(f"TẠO SESSION MỚI: {session_id} cho biển số {res['plate']} (Làn: {lane})")
            
            # Lưu vào hàng chờ của làn tương ứng
            pending_sessions[lane][session_id] = {
                "plate": plate_text,
                "timestamp": time.time(),
                "status": "WAITING"
            }
            
            # Thông báo cho Dashboard biết có xe mới vào hàng chờ
            await manager.broadcast({
                "type": "new_pending_vehicle",
                "lane": lane,
                "session_id": session_id,
                "plate": plate_text
            })
            
            return {"status": "success", "session_id": session_id, "plate": plate_text}
        
        return res
    except Exception as e:
        write_debug(f"LỖI UPLOAD MOBILE: {str(e)}")
        return {"status": "error", "message": str(e)}

class FacePayload(BaseModel):
    image: str
    session_id: str
    lane: str

@app.post("/api/scan-face-webcam")
async def scan_face_webcam(payload: FacePayload):
    """BƯỚC 2: Nhận diện khuôn mặt theo Session ID cụ thể."""
    lane = payload.lane.upper()
    sess_id = payload.session_id
    
    # Kiểm tra xem session có tồn tại không
    if sess_id not in pending_sessions[lane]:
        write_debug(f"SAI BIỆT SESSION: Không tìm thấy {sess_id} trong làn {lane}")
        write_debug(f"Danh sách hiện có: {list(pending_sessions[lane].keys())}")
        return {
            "status": "error", 
            "message": f"Phiên làm việc {sess_id} không tồn tại hoặc đã hết hạn (5 phút). Vui lòng quét lại biển số.",
            "debug_lane": lane,
            "available_sessions": list(pending_sessions[lane].keys())
        }

    session_data = pending_sessions[lane][sess_id]
    plate_text = session_data["plate"]

    # [LỚP PHÒNG NGỰ 2] KIỂM TRA TRẠNG THÁI VẬT LÝ (SQL)
    last_action = db_manager.get_plate_last_action(plate_text)
    is_currently_in = last_action in ["IN", "CHECK_IN"]

    if lane == "IN" and is_currently_in:
        write_debug(f"TỪ CHỐI LOGIC: Xe {plate_text} đang ở trong bãi, không thể VÀO tiếp!")
        await update_state("CẢNH BÁO", "XE ĐÃ TRONG BÃI", plate=plate_text, lane=lane, time_str=time.strftime("%H:%M:%S"), msg="Xe này chưa được lấy ra!")
        del pending_sessions[lane][sess_id] # Xóa rác khỏi hàng chờ
        return {"status": "error", "message": "Xe đang ở trong bãi, không thể Check-IN!"}

    if lane == "OUT" and not is_currently_in:
        write_debug(f"TỪ CHỐI LOGIC: Xe {plate_text} không ở trong bãi, không thể lấy RA!")
        await update_state("CẢNH BÁO", "XE KHÔNG TRONG BÃI", plate=plate_text, lane=lane, time_str=time.strftime("%H:%M:%S"), msg="Xe này không có trong bãi!")
        del pending_sessions[lane][sess_id] # Xóa rác khỏi hàng chờ
        return {"status": "error", "message": "Xe không ở trong bãi, không thể Check-OUT!"}

    try:
        write_debug(f"Đang quét mặt cho Session {sess_id} (Biển: {plate_text}, Làn: {lane})")
        header, encoded = payload.image.split(",", 1)
        img_data = base64.b64decode(encoded)
        nparr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None: return {"status": "error", "message": "Lỗi giải mã ảnh"}
        
        cv2.imwrite(FACE_DEST, frame)
        _, buffer = cv2.imencode('.jpg', frame)
        face_base64 = base64.b64encode(buffer).decode('utf-8')

        # [DEMO DELAY] Giả lập phân tích chuyên sâu để thầy cô kịp theo dõi
        await update_state("ĐỐI SOÁT", "Đang trích xuất đặc trưng khuôn mặt...", plate=plate_text, lane=lane)
        # await asyncio.sleep(1.5) # Xóa delay để chạy thực tế mượt mà hơn
        
        # Gọi Face API thực tế
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: requests.post(f"{FACE_API_URL}/represent", json={"image": face_base64}, timeout=30))
        face_resp = resp.json()
        face_vector = face_resp.get("embedding", [])

        if not face_vector:
            await update_state("TỪ CHỐI", "KHÔNG THẤY MẶT", plate=plate_text, msg="Hãy nhìn thẳng vào camera!", lane=lane)
            return {"status": "face_not_detected"}

        # ==========================================
        # [HỆ THỐNG GIAO DỊCH 3 VÙNG]
        # VÙNG XANH (>=75%): Tự động mở cửa
        # VÙNG VÀNG (60-75%): Yêu cầu bảo vệ xác nhận
        # VÙNG ĐỎ (<60%): Từ chối, cảnh báo xâm nhập
        # ==========================================
        curr_time = time.strftime("%H:%M:%S")
        action_type = "IN" if lane == "IN" else "OUT"

        # Log AI vector để debug
        write_debug(f"🔍 [AI VECTOR] 3 chỉ số đầu tiên: {str(face_vector[:3])}")

        # Tìm kiếm với ngưỡng mở rộng (vùng vàng)
        YELLOW_THRESHOLD = float(os.getenv("FACE_YELLOW_THRESHOLD", 0.60))
        match, zone = db_manager.search_face_extended(face_vector, YELLOW_THRESHOLD)

        # ==========================================
        # VÙNG VÀNG: Cần bảo vệ xác nhận thủ công
        # ==========================================
        if zone == 'yellow':
            db_name = match.payload.get("name", "Nghi vấn") if match else "Nghi vấn"
            score_pct = f"{match.score:.0%}" if match else "N/A"
            write_debug(f"⚠️ [VÙNG VÀNG] Khuôn mặt {db_name} | Điểm: {match.score:.3f} ({score_pct}) - Yêu cầu bảo vệ xác nhận!")

            # 🔴 BẢN VÁ BẢO MẬT: Bắt buộc kiểm tra sở hữu NGAY CẢ TRONG VÙNG VÀNG
            if lane == "OUT" and match:
                is_owner = db_manager.check_user_access(match.id, plate_text)
                if not is_owner:
                    write_debug(f"BÁO ĐỘNG BẢO MẬT CAO (VÙNG VÀNG): {db_name} định lấy xe {plate_text} nhưng KHÔNG ĐƯỢC PHÉP!")
                    db_manager.log_event(sess_id, match.id, plate_text, match.score, "CHECK_OUT", "FAILED_WRONG_OWNER")
                    await update_state("TỪ CHỐI", "SAI CHỦ TÀI SẢN", plate=plate_text, name=db_name, msg="Khuôn mặt giống cư dân nhưng không phải chủ xe này!", lane=lane, time_str=curr_time)
                    
                    archive_images(plate_text, db_name, session_id=sess_id)
                    notify_log_update()
                    
                    if sess_id in pending_sessions[lane]: del pending_sessions[lane][sess_id]
                    return {"status": "security_reject"}

            # Lưu trạng thái chờ xác nhận vào session
            pending_sessions[lane][sess_id]["status"] = "YELLOW_ZONE"
            pending_sessions[lane][sess_id]["match_id"] = match.id
            pending_sessions[lane][sess_id]["match_name"] = db_name
            pending_sessions[lane][sess_id]["match_score"] = match.score
            pending_sessions[lane][sess_id]["action_type"] = action_type
            pending_sessions[lane][sess_id]["face_vector"] = face_vector

            await update_state(
                "CẦN XÁC NHẬN",
                f"Tương đồng {score_pct} - Bảo vệ xác nhận!",
                plate=plate_text, name=db_name, lane=lane, time_str=curr_time,
                msg=f"Dữ liệu sinh trắc không đủ chắc chắn ({score_pct}). Bảo vệ vui lòng xem camera và xác nhận."
            )
            target_user_id = match.id if match else None
            registered_face_url = get_official_face_url(target_user_id, plate_text) or ""
            # Lưu cờ phí ngay tại đây để manual_approve dùng sau
            pending_sessions[lane][sess_id]["is_registered_plate"] = db_manager.get_family_by_plate(plate_text) is not None
            await manager.broadcast({
                "type": "yellow_zone",
                "session_id": sess_id,
                "lane": lane,
                "plate": plate_text,
                "name": db_name,
                "score": score_pct,
                "registered_face_url": registered_face_url
            })
            return {"status": "yellow_zone", "message": f"Đang chờ bảo vệ xác nhận ({score_pct})"}
        target_user_id = None
        db_name = "Khách lạ"

        # ==========================================
        # VÙNG XANH: Nhận diện thành công (>=75%)
        # ==========================================
        if zone == 'green' and match:
            target_user_id = match.id
            user_info = db_manager.get_user_by_id(target_user_id)
            db_name = user_info.get("name", "Người quen") if user_info else "Người quen"
            write_debug(f"✅ [VÙNG XANH] Trùng khớp với {db_name} | Điểm: {match.score:.3f} ({match.score:.0%}) - Tự động mở cửa!")

            if lane == "OUT":
                # [BẢO VỆ SỚM] - BẮT BUỘC kiểm tra sở hữu cho TẤT CẢ xe
                is_owner = db_manager.check_user_access(target_user_id, plate_text)
                
                if is_owner:
                    write_debug(f"XÁC THỰC THÀNH CÔNG: {db_name} được phép lấy xe {plate_text}.")
                    
                    # Kiểm tra xem xe này có đăng ký chưa để tính tiền (Nếu chưa -> Đổi tên thành GUEST)
                    plate_family_id = db_manager.get_family_by_plate(plate_text)
                    if plate_family_id is None:
                        write_debug(f"XỬ LÝ TRẢ PHÍ: {db_name} ra với xe chưa đăng ký {plate_text}.")
                        db_name = f"GUEST_{plate_text}"
                else:
                    write_debug(f"BÁO ĐỘNG BẢO MẬT CAO: Kẻ gian {db_name} định lấy xe {plate_text} nhưng KHÔNG ĐƯỢC PHÉP!")
                    db_manager.log_event(sess_id, target_user_id, plate_text, match.score, "CHECK_OUT", "FAILED_WRONG_OWNER")
                    await update_state("TỪ CHỐI", "SAI CHỦ TÀI SẢN", plate=plate_text, name=db_name, msg="Bạn không phải người gửi chiếc xe này!", lane=lane, time_str=curr_time)
                    
                    # 🔴 BỔ SUNG 2 DÒNG NÀY ĐỂ HIỆN LÊN WEB VÀ LƯU ẢNH BẰNG CHỨNG
                    archive_images(plate_text, db_name, session_id=sess_id)
                    notify_log_update()
                    
                    if sess_id in pending_sessions[lane]: del pending_sessions[lane][sess_id]
                    return {"status": "security_reject"}
            else:  # lane == "IN"
                plate_family_id = db_manager.get_family_by_plate(plate_text)
                if plate_family_id is None:
                    # Xe lạ vào cùng cư dân → cho vào như khách vãng lai
                    write_debug(f"CƯ DÂN DÙNG XE LẠ: {db_name} vào với xe chưa đăng ký {plate_text}. Xử lý như khách vãng lai.")
                    db_name = f"GUEST_{plate_text}"
                else:
                    db_manager.update_user_plate(target_user_id, plate_text)
                    write_debug(f"GHI NHẬN TÀI SẢN MỚI: CCCD {db_name} vừa gửi thêm xe {plate_text}")

        # ==========================================
        # VÙNG ĐỎ: Không nhận diện được (<60%)
        # ==========================================
        elif zone == 'red':
            # Lấy điểm số cao nhất AI tìm được để hiển thị lên toast
            best_score = f"{match.score:.0%}" if match else "0%"
            write_debug(f"🔴 [VÙNG ĐỎ] Không tìm thấy khuôn mặt khớp (Best match: {best_score} < {YELLOW_THRESHOLD:.0%}) - Từ chối!")
            if lane == "OUT":
                db_manager.log_event(sess_id, None, plate_text, (match.score if match else 0.0), "CHECK_OUT", "FAILED_UNKNOWN_FACE")
                await update_state("TỪ CHỐI", "CCCD KHÔNG HỢP LỆ", plate=plate_text, name="Kẻ gian",
                    msg=f"Khuôn mặt chưa từng vào bãi! (Max match: {best_score})",
                    lane=lane, time_str=curr_time)
                
                # 🔴 BỔ SUNG 2 DÒNG NÀY ĐỂ HIỆN LÊN WEB VÀ LƯU ẢNH BẰNG CHỨNG
                archive_images(plate_text, "Kẻ_gian", session_id=sess_id)
                notify_log_update()
                
                if sess_id in pending_sessions[lane]: del pending_sessions[lane][sess_id]
                return {"status": "security_reject"}
            else:
                # Làn VÀO Vùng Đỏ: Khuôn mặt hoàn toàn lạ → tự động tạo GUEST
                new_face_id = f"face_{int(time.time())}"
                db_name = f"GUEST_{plate_text}"
                target_user_id = db_manager.register_user(new_face_id, plate_text, db_name, face_vector)

        # ==========================================
        # 3. TÍNH TOÁN PHÍ GỬI XE (CẬP NHẬT LOGIC MỚI)
        # ==========================================
        calculated_fee = 0
        fee_str = ""
        
        if action_type == "OUT":
            time_in = db_manager.get_checkin_time(plate_text)
            if time_in:
                hrs = (datetime.now() - time_in).total_seconds() / 3600.0
                if "GUEST" in db_name:
                    # Logic mới: Dưới 24h thu 2.000 VNĐ. 
                    # Nếu qua 24h (qua đêm), mỗi ngày tiếp theo cộng thêm 10.000 VNĐ (Phụ thu)
                    if hrs <= 24:
                        calculated_fee = 2000
                    else:
                        extra_days = int(hrs // 24)
                        calculated_fee = 2000 + (extra_days * 10000)
                        
                    fee_str = f"{calculated_fee:,.0f} VNĐ"
                else:
                    calculated_fee = 0
                    fee_str = "CƯ DÂN (Đã thu phí tháng)"

        # ==========================================
        # 4. GHI NHẬT KÝ & THÔNG BÁO DASHBOARD
        # ==========================================
        db_manager.log_event(sess_id, target_user_id, plate_text, (match.score if match else 1.0), action_type, "SUCCESS", parking_fee=calculated_fee)

        msg_banner = f"Chào mừng {db_name}!" if action_type == "IN" else f"Tạm biệt {db_name}!"
        await update_state("THÀNH CÔNG", msg_banner, plate=plate_text, name=db_name, lane=lane, time_str=curr_time, fee=fee_str)
        archive_images(plate_text, db_name, session_id=sess_id)
        
        if sess_id in pending_sessions[lane]:
            del pending_sessions[lane][sess_id]
            write_debug(f"HOÀN TẤT GIAO DỊCH: Phiên {sess_id} đã lưu SQL với mức phí {calculated_fee} VNĐ.")

        notify_log_update()
        return {"status": "completed", "plate": plate_text}

    except Exception as e:
        write_debug(f"LỖI SCAN FACE: {str(e)}")
        # Xóa session ngay lập tức khi có lỗi hệ thống, không chờ cleanup
        if sess_id in pending_sessions.get(lane, {}):
            del pending_sessions[lane][sess_id]
            write_debug(f"ĐÃ XÓA PHIÊN LỖI: {sess_id} (làn {lane})")
        await update_state("LỖI", "Lỗi Xử Lý", msg=str(e), lane=lane)
        return {"status": "error", "message": f"Lỗi hệ thống: {str(e)}"}

class ManualApprovePayload(BaseModel):
    action: str  # "approve" hoặc "reject"

@app.post("/api/manual-approve/{lane}/{session_id}")
async def manual_approve(lane: str, session_id: str, payload: ManualApprovePayload):
    """Bảo vệ xác nhận, từ chối hoặc yêu cầu quét lại khuôn mặt ở VÙNG VÀNG."""
    lane = lane.upper()
    if session_id not in pending_sessions.get(lane, {}):
        return {"status": "error", "message": "Phiên không tồn tại hoặc đã hết hạn"}

    sess = pending_sessions[lane][session_id]
    if sess.get("status") != "YELLOW_ZONE":
        return {"status": "error", "message": "Phiên này không ở trạng thái chờ xác nhận"}

    plate_text = sess["plate"]
    db_name    = sess["match_name"]
    match_id   = sess["match_id"]
    match_score = sess["match_score"]
    action_type = sess["action_type"]
    curr_time  = time.strftime("%H:%M:%S")

    if payload.action == "approve":
        write_debug(f"✅ [THỦ CÔNG] XÁC NHẬN mở cửa cho {db_name} (biển {plate_text})")
        
        # 🔴 [BẢN VÁ]: Cập nhật Biển số nếu Xác nhận ĐÚNG NGƯỜI ở Làn VÀO
        if lane == "IN":
            plate_family_id = db_manager.get_family_by_plate(plate_text)
            if plate_family_id is None:
                db_name = f"GUEST_{plate_text}"
            else:
                db_manager.update_user_plate(match_id, plate_text)

        calculated_fee = 0
        fee_str = ""
        is_registered_plate = sess.get("is_registered_plate", True)
        
        if action_type == "OUT":
            time_in = db_manager.get_checkin_time(plate_text)
            if time_in:
                hrs = (datetime.now() - time_in).total_seconds() / 3600.0
                if not is_registered_plate:
                    if hrs <= 24: calculated_fee = 2000
                    else:
                        extra_days = int(hrs // 24)
                        calculated_fee = 2000 + (extra_days * 10000)
                    fee_str = f"{calculated_fee:,.0f} VNĐ"
                else:
                    calculated_fee = 0
                    fee_str = "CƯ DÂN (Đã thu phí tháng)"

        db_manager.log_event(session_id, match_id, plate_text, match_score, action_type, "SUCCESS", parking_fee=calculated_fee)
        
        msg_banner = f"Chào mừng {db_name}!" if action_type == "IN" else f"Tạm biệt {db_name}!"
        await update_state("THÀNH CÔNG", msg_banner, plate=plate_text, name=db_name, lane=lane, time_str=curr_time, fee=fee_str)
        archive_images(plate_text, db_name, session_id=session_id)
        del pending_sessions[lane][session_id]
        notify_log_update()
        return {"status": "approved"}
        
    elif payload.action == "retry":
        write_debug(f"🔄 [THỦ CÔNG] Yêu cầu QUÉT LẠI MẶT cho biển {plate_text} (Giữ nguyên Session)")
        pending_sessions[lane][session_id]["status"] = "WAITING"
        await update_state("QUÉT LẠI", "Mời nhìn thẳng Camera", plate=plate_text, name="---", lane=lane, time_str=curr_time, msg="Vui lòng tháo kính và nhìn thẳng vào Camera.")
        await manager.broadcast({"type": "retry_scan", "session_id": session_id, "lane": lane, "plate": plate_text})
        return {"status": "retry"}
        
    else:
        # 🔴 [BẢN VÁ LỚN]: Phân rẽ 2 luồng TỪ CHỐI khác nhau hoàn toàn cho 2 làn
        if lane == "IN":
            # ---> TẠO MỚI KHÁCH VÃNG LAI
            write_debug(f"👤 [THỦ CÔNG] Bảo vệ xác nhận KHÁCH MỚI cho biển {plate_text}. Đang tạo dữ liệu...")
            new_face_id = f"face_{int(time.time())}"
            new_db_name = f"GUEST_{plate_text}"
            
            # Lấy vector 512D khuôn mặt AI đã trích xuất sẵn từ lúc đưa vào Vùng Vàng
            face_vector = sess["face_vector"]
            
            # Đăng ký Khách mới vào Qdrant và SQL
            new_target_user_id = db_manager.register_user(new_face_id, plate_text, new_db_name, face_vector)
            
            # Ghi Log vào bãi thành công
            db_manager.log_event(session_id, new_target_user_id, plate_text, 0.0, "IN", "SUCCESS", parking_fee=0)
            await update_state("THÀNH CÔNG", f"Chào mừng {new_db_name}!", plate=plate_text, name=new_db_name, lane=lane, time_str=curr_time)
            
            archive_images(plate_text, new_db_name, session_id=session_id)
            del pending_sessions[lane][session_id]
            notify_log_update()
            return {"status": "created_new"}
            
        else:
            # ---> BÁO ĐỘNG KẺ GIAN (Làn RA)
            write_debug(f"❌ [THỦ CÔNG] Bảo vệ đã TỪ CHỐI khuôn mặt {db_name} (biển {plate_text})")
            db_manager.log_event(session_id, match_id, plate_text, match_score, action_type, "FAILED_WRONG_OWNER")
            await update_state("TỪ CHỐI", "Bảo vệ từ chối xác nhận", plate=plate_text, name=db_name, lane=lane, time_str=curr_time)
            
            archive_images(plate_text, db_name, session_id=session_id)
            del pending_sessions[lane][session_id]
            notify_log_update()
            return {"status": "rejected"}

async def trigger_scan():
    """Chế độ Hybrid/Defense: Chỉ cập nhật trạng thái, nhường Camera cho Browser"""
    await update_state("ĐANG ĐỢI BIỂN SỐ", "Mời quét biển số bằng điện thoại...", plate="---", name="---")
    return {"status": "waiting_for_mobile"}
async def run_ai_pipeline_legacy(frame, source="LOCAL", lane="ALL"):
    """Dùng cho cả quét nhanh 1 bước và quét từ điện thoại"""
    try:
        _, buffer = cv2.imencode('.jpg', frame)
        img_base64 = base64.b64encode(buffer).decode('utf-8')

        # 1. Plate API
        write_debug(f"Đang gọi Plate API (Nguồn: {source}, Làn: {lane})...")
        await update_state("QUÉT BIỂN SỐ", "Đang xử lý...", msg=f"Nguồn: {source}", lane=lane)
        plate_text = "Không rõ"
        start_time = time.time()
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, lambda: requests.post(f"{PLATE_API_URL}/predict", json={"image": img_base64}, timeout=15))
            plate_resp = resp.json()
            process_time = (time.time() - start_time) * 1000
            plate_text = plate_resp.get("plate", "Không rõ")
            write_debug(f"Plate API phản hồi: {plate_text} ({int(process_time)}ms)")
            
            # ƯU TIÊN HIỂN THỊ ẢNH CẮT
            if plate_resp.get("crop"):
                try:
                    crop_data = base64.b64decode(plate_resp["crop"])
                    with open(PLATE_DEST, "wb") as f: f.write(crop_data)
                    write_debug("Đã lưu ảnh CẮT biển số.")
                except Exception as e:
                    write_error(f"Lỗi lưu crop: {e}")
                    cv2.imwrite(PLATE_DEST, frame)
            else:
                write_error("Plate API không trả về ảnh cắt. Ghi đè ảnh gốc làm fallback.", "PLATE")
                cv2.imwrite(PLATE_DEST, frame)
        except Exception as e:
            write_error(f"LỖI PLATE SERVICE: {str(e)}", "PLATE")
            cv2.imwrite(PLATE_DEST, frame)
        face_vector = []
        if source == "LOCAL":
            write_debug("Chế độ LOCAL: Đang gọi Face API...")
            await update_state("QUÉT MẶT", "Đang đối soát...", plate=plate_text, lane="IN")
            try:
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(None, lambda: requests.post(f"{FACE_API_URL}/represent", json={"image": img_base64}, timeout=15))
                face_resp = resp.json()
                face_vector = face_resp.get("embedding", [])
                write_debug(f"Face API (LOCAL) phản hồi: {face_resp.get('status')}")
            except Exception as e:
                write_debug(f"LỖI FACE SERVICE (LOCAL): {str(e)}")
            cv2.imwrite(FACE_DEST, frame)
        else:
            # Nếu là MOBILE, ta KHÔNG ghi đè ảnh xe vào khung mặt để tránh nhầm lẫn
            # Chỉ xóa ảnh mặt cũ để người dùng biết là đang chờ quét mặt mới
            if os.path.exists(FACE_DEST):
                try: os.remove(FACE_DEST)
                except: pass

        # Bước 3: DB Logic (CHỈ DÀNH CHO QUÉT NHANH 1 BƯỚC TẠI LOCAL)
        if source == "MOBILE":
            return {"status": "success", "plate": plate_text, "next": "WAITING_FOR_FACE"}
        
        # Nếu là LOCAL (Quét 1 bước), tiếp tục xử lý DB ngay
        if not face_vector:
            await update_state("TỪ CHỐI", "KHÔNG THẤY MẶT", plate=plate_text, lane=lane)
            return {"status": "face_not_detected"}

        # Xử lý DB (Quét nhanh 1 bước)
        match = db_manager.search_face(face_vector, float(os.getenv("FACE_SIMILARITY_THRESHOLD", 0.75)))
        curr_time = time.strftime("%H:%M:%S - %d/%m")
        # Tạo session_id cho chế độ LOCAL 1 bước
        legacy_sess_id = f"local_{int(time.time())}_{str(uuid.uuid4())[:4]}"
        if match:
            db_name = match.payload.get("name", "Unknown")
            # Sửa lỗi: truyền đủ tham số theo đúng signature của log_event()
            db_manager.log_event(legacy_sess_id, match.id, plate_text, match.score, "CHECK", "SUCCESS")
            await update_state("THÀNH CÔNG", "XÁC THỰC OK", plate_text, db_name, curr_time, f"Chào {db_name}!", lane=lane)
            archive_images(plate_text, db_name)
        else:
            await update_state("THÔNG QUA", "KHÁCH MỚI", plate_text, "Khách", curr_time, "Đã lưu thông tin khách.", lane=lane)
            archive_images(plate_text, "Khách_Vãng_Lai")

        return {"status": "completed", "plate": plate_text}
    except Exception as e:
        print(f"Legacy Pipeline Error: {e}")
        return {"status": "error", "message": str(e)}


class MemberInfo(BaseModel):
    name: str
    image_base64: str # Ảnh để lấy vector khuôn mặt

class FamilyRegistration(BaseModel):
    room_number: str
    owner_name: str
    plates: List[str]
    members: List[MemberInfo]
    monthly_fee: int = 0  # <--- Bổ sung dòng này

@app.post("/api/admin/register-family")
async def register_family(data: FamilyRegistration):
    try:
        write_debug(f"=== BẮT ĐẦU ĐĂNG KÝ HỘ GIA ĐÌNH: {data.room_number} ===")
        # Sửa lỗi: luôn đảm bảo kết nối PG còn sống trước khi dùng
        if not db_manager.ensure_pg_connection():
            return {"status": "error", "message": "Không thể kết nối đến Database!"}
        cur = db_manager.pg_conn.cursor()

        # 🔴 [BẢN VÁ DỌN RÁC]: Tự động dọn hộ cũ bị bỏ hoang do xóa riêng lẻ trước đó
        cur.execute("SELECT family_id FROM families WHERE UPPER(room_number) = %s", (data.room_number.strip().upper(),))
        existing_rooms = cur.fetchall()
        for r_id in existing_rooms:
            old_fam_id = r_id[0]
            cur.execute("SELECT COUNT(*) FROM parking_users WHERE family_id = %s", (old_fam_id,))
            u_cnt = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM family_vehicles WHERE family_id = %s", (old_fam_id,))
            v_cnt = cur.fetchone()[0]
            if u_cnt == 0 and v_cnt == 0:
                cur.execute("DELETE FROM families WHERE family_id = %s", (old_fam_id,))
                write_debug(f"🧹 [CSDL]: Phát hiện hộ cũ phòng {data.room_number} bị bỏ hoang (0 người, 0 xe), đã dọn dẹp.")

        # ==========================================
        # 🚧 LỚP RÀO CHẮN 1: KIỂM TRA TRÙNG BIỂN SỐ
        # ==========================================
        for plate in data.plates:
            clean_plate = plate.strip().upper()
            if clean_plate:
                cur.execute("""
                    SELECT f.room_number FROM family_vehicles v 
                    JOIN families f ON v.family_id = f.family_id 
                    WHERE v.plate_number = %s
                """, (clean_plate,))
                existing_fam = cur.fetchone()
                if existing_fam:
                    cur.close()
                    # Trả về thông báo lỗi rõ ràng cho Form Admin
                    return {"status": "error", "message": f"Biển số {clean_plate} đã được đăng ký cho phòng {existing_fam[0]}!"}

        # ==========================================
        # 🚧 LỚP RÀO CHẮN 2: KIỂM TRA TRÙNG KHUÔN MẶT
        # ==========================================
        member_vectors = []
        for member in data.members:
            raw_base64 = member.image_base64
            if "," in raw_base64: raw_base64 = raw_base64.split(",", 1)[1]
            
            resp = requests.post(f"{FACE_API_URL}/represent", json={"image": raw_base64})
            face_data = resp.json()
            
            if face_data.get("status") == "success":
                vector = face_data["embedding"]
                
                # Kiểm tra Qdrant xem mặt này đã có ai đăng ký chưa
                # Ngưỡng 0.75 — đồng bộ với ngưỡng xác thực chính để nhất quán
                match = db_manager.search_face(vector, threshold=0.75)
                if match:
                    # Sửa lỗi SQL: parking_users không có cột room_number, phải JOIN với families
                    cur.execute("""
                        SELECT f.room_number, u.face_url 
                        FROM parking_users u
                        LEFT JOIN families f ON u.family_id = f.family_id
                        WHERE u.user_id = %s
                    """, (int(match.id),))
                    user_info = cur.fetchone()
                    existing_room = user_info[0] if user_info else "Không rõ"
                    existing_face_url = user_info[1] if (user_info and user_info[1]) else "/dashboard/default_avatar.png"
                    
                    cur.close()
                    existing_name = match.payload.get("name", "Không rõ")
                    write_debug(f"PHÁT HIỆN TRÙNG MẶT: {member.name} trùng với {existing_name} (phòng {existing_room}), điểm={match.score:.3f}")
                    return {
                        "status": "error_duplicate",
                        "message": f"Khuôn mặt của '{member.name}' trùng khớp {match.score:.0%} với cư dân '{existing_name}' thuộc phòng '{existing_room}' đã có trong hệ thống!",
                        "new_face": f"data:image/jpeg;base64,{raw_base64}",
                        "old_face": existing_face_url
                    }
                
                member_vectors.append((member, vector))
            else:
                cur.close()
                return {"status": "error", "message": f"AI không nhận diện được rõ khuôn mặt của {member.name}. Vui lòng chụp lại!"}

        # ==========================================
        # ✅ VƯỢT QUA KIỂM TRA -> TIẾN HÀNH LƯU DATABASE
        # ==========================================
        # 1. Lưu Hộ gia đình
        cur.execute("INSERT INTO families (room_number, owner_name, monthly_fee) VALUES (%s, %s, %s) RETURNING family_id", 
                    (data.room_number, data.owner_name, data.monthly_fee))
        family_id = cur.fetchone()[0]

        # 2. Lưu Biển số xe
        for plate in data.plates:
            if plate.strip():
                cur.execute("INSERT INTO family_vehicles (plate_number, family_id) VALUES (%s, %s)", 
                            (plate.strip().upper(), family_id))

        # 3. Lưu Thành viên (upload Cloudinary + lưu SQL + Qdrant)
        for member, vector in member_vectors:
            try:
                face_id = f"face_{int(time.time())}_{member.name}"
                face_url, face_pid = None, None
                
                # Cập nhật lên Cloudinary SAU KHI đã vượt qua kiểm tra trùng
                cloud_folder = f"smart_parking/residents/{data.room_number}"
                # Lấy base64 từ member_vectors (giữ lại ảnh gốc để upload)
                raw_b64 = member.image_base64
                if "," in raw_b64: raw_b64 = raw_b64.split(",", 1)[1]
                cloud_res = cloudinary.uploader.upload(
                    f"data:image/jpeg;base64,{raw_b64}",
                    folder=cloud_folder,
                    public_id=f"profile_{face_id}"
                )
                face_url = cloud_res.get("secure_url")
                face_pid = cloud_res.get("public_id")
                
                # Lưu SQL & Qdrant
                db_manager.register_resident(data.room_number, face_id, member.name, vector, face_url=face_url, face_public_id=face_pid)
            except Exception as e:
                write_error(f"Lỗi thêm thành viên {member.name}: {e}", "REGISTER")
                raise Exception(f"Lỗi khi lưu hình ảnh {member.name}")

        db_manager.pg_conn.commit()
        cur.close()
        return {"status": "success", "message": f"Đã đăng ký thành công hộ {data.room_number}"}
        
    except Exception as e:
        write_error(f"LỖI ĐĂNG KÝ: {str(e)}", "REGISTER")
        if db_manager.pg_conn: db_manager.pg_conn.rollback()
        return {"status": "error", "message": "Lỗi hệ thống khi lưu trữ dữ liệu"}


@app.get("/api/admin/family/{room_number}")
def get_family_details(room_number: str):
    """Tra cứu thông tin hộ để điều chỉnh / dời đi."""
    if not db_manager.ensure_pg_connection():
        return {"status": "error", "message": "Mất kết nối Database"}
    try:
        cur = db_manager.pg_conn.cursor()
        cur.execute("SELECT family_id, owner_name FROM families WHERE UPPER(room_number) = %s", (room_number.strip().upper(),))
        fam = cur.fetchone()
        if not fam:
            cur.close()
            return {"status": "error", "message": f"Không tìm thấy hộ phòng {room_number}"}
        fam_id, owner_name = fam
        cur.execute("SELECT plate_number FROM family_vehicles WHERE family_id = %s", (fam_id,))
        vehicles = [row[0] for row in cur.fetchall()]
        cur.execute("SELECT user_id, full_name, face_url FROM parking_users WHERE family_id = %s", (fam_id,))
        members = [{"user_id": row[0], "name": row[1], "face_url": row[2]} for row in cur.fetchall()]
        cur.close()
        return {"status": "success", "family_id": fam_id, "owner_name": owner_name, "vehicles": vehicles, "members": members}
    except Exception as e:
        if db_manager.pg_conn: db_manager.pg_conn.rollback()
        return {"status": "error", "message": f"Lỗi hệ thống: {str(e)}"}


class AddVehiclePayload(BaseModel):
    plate_number: str

@app.post("/api/admin/family/{family_id}/add-vehicle")
def add_single_vehicle(family_id: int, payload: AddVehiclePayload):
    """THÊM XE vào hộ gia đình sẵn có."""
    if not db_manager.ensure_pg_connection(): return {"status": "error", "message": "Mất CSDL"}
    try:
        cur = db_manager.pg_conn.cursor()
        clean_plate = payload.plate_number.strip().upper()
        cur.execute("SELECT family_id FROM family_vehicles WHERE UPPER(plate_number) = %s", (clean_plate,))
        exist = cur.fetchone()
        if exist:
            cur.close()
            return {"status": "error", "message": f"Biển số đã đăng ký ở hộ mang mã ID {exist[0]}!"}
        cur.execute("INSERT INTO family_vehicles (plate_number, family_id) VALUES (%s, %s)", (clean_plate, family_id))
        db_manager.pg_conn.commit()
        cur.close()
        write_debug(f"➕ [BIẾN ĐỘNG]: Thêm xe {clean_plate} vào hộ ID {family_id}")
        return {"status": "success", "message": f"Đã thêm xe {clean_plate} thành công!"}
    except Exception as e:
        db_manager.pg_conn.rollback()
        return {"status": "error", "message": str(e)}


@app.delete("/api/admin/family/vehicle/{plate_number:path}")
def delete_single_vehicle(plate_number: str):
    """XÓA XE khỏi hộ → chuyển thành xe vãng lai. Dùng :path để hỗ trợ ký tự đặc biệt."""
    if not db_manager.ensure_pg_connection(): return {"status": "error", "message": "Mất CSDL"}
    try:
        cur = db_manager.pg_conn.cursor()
        cur.execute("DELETE FROM family_vehicles WHERE UPPER(plate_number) = %s", (plate_number.strip().upper(),))
        db_manager.pg_conn.commit()
        cur.close()
        write_debug(f"➖ [BIẾN ĐỘNG]: Xóa xe {plate_number} khỏi diện cư dân.")
        return {"status": "success", "message": f"Đã gỡ biển số {plate_number} thành xe vãng lai."}
    except Exception as e:
        db_manager.pg_conn.rollback()
        return {"status": "error", "message": str(e)}


@app.post("/api/admin/family/member/{user_id}")
def remove_single_member(user_id: int):
    """DỜI THÀNH VIÊN: Hạ cấp sang khách vãng lai, giữ nguyên lịch sử."""
    if not db_manager.ensure_pg_connection(): return {"status": "error", "message": "Mất CSDL"}
    try:
        cur = db_manager.pg_conn.cursor()
        cur.execute("UPDATE parking_users SET family_id = NULL, role = 'guest' WHERE user_id = %s", (user_id,))
        if db_manager.ensure_qdrant_connection():
            try:
                db_manager.qdrant_client.set_payload(
                    collection_name=db_manager.collection_name,
                    payload={"role": "guest", "family_id": None},
                    points=[user_id]
                )
            except Exception as q_err:
                write_error(f"Lỗi đồng bộ Qdrant hạ cấp thành viên: {q_err}")
        db_manager.pg_conn.commit()
        cur.close()
        write_debug(f"➖ [BIẾN ĐỘNG]: Thành viên ID {user_id} dời đi → khách.")
        return {"status": "success", "message": "Thành viên đã dời đi và chuyển thành khách vãng lai."}
    except Exception as e:
        db_manager.pg_conn.rollback()
        return {"status": "error", "message": str(e)}


@app.post("/api/admin/remove-family/{room_number}")
def remove_whole_family_safe(room_number: str):
    """DỜI TOÀN BỘ HỘ: Giải phóng phòng an toàn, giữ nguyên lịch sử check-in/out."""
    if not db_manager.ensure_pg_connection():
        return {"status": "error", "message": "Không thể kết nối Database"}
    cur = db_manager.pg_conn.cursor()
    try:
        cur.execute("SELECT family_id FROM families WHERE UPPER(room_number) = %s", (room_number.strip().upper(),))
        res = cur.fetchone()
        if not res:
            cur.close()
            return {"status": "error", "message": f"Phòng {room_number} không tồn tại hoặc đã dời đi trước đó."}
        fam_id = res[0]
        cur.execute("SELECT user_id FROM parking_users WHERE family_id = %s", (fam_id,))
        user_ids = [row[0] for row in cur.fetchall()]
        cur.execute("DELETE FROM family_vehicles WHERE family_id = %s", (fam_id,))
        cur.execute("UPDATE parking_users SET family_id = NULL, role = 'guest' WHERE family_id = %s", (fam_id,))
        cur.execute("DELETE FROM families WHERE family_id = %s", (fam_id,))
        if db_manager.ensure_qdrant_connection() and user_ids:
            for uid in user_ids:
                try:
                    db_manager.qdrant_client.set_payload(
                        collection_name=db_manager.collection_name,
                        payload={"role": "guest", "family_id": None},
                        points=[uid]
                    )
                except: pass
            write_debug(f"🧹 [Qdrant]: Hạ cấp {len(user_ids)} thành viên hộ {room_number}")
        db_manager.pg_conn.commit()
        cur.close()
        write_debug(f"🧹 [CSDL]: Hộ phòng {room_number} dời đi sạch sẽ.")
        return {"status": "success", "message": f"Hộ phòng {room_number} đã dời đi hoàn tất!"}
    except Exception as e:
        db_manager.pg_conn.rollback()
        cur.close()
        write_error(f"Lỗi dời hộ {room_number}: {e}")
        return {"status": "error", "message": f"Lỗi hệ thống: {str(e)}"}


@app.get("/")
def root():
    return {"message": "Smart Parking Orchestrator Running", "dashboard": "/dashboard/index.html"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)