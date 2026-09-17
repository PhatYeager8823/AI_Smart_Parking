import os
import cv2
import numpy as np
import base64
import time
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from deepface import DeepFace
from contextlib import asynccontextmanager
from dotenv import load_dotenv

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

# Shared log files and environment config
ROOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
load_dotenv(os.path.join(ROOT_DIR, "system.env"))
load_dotenv(os.path.join(ROOT_DIR, ".env"))

# Load config from env
BACKBONE = os.getenv("FACE_BACKBONE", "Facenet512")
DETECTOR = os.getenv("FACE_DETECTOR", "mtcnn")

DEBUG_LOG_FILE = os.path.join(ROOT_DIR, "logs", "debug_face.txt")
ERROR_LOG_FILE = os.path.join(ROOT_DIR, "logs", "error_log.txt")

def write_face_debug(msg):
    """Ghi log an toàn vào file debug_face.txt"""
    try:
        timestamp = time.strftime("%H:%M:%S")
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [FACE_SERVICE] {msg}\n")
    except:
        pass 

def write_error(msg):
    """Ghi log lỗi cho dịch vụ khuôn mặt."""
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [FACE] ERROR: {msg}\n")
    except:
        pass
    print(f"FACE_ERROR: {msg}")

def warmup_model():
    """Tải model vào RAM trước khi nhận request đầu tiên."""
    write_face_debug(f"--- WARMUP: Đang load model {BACKBONE} + detector={DETECTOR}... ---")
    try:
        # Create a tiny dummy image for warmup
        dummy = np.zeros((160, 160, 3), dtype=np.uint8)
        dummy_path = "warmup_dummy.jpg"
        cv2.imwrite(dummy_path, dummy)
        
        DeepFace.represent(
            img_path=dummy_path,
            model_name=BACKBONE,
            detector_backend=DETECTOR,
            enforce_detection=False,
            align=False
        )
        write_face_debug(f"--- WARMUP XONG! Hệ thống MTCNN đã sẵn sàng. ---")
    except Exception as e:
        write_face_debug(f"WARMUP Warning: {e}")
    finally:
        if os.path.exists("warmup_dummy.jpg"): os.remove("warmup_dummy.jpg")

@asynccontextmanager
async def lifespan(app: FastAPI):
    warmup_model()
    yield

app = FastAPI(title="Face API (DeepFace)", lifespan=lifespan)

class ImagePayload(BaseModel):
    image: str # Base64 string

@app.get("/")
def health():
    return {"status": "ready", "model": BACKBONE, "detector": DETECTOR}

@app.post("/represent")
def represent(payload: ImagePayload):
    # Sử dụng file tạm riêng biệt cho mỗi request
    temp_path = f"temp_face_{uuid.uuid4().hex[:8]}.jpg"
    try:
        write_face_debug(f"Nhận request đối soát ({len(payload.image)} bytes)")
        img_data = base64.b64decode(payload.image)
        nparr = np.frombuffer(img_data, np.uint8)
        img_orig = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img_orig is None:
            write_face_debug("Lỗi: Không giải mã được ảnh")
            raise HTTPException(status_code=400, detail="Invalid Image Data")

        cv2.imwrite(temp_path, img_orig)

        # Trích xuất Vector bằng MTCNN
        embeddings = DeepFace.represent(
            img_path=temp_path, 
            model_name=BACKBONE, 
            detector_backend=DETECTOR, 
            enforce_detection=True, 
            align=True
        )
        
        if not embeddings:
            write_face_debug("Kết quả: MTCNN không tìm thấy mặt")
            return {"status": "no_face", "embedding": []}

        write_face_debug(f"Kết quả: Thành công (Tìm thấy mặt với {DETECTOR})")
        return {
            "status": "success", 
            "embedding": embeddings[0]["embedding"],
            "facial_area": embeddings[0]["facial_area"]
        }

    except Exception as e:
        msg = str(e)
        if "Face could not be detected" in msg:
            write_face_debug(f"Kết quả: {DETECTOR} không phát hiện được mặt (mờ hoặc góc nghiêng quá lớn)")
            return {"status": "no_face", "embedding": []}
        
        write_face_debug(f"LỖI HỆ THỐNG: {msg}")
        raise HTTPException(status_code=500, detail=msg)
    finally:
        # Dọn dẹp file tạm sau mỗi request
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass

@app.post("/extract-face")
def extract_face(payload: ImagePayload):
    """Sử dụng để hiển thị ảnh khuôn mặt đã được bao khung trên Dashboard"""
    try:
        img_data = base64.b64decode(payload.image)
        nparr = np.frombuffer(img_data, np.uint8)
        img_orig = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Tiết kiệm tài nguyên: Dùng opencv detector cho việc vẽ khung preview nhanh
        # Nhưng request đối soát chính vẫn dùng MTCNN
        face_objs = DeepFace.extract_faces(
            img_path=img_orig,
            detector_backend=DETECTOR, 
            enforce_detection=False,
            align=False
        )
        
        if not face_objs:
             return {"status": "no_face", "image": ""}

        area = face_objs[0].get("facial_area", {})
        if area:
            x, y, w, h = area.get("x", 0), area.get("y", 0), area.get("w", 0), area.get("h", 0)
            cv2.rectangle(img_orig, (x, y), (x+w, y+h), (0, 255, 0), 3)
            cv2.putText(img_orig, "FACE", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        
        _, buffer = cv2.imencode('.jpg', img_orig)
        img_base64 = base64.b64encode(buffer).decode('utf-8')
        
        return {"status": "success", "image": img_base64}

    except Exception as e:
        write_face_debug(f"Extract-Face Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
