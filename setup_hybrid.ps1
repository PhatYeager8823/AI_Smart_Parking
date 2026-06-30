Write-Host "--- Đang thiết lập hệ thống 3 lớp (3-Venv Architecture) ---" -ForegroundColor Cyan

# 1. Tạo và cài đặt cho Backend
Write-Host "[1/3] Cài đặt Backend..." -ForegroundColor Yellow
python -m venv venv_backend
.\venv_backend\Scripts\python.exe -m pip install --upgrade pip
.\venv_backend\Scripts\pip.exe install -r requirements\requirements_backend.txt uvicorn

# 2. Tạo và cài đặt cho Plate API (Biển số)
Write-Host "[2/3] Cài đặt Plate API (Dùng PaddlePaddle bản mới nhất)..." -ForegroundColor Yellow
python -m venv venv_plate
.\venv_plate\Scripts\python.exe -m pip install --upgrade pip
.\venv_plate\Scripts\pip.exe install -r requirements\requirements_plate.txt ultralytics

# 3. Tạo và cài đặt cho Face API (Khuôn mặt)
Write-Host "[3/3] Cài đặt Face API (Dùng TensorFlow + Protobuf 3.19)..." -ForegroundColor Yellow
python -m venv venv_face
.\venv_face\Scripts\python.exe -m pip install --upgrade pip
.\venv_face\Scripts\pip.exe install -r requirements\requirements_face.txt
.\venv_face\Scripts\pip.exe install "protobuf==3.19.6"

Write-Host "--- THIẾT LẬP HOÀN TẤT! ---" -ForegroundColor Green
