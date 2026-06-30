# Script khởi động 3 dịch vụ AI dùng 3 môi trường riêng biệt

# 1. Khởi động Plate API (Cổng 8001) - Dùng venv_plate
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv_plate\Scripts\python.exe src\plate_service.py" -WindowStyle Normal

# 2. Khởi động Face API (Cổng 8002) - Dùng venv_face
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv_face\Scripts\python.exe src\face_service.py" -WindowStyle Normal

# 3. Khởi động Backend Orchestrator (Cổng 8888) - Dùng venv_backend
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv_backend\Scripts\python.exe src\main_backend.py" -WindowStyle Normal

Write-Host "--- HỆ THỐNG ĐANG KHỞI ĐỘNG (MULTI-VENV MODE) ---" -ForegroundColor Cyan
Write-Host "Mời bạn truy cập: http://localhost:8888/dashboard/index.html" -ForegroundColor Green
