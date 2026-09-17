@echo off
title Smart Park AI - Master Launcher
color 0B

echo ===================================================
echo      KHOI DONG HE THONG SMART PARK AI (NHOM 9)
echo ===================================================
echo.

echo [1/4] Kiem tra va khoi dong Docker (PostgreSQL ^& Qdrant)...
:: Tu dong mo Docker Desktop
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
echo Vui long doi 10 giay de Docker load...
timeout /t 10 /nobreak > NUL
echo Kich hoat cac Container Database...
if exist system.env (
    docker compose --env-file system.env up -d
) else if exist .env (
    docker compose --env-file .env up -d
) else (
    docker compose up -d
)

echo.
echo [2/4] Kich hoat 3 dich vu loi (Backend, Plate, Face)...
:: Chay file ps1 cua ban trong mot cua so rieng
start "AI Services" powershell.exe -ExecutionPolicy Bypass -File ".\start_hybrid.ps1"

echo Dang cho Server 8888 san sang (10 giay)...
timeout /t 10 /nobreak > NUL

echo.
echo [3/4] Kich hoat Ngrok Tunnel cho Mobile...
if exist .\ngrok.exe (
    start "Ngrok Tunnel" .\ngrok.exe http 8888
) else (
    echo [Luu y: Khong tim thay ngrok.exe, he thong se chay che do Localhost tren may]
)

echo.
echo [4/4] Mo Giao dien quan ly (Dashboard)...
echo Mo Giao dien Dual-Lane...
start "" "http://localhost:8888/dashboard/index.html"
timeout /t 1 /nobreak > NUL

echo Mo tab Dang ky Ho gia dinh (Admin)...
start "" "http://localhost:8888/dashboard/admin.html"
timeout /t 1 /nobreak > NUL

echo Mo tab Quan tri (pgAdmin & Qdrant)...
start "" "http://localhost:5050"
timeout /t 1 /nobreak > NUL
start "" "http://localhost:6333/dashboard"

echo.
echo ===================================================
echo HOAN TAT! HE THONG DA SAN SANG DE BAO VE.
echo De tat he thong, chi can tat cac cua so mau den.
echo Chuc Nhom 9 bao ve do an thanh cong ruc ro!
echo ===================================================
pause
