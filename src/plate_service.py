import os
import cv2
import numpy as np
import base64
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ultralytics import YOLO
from paddleocr import PaddleOCR
import re

import time
from dotenv import load_dotenv

# Cấu hình PaddleOCR
import paddle
if not hasattr(paddle.distributed, 'get_rank'):
    paddle.distributed.get_rank = lambda: 0
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_new_executor_serial_run"] = "1"
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'

# Logging paths
ROOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
load_dotenv(os.path.join(ROOT_DIR, "system.env"))
load_dotenv(os.path.join(ROOT_DIR, ".env"))
DEBUG_LOG_FILE = os.path.join(ROOT_DIR, "logs", "debug_plate.txt")
ERROR_LOG_FILE = os.path.join(ROOT_DIR, "logs", "error_log.txt")

def write_plate_debug(msg):
    """Ghi log an toàn cho dịch vụ biển số."""
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [PLATE] {msg}\n")
    except: pass
    print(f"PLATE_LOG: {msg}")

def write_error(msg):
    """Ghi log lỗi cho dịch vụ biển số."""
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [PLATE] ERROR: {msg}\n")
    except: pass
    print(f"PLATE_ERROR: {msg}")

app = FastAPI(title="Plate API (YOLO + PaddleOCR)")

# Load models at startup
MODEL_YOLO_PATH = os.path.join(ROOT_DIR, "models", "best.pt")
PADDING = 40
YOLO_CONF = 0.35  # Ngưỡng tin cậy detection

print("--- Initializing AI Models ---")
try:
    yolo_model = YOLO(MODEL_YOLO_PATH)
    write_plate_debug("✅ YOLO Model Loaded")
except Exception as e:
    print(f"❌ YOLO Load Error: {e}")
    yolo_model = None

try:
    # Cấu hình ổn định cho PaddleOCR 2.7.3
    ocr_engine = PaddleOCR(
        lang='en', 
        use_angle_cls=True, 
        use_gpu=False, 
        show_log=False,
        det_db_thresh=0.3,
        det_db_box_thresh=0.5
    )
    write_plate_debug("✅ PaddleOCR Engine Ready (v2.7.3 Stable)")
except Exception as e:
    print(f"❌ OCR Init Error: {e}")
    ocr_engine = None

class ImagePayload(BaseModel):
    image: str # Base64 string

def apply_vn_custom_rules(fp, fs, fn):
    DIGIT_FIX = {'B':'8', 'S':'5', 'G':'6', 'D':'0', 'O':'0', 'Q':'0', 'Z':'2', 'A':'4', 'T':'7'}
    # Bảng ánh xạ chuẩn hóa ký tự OCR thường gặp sai sót nét
    LETTER_FIX = {'8':'B', '5':'S', '0':'D', '2':'Z', '4':'A', '6':'G', '7':'T', '1':'I', '3':'B'} 
    
    # 1. Mã Tỉnh (fp) - BẮT BUỘC LÀ SỐ
    fp_chars = list(fp.ljust(2, '0')) 
    for i in range(2):
        if fp_chars[i] in DIGIT_FIX: fp_chars[i] = DIGIT_FIX[fp_chars[i]]
    fp_fixed = "".join(fp_chars)
    
    # 2. Mã Seri (fs) - Ký tự đầu BẮT BUỘC LÀ CHỮ
    fs_chars = list(fs)
    if len(fs_chars) > 0:
        if fs_chars[0] in LETTER_FIX: fs_chars[0] = LETTER_FIX[fs_chars[0]]
        # Ký tự đầu seri nếu nhận diện nhầm thành số 9 thì chuẩn hóa về P
        if fs_chars[0] == '9': fs_chars[0] = 'P'
        
    # Ký tự thứ 2 của seri (nếu có) có thể là Số (D1) hoặc Chữ (AB) -> ĐỂ NGUYÊN
    fs_fixed = "".join(fs_chars)
    
    # 3. Đuôi số (fn) - BẮT BUỘC LÀ SỐ
    fn_chars = list(fn)
    for i in range(len(fn_chars)):
        if fn_chars[i] in DIGIT_FIX: fn_chars[i] = DIGIT_FIX[fn_chars[i]]
    fn_fixed = "".join(fn_chars)
    
    return fp_fixed, fs_fixed, fn_fixed

def apply_ocr_tiers(img_crop):
    h, w = img_crop.shape[:2]
    scale = 2.5
    base = cv2.resize(img_crop, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_LANCZOS4)
    # Ngưỡng lọc nhiễu: Bỏ qua fragment nằm quá thấp (>90% chiều cao ảnh đã scale)
    max_cy = h * scale * 0.90
    all_fragments = []
    tiers = {
        'standard': base,
        'sharpen': cv2.filter2D(base, -1, np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])),
        'anti_glare': cv2.LUT(base, np.array([((i/255.0)**(1/0.45))*255 for i in np.arange(256)]).astype("uint8")),
        'clahe': cv2.cvtColor(cv2.merge(list(map(lambda c: cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(c), cv2.split(cv2.cvtColor(base, cv2.COLOR_BGR2LAB))))), cv2.COLOR_LAB2BGR)
    }

    for t_name, t_img in tiers.items():
        # PaddleOCR 3.x không dùng tham số cls trong hàm ocr()
        res = ocr_engine.ocr(t_img) 
        if res and res[0]:
            for line in res[0]:
                txt = line[1][0].upper().replace(" ", "").replace("-", "").replace(".", "")
                conf = line[1][1]
                cy = np.mean([p[1] for p in line[0]])
                if cy > max_cy: continue  # Lọc noise phía dưới ảnh
                all_fragments.append({'t': txt, 'sc': conf, 'cy': cy, 'tier': t_name})
    return all_fragments

@app.get("/")
def health():
    return {"status": "ready", "model": "YOLOv8 + PaddleOCR v2.6"}

@app.post("/predict")
def predict(payload: ImagePayload):
    if not yolo_model or not ocr_engine:
        write_error("AI System Not Ready (Models not loaded)")
        raise HTTPException(status_code=503, detail="AI System Not Ready")

    try:
        # Decode image
        img_data = base64.b64decode(payload.image)
        nparr = np.frombuffer(img_data, np.uint8)
        img_orig = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img_orig is None:
            raise HTTPException(status_code=400, detail="Invalid Image Data")

        # YOLO Prediction
        results = yolo_model.predict(img_orig, conf=YOLO_CONF, verbose=False) # Sử dụng ngưỡng YOLO_CONF mới
        if not results or len(results[0].boxes) == 0:
            write_error("YOLO: Không tìm thấy biển số xe")
            return {"plate": "No Plate Detected", "confidence": 0}

        box = results[0].boxes[0]
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        h_orig, w_orig = img_orig.shape[:2]
        
        # Crop with Padding
        x1_p, y1_p = max(0, x1-PADDING), max(0, y1-PADDING)
        x2_p, y2_p = min(w_orig, x2+PADDING), min(h_orig, y2+PADDING)
        crop = img_orig[y1_p:y2_p, x1_p:x2_p]

        # Encode crop even if OCR fails
        _, crop_buffer = cv2.imencode('.jpg', crop)
        crop_base64 = base64.b64encode(crop_buffer).decode('utf-8')

        # Multi-tier OCR
        fragments = apply_ocr_tiers(crop)
        if not fragments:
            return {"plate": "Không rõ", "confidence": 0, "crop": crop_base64}

        # Scoring logic
        y_coords = sorted([f['cy'] for f in fragments])
        mid_y = y_coords[len(y_coords)//2]
        p_sc, s_sc, n_sc = {}, {}, {}

        for f in fragments:
            txt = f['t']
            conf, cy, tier = f['sc'], f['cy'], f['tier']
            loc = 1 if cy < mid_y else 2
            
            if loc == 2:
                # Dòng dưới: trích xuất cụm số và chuẩn hóa
                num_m = re.search(r'[0-9A-Z]{4,5}', txt)
                if num_m:
                    num = num_m.group()
                    bonus = 150 if tier in ['anti_glare', 'clahe'] else 0
                    n_sc[num] = max(n_sc.get(num, 0), conf + 200 + bonus)
            else:
                clean_top = "".join(re.findall(r'[A-Z0-9]', txt))
                if len(clean_top) >= 4:
                    p_sc[clean_top[:2]] = max(p_sc.get(clean_top[:2], 0), conf + 100)
                    s_sc[clean_top[2:4]] = max(s_sc.get(clean_top[2:4], 0), conf + 100)
                elif len(clean_top) == 3:  # Xử lý trường hợp dòng trên 3 ký tự (VD: 85D)
                    p_sc[clean_top[:2]] = max(p_sc.get(clean_top[:2], 0), conf + 90)
                    s_sc[clean_top[2:]] = max(s_sc.get(clean_top[2:], 0), conf + 90)
                elif len(clean_top) <= 2 and len(clean_top) > 0:
                    if any(c.isdigit() for c in clean_top):
                        p_sc[clean_top] = max(p_sc.get(clean_top, 0), conf + 80)
                    else: 
                        s_sc[clean_top] = max(s_sc.get(clean_top, 0), conf + 80)

        fp = sorted(p_sc.items(), key=lambda x: x[1], reverse=True)[0][0] if p_sc else "??"
        fs = sorted(s_sc.items(), key=lambda x: x[1], reverse=True)[0][0] if s_sc else "??"
        fn = sorted(n_sc.items(), key=lambda x: x[1], reverse=True)[0][0] if n_sc else "?????"
        
        # Chuẩn hóa và sửa lỗi từng cụm biển số
        fp_fix, fs_fix, fn_fix = apply_vn_custom_rules(fp, fs, fn)
        raw_combined = f"{fp_fix}{fs_fix}{fn_fix}"
        
        # Định dạng chuẩn biển số xe
        pretty_plate = f"{fp_fix}-{fs_fix} {fn_fix}"
        if len(fn_fix) == 5:
            pretty_plate = f"{fp_fix}-{fs_fix} {fn_fix[:3]}.{fn_fix[3:]}"

        # Encode crop to base64
        _, crop_buffer = cv2.imencode('.jpg', crop)
        crop_base64 = base64.b64encode(crop_buffer).decode('utf-8')

        return {
            "plate": pretty_plate, 
            "raw": raw_combined,
            "crop": crop_base64
        }

    except Exception as e:
        write_error(f"Lỗi Plate API Request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
