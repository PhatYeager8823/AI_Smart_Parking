# 🅿️ AI Smart Parking — Hệ Thống Bãi Đỗ Xe Thông Minh (Edition A+)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white"/>
  <img src="https://img.shields.io/badge/PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white"/>
  <img src="https://img.shields.io/badge/Qdrant-DC244C?style=for-the-badge&logo=qdrant&logoColor=white"/>
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white"/>
  <img src="https://img.shields.io/badge/YOLOv8-FF5500?style=for-the-badge&logo=yolo&logoColor=white"/>
</p>

> Hệ thống quản lý bãi đỗ xe tích hợp AI toàn diện: nhận diện khuôn mặt sinh trắc học, đọc biển số xe tự động (LPR), kiến trúc bảo mật 3 lớp (Triple-Defense), hỗ trợ 2 làn vào/ra độc lập và dashboard giám sát thời gian thực (Real-time WebSocket). Đồ án thực tập tốt nghiệp.

---

## 📋 Mục Lục

- [Tổng Quan](#-tổng-quan)
- [Kiến Trúc Hệ Thống](#-kiến-trúc-hệ-thống)
- [Kiến Trúc Đa Môi Trường (3-Venv Hybrid)](#-kiến-trúc-đa-môi-trường-3-venv-hybrid)
- [Tính Năng Nổi Bật](#-tính-năng-nổi-bật)
- [Công Nghệ Sử Dụng](#-công-nghệ-sử-dụng)
- [Cổng Dịch Vụ & Danh Sách URL](#-cổng-dịch-vụ--danh-sách-url)
- [Hướng Dẫn Cài Đặt & Vận Hành](#-hướng-dẫn-cài-đặt--vận-hành)
- [Cấu Trúc Thư Mục](#-cấu-trúc-thư-mục)
- [Cơ Chế Bảo Mật 3 Lớp](#-cơ-chế-bảo-mật-3-lớp)
- [Xử Lý Kịch Bản Ngoại Lệ](#-xử-lý-kịch-bản-ngoại-lệ)
- [Tác Giả & Bản Quyền](#-tác-giả--bản-quyền)

---

## 🎯 Tổng Quan

**AI Smart Parking** là hệ thống quản lý bãi đỗ xe thế hệ mới, ứng dụng trí tuệ nhân tạo để tự động hóa toàn diện quy trình kiểm soát phương tiện vào/ra. Thay vì phụ thuộc vào thẻ từ RFID hoặc vé giấy truyền thống (dễ mất mát, dễ làm giả, dễ tráo xe), hệ thống kết hợp **nhận diện biển số xe (YOLOv8 + PaddleOCR)** và **nhận diện khuôn mặt (DeepFace FaceNet512 + Qdrant Vector Search)** làm định danh sinh trắc học kép.

### Điểm khác biệt cốt lõi
- 🧠 **No-Touch AI Autonomous**: Không cần chạm tay — đứng trước camera, hệ thống tự động nhận diện và phân tích.
- 🔐 **Triết lý "Khuôn mặt là CCCD"**: Kiểm soát quyền sở hữu tài sản dựa trên dữ liệu đối soát sinh trắc học, chống triệt để tình trạng tráo biển số, tráo xe.
- ⚡ **Zero-Latency Cloud Storage**: Tác vụ đồng bộ ảnh lên Cloudinary chạy hoàn toàn trên background thread; cổng barie mở ngay khi xác thực thành công.
- 📡 **Real-time WebSocket Engine**: Cập nhật trạng thái phương tiện, ảnh đối chiếu và bảng nhật ký trên dashboard tức thì (~0ms).
- 🏢 **Hỗ trợ Hộ gia đình (Family Vehicles)**: Cho phép nhiều thành viên trong cùng một hộ chia sẻ quyền gửi/lấy danh sách xe của hộ.

---

## 🏗️ Kiến Trúc Hệ Thống

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       DISTRIBUTED SYSTEM ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [Trạm Làn VÀO]                 [Core Backend]            [Trạm Làn RA]     │
│  index.html?lane=IN            main_backend.py            index.html?lane=OUT│
│  MediaPipe Client AI   ◄──WS──► FastAPI (Port 8888) ◄──WS──►MediaPipe Client│
│  Camera Làn Vào                 State & Session Engine    Camera Làn Ra     │
│                                        ▲                                    │
│                        ┌───────────────┼───────────────┐                    │
│                        ▼               ▼               ▼                    │
│                 [Plate Service]  [Face Service]  [Databases]                │
│                 Port 8001        Port 8002       PostgreSQL (Port 5432)     │
│                 YOLOv8 + Paddle  DeepFace + MTCNN Qdrant (Port 6333)        │
│                                                  Cloudinary Storage         │
│                                                                             │
│                        ┌───────────────────────────────┐                    │
│                        │       Admin Management        │                    │
│                        │  admin.html | pgAdmin (5050)  │                    │
│                        └───────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🐍 Kiến Trúc Đa Môi Trường (3-Venv Hybrid)

Để giải quyết triệt để xung đột thư viện giữa các nền tảng AI (đặc biệt là xung đột `protobuf`, `numpy`, `opencv` giữa **PaddlePaddle** và **TensorFlow/DeepFace**), dự án tách biệt thành 3 môi trường ảo độc lập:

| Môi trường | Thư mục | Port | Nhiệm vụ chính | Thư viện cốt lõi |
|---|---|---|---|---|
| **Backend Orchestrator** | `venv_backend/` | `8888` | Điều phối logic, WebSocket, Quản lý DB & Cloud | `fastapi`, `psycopg2`, `qdrant-client`, `cloudinary` |
| **Plate Recognition** | `venv_plate/` | `8001` | Phát hiện và nhận diện ký tự biển số xe | `ultralytics` (YOLOv8), `paddleocr`, `paddlepaddle` |
| **Face Verification** | `venv_face/` | `8002` | Trích xuất vector đặc trưng khuôn mặt 512D | `deepface`, `tensorflow`, `mtcnn` |

---

## ✨ Tính Năng Nổi Bật

### 🤖 AI & Computer Vision
1. **Chụp ảnh tự động (No-Touch AI)**:
   - **Lọc khoảng cách**: Chỉ kích hoạt khi tỷ lệ khuôn mặt chiếm >22% khung hình.
   - **Lọc độ ổn định**: So sánh vị trí khuôn mặt qua các frame liên tiếp; chỉ chụp khi đứng yên ổn định.
   - Giảm hơn 80% lưu lượng mạng và tải xử lý cho server.
2. **Quy tắc chuẩn hóa biển số Việt Nam**:
   - Tự động tách 3 cụm: Mã tỉnh (2 số) - Seri đăng ký (chữ + số/chữ) - Số thứ tự (4 hoặc 5 số).
   - Bảng ánh xạ sửa lỗi nét quang học thường gặp (8/B, 5/S, 0/D, 2/Z, 1/I, 3/B, 9/P).
3. **Cơ chế phân vùng xác thực (3-Zone Model)**:
   - **Vùng Xanh (>= 75%)**: Xác thực thành công, tự động mở barie.
   - **Vùng Vàng (50% - 74%)**: Nghi vấn, hiển thị modal yêu cầu bảo vệ bấm nút xác nhận hoặc quét lại.
   - **Vùng Đỏ (< 50%)**: Không khớp danh tính; làn Vào tạo phiên khách mới, làn Ra kích hoạt cảnh báo an ninh.

### 🛡️ Cảnh báo & Giám sát
- 🚨 **Red Alert System**: Rung màn hình giám sát, nhấp nháy viền cảnh báo đỏ và phát còi báo động qua Web Audio API.
- 📸 **Bằng chứng đối chiếu song song**: Hiển thị đồng thời ảnh camera vừa chụp và ảnh đại diện lúc đăng ký trong cơ sở dữ liệu.
- 💰 **Tính toán phí gửi xe linh hoạt**: Miễn phí cho cư dân đã đóng phí tháng; tự động tính phí theo khung giờ và phụ thu qua đêm cho khách vãng lai.

---

## 🛠️ Công Nghệ Sử Dụng

| Tầng | Công nghệ | Chi tiết sử dụng |
|---|---|---|
| **Web Framework** | FastAPI, Uvicorn | Xây dựng Microservices và Orchestrator API |
| **Cơ sở dữ liệu Quan hệ** | PostgreSQL 15 | Lưu trữ bảng người dùng, hộ gia đình, danh sách xe, nhật ký giao dịch |
| **Vector Database** | Qdrant v1.13 | Tìm kiếm tương đồng vector khuôn mặt 512D với khoảng cách Cosine |
| **Thị giác máy tính** | YOLOv8, PaddleOCR | Nhận diện vùng biển số và bóc tách ký tự OCR tiếng Việt |
| **Nhận diện khuôn mặt** | DeepFace (FaceNet512, MTCNN) | Trích xuất vector đặc trưng sinh trắc học chất lượng cao |
| **Client-Side AI** | MediaPipe Face Detection | Bắt khuôn mặt trực tiếp trên trình duyệt bằng WebAssembly |
| **Lưu trữ Cloud** | Cloudinary SDK | Tự động lưu trữ và phân loại hình ảnh giao dịch theo ngày |
| **Ảo hóa & Vận hành** | Docker Compose | Triển khai nhanh PostgreSQL, Qdrant và pgAdmin |

---

## 🌐 Cổng Dịch Vụ & Danh Sách URL

Sau khi khởi động hệ thống, các dịch vụ sẽ hoạt động tại các địa chỉ sau:

| Dịch vụ / Giao diện | Địa chỉ URL | Mô tả |
|---|---|---|
| **Dual-Lane Dashboard** | `http://localhost:8888/dashboard/index.html` | Màn hình chính điều khiển đồng thời 2 làn Vào/Ra |
| **Trạm Làn Vào (IN)** | `http://localhost:8888/dashboard/index.html?lane=IN` | Giao diện riêng cho chốt kiểm soát làn Vào |
| **Trạm Làn Ra (OUT)** | `http://localhost:8888/dashboard/index.html?lane=OUT` | Giao diện riêng cho chốt kiểm soát làn Ra |
| **Đăng ký Hộ gia đình (Admin)** | `http://localhost:8888/dashboard/admin.html` | Thêm hộ dân, thành viên, biển số và ảnh mẫu |
| **Mobile Scanner** | `http://localhost:8888/dashboard/mobile.html` | Giao diện điện thoại chụp biển số cơ động |
| **Orchestrator Swagger Docs** | `http://localhost:8888/docs` | Tài liệu API điều phối chính |
| **Plate API Swagger Docs** | `http://localhost:8001/docs` | Tài liệu API nhận diện biển số |
| **Face API Swagger Docs** | `http://localhost:8002/docs` | Tài liệu API vector khuôn mặt |
| **Qdrant Vector Dashboard** | `http://localhost:6333/dashboard` | Giao diện quản trị Vector Database |
| **pgAdmin 4** | `http://localhost:5050` | Quản trị PostgreSQL (User: `admin@admin.com`, Pass: `admin`) |

---

## 🚀 Hướng Dẫn Cài Đặt & Vận Hành

### Yêu cầu tiên quyết
- **Hệ điều hành**: Windows 10 / 11 (hoặc Linux / macOS tương đương)
- **Python**: 3.10.x
- **Docker Desktop**: Đã cài đặt và đang chạy
- **Git**: Đã cài đặt

---

### Bước 1: Clone Repository

```bash
git clone https://github.com/PhatYeager8823/AI_Smart_Parking.git
cd AI_Smart_Parking
```

---

### Bước 2: Thiết lập Biến Môi Trường (.env)

Tạo file cấu hình từ file mẫu `.env.example`:

```powershell
# Trên Windows PowerShell / Command Prompt:
copy .env.example system.env
copy .env.example .env
```

Mở file `system.env` và cập nhật các khóa Cloudinary nếu muốn kích hoạt tính năng sao lưu ảnh lên Cloud:
```ini
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

---

### Bước 3: Khởi động Cơ sở Dữ liệu với Docker

Chạy lệnh Docker Compose để tạo PostgreSQL, Qdrant và pgAdmin:

```bash
docker compose up -d
```

Kiểm tra trạng thái container:
```bash
docker compose ps
```
> Khi khởi chạy lần đầu, container `parking_db` sẽ tự động nạp toàn bộ cấu trúc bảng từ `database/database_setup.sql`.

---

### Bước 4: Tạo 3 Môi Trường Ảo (Chỉ cần chạy 1 lần đầu)

Chạy script cài đặt tự động bằng PowerShell:

```powershell
.\setup_hybrid.ps1
```

Script sẽ tự động:
1. Tạo `venv_backend` và cài đặt `requirements_backend.txt`.
2. Tạo `venv_plate` và cài đặt `requirements_plate.txt` cùng YOLOv8.
3. Tạo `venv_face` và cài đặt `requirements_face.txt`, `tensorflow`, `protobuf==3.19.6`.

---

### Bước 5: Khởi Động Toàn Bộ Hệ Thống

#### Cách 1: Khởi động 1-Click (Khuyên dùng trên Windows)
Nhấp đúp chuột vào file hoặc chạy qua terminal:
```cmd
RUN_SMART_PARKING.bat
```
Script sẽ khởi động Docker, 3 dịch vụ Python trong các cửa sổ riêng biệt, mở Ngrok và tự động mở các tab trình duyệt quản lý.

#### Cách 2: Khởi động bằng PowerShell
```powershell
.\start_hybrid.ps1
```
Sau đó truy cập: `http://localhost:8888/dashboard/index.html`

---

### Bước 6: Dừng Hệ Thống

Khi muốn tắt toàn bộ hệ thống và dọn dẹp các tiến trình:
```cmd
STOP_SMART_PARKING.bat
```

---

## 📁 Cấu Trúc Thư Mục

```
AI_Smart_Parking/
├── dashboard/
│   ├── index.html              # Màn hình điều phối 2 làn (Dual-Lane Dashboard)
│   ├── admin.html              # Trang quản lý & đăng ký hộ gia đình cư dân
│   ├── mobile.html             # Trang quét biển số trên thiết bị di động
│   ├── style.css               # Giao diện Glassmorphism hiện đại
│   └── state.json              # File cache trạng thái phiên
├── database/
│   └── database_setup.sql      # Kịch bản khởi tạo bảng PostgreSQL (Docker entrypoint)
├── docs/
│   └── phan_tich_thiet_ke_Al_Smart_Parking.md # Báo cáo phân tích thiết kế chi tiết
├── models/
│   └── best.pt                 # Trọng số YOLOv8 nhận diện biển số xe
├── requirements/
│   ├── requirements_backend.txt# Thư viện cho Orchestrator Backend
│   ├── requirements_face.txt   # Thư viện cho Face Service (TensorFlow/DeepFace)
│   └── requirements_plate.txt  # Thư viện cho Plate Service (PaddleOCR/YOLO)
├── src/
│   ├── main_backend.py         # Bộ điều phối trung tâm (FastAPI + WebSocket)
│   ├── db_manager.py           # Lớp kết nối PostgreSQL và Qdrant
│   ├── face_service.py         # Microservice trích xuất vector khuôn mặt
│   ├── plate_service.py        # Microservice bóc tách biển số xe
│   └── liveness_detector.py    # Module kiểm tra độ sống khuôn mặt (Anti-spoofing)
├── .env.example                # Mẫu cấu hình biến môi trường
├── .gitignore                  # Cấu hình bỏ qua file nhị phân và cache
├── docker-compose.yml          # Cấu hình container Database & pgAdmin
├── servers.json                # Cấu hình tự động kết nối DB cho pgAdmin
├── setup_hybrid.ps1            # Script khởi tạo 3 môi trường ảo tự động
├── start_hybrid.ps1            # Script kích hoạt 3 dịch vụ AI
├── RUN_SMART_PARKING.bat       # Script khởi động trọn gói 1-Click
├── STOP_SMART_PARKING.bat      # Script dừng và dọn dẹp tiến trình
└── README.md                   # Tài liệu hướng dẫn dự án
```

---

## 🛡️ Cơ Chế Bảo Mật 3 Lớp (Triple-Defense)

```
       Yêu cầu vào/ra phương tiện
                  │
                  ▼
┌───────────────────────────────────────┐
│     LỚP 1: RAM Queue Guard            │ ➔ Chặn Spam, chống DDoS hàng chờ
│     Kiểm tra biển số đang đợi         │
└──────────────────┬────────────────────┘
                   │ ĐẠT
                   ▼
┌───────────────────────────────────────┐
│     LỚP 2: SQL Physics Guard          │ ➔ Kiểm soát logic vật lý ra/vào
│     Kiểm tra trạng thái xe trong bãi  │    (Chống lỗi Ghost Car)
└──────────────────┬────────────────────┘
                   │ ĐẠT
                   ▼
┌───────────────────────────────────────┐
│     LỚP 3: CCCD Identity Guard        │ ➔ Đối soát quyền sở hữu sinh trắc
│     Khuôn mặt người lấy = Người gửi?  │    (Chống tráo xe, kẻ gian lấy cắp)
└──────────────────┬────────────────────┘
                   │ ĐẠT
                   ▼
             🔓 MỞ BARIE
```

---

## ⚠️ Xử Lý Kịch Bản Ngoại Lệ

| Tình huống ngoại lệ | Lớp phát hiện | Hành động xử lý của hệ thống |
|---|---|---|
| **Ghost Car** (Xe chưa vào nhưng xin ra) | Lớp 2 — SQL Physics | Báo cảnh báo `XE CHƯA VÀO BÃI`, từ chối mở cổng, ghi log vi phạm. |
| **Car Re-entry** (Xe đang trong bãi lại xin vào) | Lớp 2 — SQL Physics | Cảnh báo `XE ĐÃ TRONG BÃI`, yêu cầu kiểm tra thực tế tại chốt. |
| **Identity Swap** (Kẻ lạ lấy xe cư dân/khách) | Lớp 3 — CCCD Identity | Kích hoạt `Red Alert`: Rung màn hình, hú còi, hiển thị `SAI CHỦ TÀI SẢN`, lưu ảnh chụp kẻ gian vào nhật ký. |
| **Khuôn mặt chưa từng đăng ký (Làn Ra)** | Lớp 3 — Qdrant Search | Từ chối với mã trạng thái `FAILED_UNKNOWN_FACE`, cảnh báo kẻ gian xâm nhập. |
| **Người trong cùng hộ lấy xe của nhau** | Lớp 3 — Family Linking | Truy vấn bảng `family_vehicles` và `families`: Xác nhận hợp lệ và cho phép lấy xe bình thường. |
| **Spam request hàng đợi** | Lớp 1 — RAM Queue | Từ chối ngay tại bộ nhớ tạm nếu biển số đó đang trong phiên xử lý dở. |

---

## 👨‍💻 Tác Giả & Bản Quyền

- **Tác giả**: Dương Thịnh Phát
- **Đồ án**: Thực tập tốt nghiệp — Hệ thống Quản lý Bãi đỗ xe Thông minh sử dụng Trí tuệ Nhân tạo (AI Smart Parking)
- **Giấy phép**: MIT License
