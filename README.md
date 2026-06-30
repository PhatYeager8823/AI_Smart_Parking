# 🅿️ AI Smart Parking — Hệ Thống Bãi Đỗ Xe Thông Minh (Edition A+)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white"/>
  <img src="https://img.shields.io/badge/PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white"/>
  <img src="https://img.shields.io/badge/Qdrant-DC244C?style=for-the-badge&logo=qdrant&logoColor=white"/>
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white"/>
  <img src="https://img.shields.io/badge/YOLOv8-FF5500?style=for-the-badge&logo=yolo&logoColor=white"/>
</p>

> Hệ thống quản lý bãi đỗ xe tích hợp AI toàn diện: nhận diện khuôn mặt, đọc biển số xe tự động, bảo mật 3 lớp và dashboard giám sát thời gian thực. Đồ án thực tập tốt nghiệp.

---

## 📋 Mục Lục

- [Tổng Quan](#-tổng-quan)
- [Kiến Trúc Hệ Thống](#-kiến-trúc-hệ-thống)
- [Tính Năng Nổi Bật](#-tính-năng-nổi-bật)
- [Công Nghệ Sử Dụng](#-công-nghệ-sử-dụng)
- [Cài Đặt & Chạy](#-cài-đặt--chạy)
- [Cấu Trúc Thư Mục](#-cấu-trúc-thư-mục)
- [Bảo Mật 3 Lớp](#-bảo-mật-3-lớp)
- [Xử Lý Kịch Bản Ngoại Lệ](#-xử-lý-kịch-bản-ngoại-lệ)

---

## 🎯 Tổng Quan

**AI Smart Parking** là hệ thống quản lý bãi đỗ xe thế hệ mới, ứng dụng trí tuệ nhân tạo để tự động hóa hoàn toàn quy trình ra/vào bãi xe. Thay vì dùng thẻ từ hay vé giấy truyền thống, hệ thống sử dụng **khuôn mặt** và **biển số xe** làm phương thức định danh.

### Điểm khác biệt cốt lõi
- 🧠 **No-Touch AI**: Không cần chạm tay — chỉ cần đứng trước camera, hệ thống tự nhận diện
- 🔐 **Triết lý "Khuôn mặt là CCCD"**: Bảo vệ tài sản dựa trên danh tính sinh trắc học
- ⚡ **Zero-Latency**: Upload ảnh cloud chạy ngầm, barie mở ngay lập tức sau xác thực
- 📡 **WebSocket Real-time**: Đồng bộ trạng thái toàn hệ thống với độ trễ ~0ms

---

## 🏗️ Kiến Trúc Hệ Thống

```
┌─────────────────────────────────────────────────────────┐
│                    DISTRIBUTED ARCHITECTURE              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [Trạm VÀO]          [Core Backend]        [Trạm RA]   │
│  index.html          main_backend.py       index.html   │
│  ?lane=IN   ◄──WS──► FastAPI + WebSocket ◄──WS──►      │
│  MediaPipe           PostgreSQL + Qdrant    ?lane=OUT   │
│  (Client AI)         YOLOv8 + DeepFace     (Client AI) │
│                             │                           │
│                    ┌────────┴────────┐                  │
│                    │  Admin Dashboard│                  │
│                    │  admin.html     │                  │
│                    │  Real-time Log  │                  │
│                    └─────────────────┘                  │
└─────────────────────────────────────────────────────────┘
```

### Các thành phần chính

| Component | File | Vai trò |
|-----------|------|---------|
| **Core Orchestrator** | `src/main_backend.py` | Điều phối trung tâm, WebSocket engine, State management |
| **Data Layer** | `src/db_manager.py` | Quản lý PostgreSQL + Qdrant, đối soát lịch sử |
| **Client AI** | `dashboard/index.html` | MediaPipe face detection trên trình duyệt |
| **Admin Dashboard** | `dashboard/admin.html` | Giám sát thời gian thực |
| **Face Service** | `src/face_service.py` | DeepFace FaceNet512 embedding |
| **Plate Service** | `src/plate_service.py` | YOLOv8 + PaddleOCR biển số |

---

## ✨ Tính Năng Nổi Bật

### 🤖 AI Innovations

**1. Chụp ảnh Tự động (No-Touch Autonomous)**
- **Phễu lọc 1 — Khoảng cách**: Chỉ kích hoạt khi khuôn mặt chiếm >22% khung hình
- **Phễu lọc 2 — Độ ổn định**: So sánh tọa độ X-Y liên tiếp, chụp khi đứng yên ổn định
- Giảm 80% tải cho Backend so với gửi ảnh liên tục

**2. Red Alert System — Báo động Đa phương thức**
- 🔊 **Siren**: Hú còi báo động (Oscillator sawtooth wave — Web Audio API)
- 📺 **Shake Alert**: Rung lắc màn hình giám sát để cảnh báo bảo vệ

**3. Background Archiving — Lưu trữ Cloud Zero-Latency**
- Upload ảnh Cloudinary chạy trên luồng ngầm (`Threading`)
- Barie mở ngay sau xác thực, không chờ tải lên mạng
- Ảnh phân loại tự động theo ngày: `smart_parking/storage/DD-MM-YYYY/`

### 🚗 Tính năng hệ thống

- ✅ Nhận diện biển số xe (YOLOv8 + PaddleOCR)
- ✅ Xác thực khuôn mặt chủ xe (DeepFace FaceNet512, vector 512 chiều)
- ✅ Kiểm soát vào/ra độc lập theo 2 làn (URL: `?lane=IN` / `?lane=OUT`)
- ✅ Dashboard admin giám sát toàn bộ nhật ký thời gian thực
- ✅ Lưu trữ ảnh tự động lên Cloudinary
- ✅ Phát hiện và cảnh báo hành vi gian lận (tráo xe, kẻ lạ)

---

## 🛠️ Công Nghệ Sử Dụng

### Backend & AI
| Công nghệ | Mục đích |
|-----------|----------|
| **FastAPI** | API framework hiệu năng cao |
| **PostgreSQL 15** | Lưu nhật ký giao dịch, thông tin người dùng |
| **Qdrant v1.13** | Vector database lưu embedding khuôn mặt 512 chiều |
| **DeepFace (FaceNet512)** | Trích xuất đặc trưng khuôn mặt |
| **YOLOv8** | Phát hiện và nhận diện biển số xe |
| **PaddleOCR** | OCR đọc ký tự biển số |
| **Cloudinary SDK** | Lưu trữ ảnh trên cloud |
| **WebSocket** | Giao tiếp thời gian thực |

### Frontend & Client AI
| Công nghệ | Mục đích |
|-----------|----------|
| **MediaPipe Tasks Vision** | Face detection trực tiếp trên trình duyệt |
| **Web Audio API** | Tạo âm thanh cảnh báo |
| **Glassmorphism 2.0** | Giao diện hiện đại, chuyên nghiệp |

### Infrastructure
| Công nghệ | Mục đích |
|-----------|----------|
| **Docker Compose** | Orchestrate PostgreSQL + Qdrant + pgAdmin |
| **pgAdmin 4** | Quản lý database trực quan |

---

## 🚀 Cài Đặt & Chạy

### Yêu cầu
- Python 3.10+
- Docker Desktop
- Git

### Bước 1: Clone repository
```bash
git clone https://github.com/PhatYeager8823/AI_Smart_Parking.git
cd AI_Smart_Parking
```

### Bước 2: Cấu hình môi trường
```bash
# Sao chép file .env mẫu
copy .env.example .env
# Chỉnh sửa .env với thông tin của bạn (DB, Cloudinary API key, v.v.)
```

### Bước 3: Khởi động Database (Docker)
```bash
docker-compose up -d
```
> PostgreSQL: `localhost:5432` | Qdrant: `localhost:6333` | pgAdmin: `http://localhost:5050`

### Bước 4: Cài đặt dependencies
```bash
# Backend chính
pip install -r requirements/requirements_backend.txt

# Face recognition service
pip install -r requirements/requirements_face.txt

# Plate recognition service
pip install -r requirements/requirements_plate.txt
```

### Bước 5: Chạy hệ thống
```bash
# Windows — chạy toàn bộ hệ thống tự động
.\RUN_SMART_PARKING.bat
```
Hoặc chạy PowerShell:
```powershell
.\start_hybrid.ps1
```

### Truy cập
| Endpoint | URL |
|----------|-----|
| Trạm VÀO | `http://localhost:8000/?lane=IN` |
| Trạm RA | `http://localhost:8000/?lane=OUT` |
| Admin Dashboard | `http://localhost:8000/admin` |
| API Docs | `http://localhost:8000/docs` |

---

## 📁 Cấu Trúc Thư Mục

```
AI_Smart_Parking/
├── src/
│   ├── main_backend.py        # Core Orchestrator (FastAPI + WebSocket)
│   ├── db_manager.py          # Data Layer (PostgreSQL + Qdrant)
│   ├── face_service.py        # DeepFace embedding service
│   ├── plate_service.py       # YOLOv8 + PaddleOCR service
│   ├── liveness_detector.py   # Anti-spoofing detector
│   └── select_camera.py       # Camera selection utility
├── dashboard/
│   ├── index.html             # Giao diện trạm vào/ra (Client AI)
│   ├── admin.html             # Dashboard giám sát admin
│   ├── mobile.html            # Giao diện mobile
│   └── style.css              # Glassmorphism UI styles
├── database/
│   └── database_setup.sql     # Schema khởi tạo PostgreSQL
├── requirements/
│   ├── requirements_backend.txt
│   ├── requirements_face.txt
│   └── requirements_plate.txt
├── docs/
│   └── phan_tich_thiet_ke_Al_Smart_Parking.md
├── docker-compose.yml         # PostgreSQL + Qdrant + pgAdmin
├── RUN_SMART_PARKING.bat      # Script khởi động Windows
├── STOP_SMART_PARKING.bat     # Script dừng hệ thống
├── .env.example               # Mẫu biến môi trường
└── README.md
```

---

## 🛡️ Bảo Mật 3 Lớp

```
REQUEST
   │
   ▼
┌─────────────────────────────────┐
│  LỚP 1: RAM Queue Guard         │  Chống Spam/DDoS hàng chờ
│  Kiểm tra biển số đang chờ      │
└────────────────┬────────────────┘
                 │ PASS
                 ▼
┌─────────────────────────────────┐
│  LỚP 2: SQL Physics Guard       │  Kiểm soát trạng thái vật lý
│  Xe đã vào? Xe chưa vào?        │  (chống Ghost Car)
└────────────────┬────────────────┘
                 │ PASS
                 ▼
┌─────────────────────────────────┐
│  LỚP 3: CCCD Identity Guard     │  Đối soát danh tính sinh trắc
│  Khuôn mặt = Chủ xe?            │  (chống tráo xe, kẻ lạ)
└────────────────┬────────────────┘
                 │ PASS
                 ▼
            🔓 MỞ BARIE
```

---

## ⚠️ Xử Lý Kịch Bản Ngoại Lệ

| Kịch bản | Phát hiện | Phản hồi |
|----------|-----------|----------|
| **Ghost Car** (xe chưa vào xin ra) | Lớp 2 — SQL Physics | ❌ `XE KHÔNG TRONG BÃI` |
| **Identity Swap** (tráo xe/ăn cắp) | Lớp 3 — CCCD Identity | 🚨 `SAI CHỦ TÀI SẢN` + Red Alert + Lưu ảnh kẻ gian |
| **Unknown Intruder** (khuôn mặt lạ) | Lớp 3 — Qdrant similarity | ❌ `CCCD KHÔNG HỢP LỆ` |
| **DDoS Spam** (spam biển số) | Lớp 1 — RAM Queue | ❌ Từ chối ngay, bảo vệ tài nguyên |

---

## 👨‍💻 Tác Giả

**Dương Thịnh Phát** — Đồ án Thực tập Tốt nghiệp

---

## 📄 License

MIT License — Free to use for educational purposes.
