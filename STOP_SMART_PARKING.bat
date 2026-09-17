@echo off
title Smart Park AI - Shutdown System
color 0C

echo ===================================================
echo      DANG TAT HE THONG SMART PARK AI (NHOM 9)
echo ===================================================
echo.

echo [1/3] Dang xoa cac Container Docker (Don dep sach)...
if exist system.env (
    docker compose --env-file system.env down
) else (
    docker compose down
)
echo.

echo [2/3] Dang tat cac dich vu AI (Python)...
taskkill /f /im python.exe /t >nul 2>&1
echo Cac dich vu Backend, Plate, Face da dung.
echo.

echo [3/3] Dang tat Ngrok Tunnel...
taskkill /f /im ngrok.exe /t >nul 2>&1
echo Ngrok da dong.
echo.

echo ===================================================
echo DA DON DEP XONG! CAM ON BAN DA SU DUNG HE THONG.
echo ===================================================
timeout /t 5
exit
