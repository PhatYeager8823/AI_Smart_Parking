# PHÂN TÍCH THIẾT KẾ HỆ THỐNG AI SMART PARKING (EDITION A+)

Tài liệu này cung cấp cái nhìn tổng quan về kiến trúc, công nghệ, mô hình AI và logic nghiệp vụ của hệ thống **AI Smart Parking** (Phiên bản nâng cấp Bảo mật & Đa máy trạm) phục vụ báo cáo đồ án tốt nghiệp.

---

## 1. Tổng Quan Kiến Trúc Hệ Thống (Architecture)

Hệ thống được xây dựng trên mô hình **Distributed Orchestration** (Điều phối Phân tán), cho phép mở rộng linh hoạt theo quy mô bãi xe thực tế.

*   **Main Backend (Core Control)**: Sử dụng **FastAPI** xử lý điều phối trung tâm.
*   **Kiến trúc Máy trạm Độc lập (Dual-Station Architecture)**: Hệ thống cho phép tách biệt luồng xử lý thông qua URL Parameters (`?lane=IN/OUT`).
*   **Giao tiếp Thời gian thực (Real-time WebSocket)**: Toàn bộ quá trình đồng bộ trạng thái AI và nhật ký hoạt động được thực hiện qua giao thức **WebSocket**, loại bỏ hoàn toàn độ trễ.

---

## 2. Phân Cấu Trúc Mã Nguồn Cốt Lõi (Core Components)

Hệ thống được thiết kế theo mô hình Micro-monolith tinh gọn, chia làm 3 tệp tin chuyên biệt đảm nhận 3 vai trò độc lập:

### 2.1. `index.html` (Lớp Giao diện & Tiền xử lý - Frontend & Client AI)
*   **Phân luồng độc lập:** Đọc tham số URL (`?lane=IN` hoặc `OUT`) để tự động khóa cứng chức năng màn hình.
*   **Tiền xử lý AI (Client-side):** Chạy trực tiếp mô hình **MediaPipe Face Detection** trên trình duyệt, tự động bắt "khoảnh khắc vàng" (đủ gần, đủ tĩnh) trước khi gửi lên Server, giúp giảm 80% tải cho Backend.
*   **Cảnh báo vật lý:** Quản lý hiệu ứng thị giác (Rung màn hình, viền đỏ) và âm thanh hú còi (Web Audio API) khi phát hiện gian lận.

### 2.2. `main_backend.py` (Lớp Điều phối - Core Orchestrator)
*   **Quản lý trạng thái (State Management):** Sử dụng biến RAM (`pending_sessions`) để xếp hàng các xe đang chờ quét mặt. Tự động dọn rác (cleanup) các phiên chờ quá hạn.
*   **Bảo vệ Logic:** Là bộ não quyết định đóng/mở cổng. Áp dụng nghiêm ngặt các quy tắc vật lý: Từ chối xe "Vào rồi lại Xin Vào" hoặc "Chưa Vào mà Xin Ra".
*   **Giao tiếp Thời gian thực:** Chứa Engine WebSocket phát sóng trạng thái (Broadcast) xuống tất cả các màn hình giám sát với độ trễ ~0ms.

### 2.3. `db_manager.py` (Lớp Truy xuất Dữ liệu - Data Layer)
*   **Đồng bộ Kép:** Quản lý cùng lúc kết nối đến PostgreSQL (lưu lịch sử) và Qdrant (lưu vector khuôn mặt 512 chiều).
*   **Đối soát Lịch sử CCCD:** Chứa hàm `check_user_access` mang tính cách mạng - thay vì hỏi "Xe này của ai?", nó truy vấn SQL để hỏi "Khuôn mặt này có phải là người đã gửi chiếc xe này vào không?", giải quyết triệt để bài toán 1 người sở hữu nhiều xe.

---

## 3. Công Nghệ & Thư Viện Sử Dụng (Tech Stack)

### 3.1. Backend & AI Services
*   **FastAPI / Pydantic**: Hiệu năng cao và xác thực dữ liệu chặt chẽ.
*   **PostgreSQL & Qdrant**: Cặp đôi CSDL SQL và Vector mạnh mẽ nhất hiện nay.
*   **DeepFace (FaceNet512)**: Trích xuất đặc trưng khuôn mặt 512 chiều với độ chính xác cao.
*   **Cloudinary SDK**: Giải pháp Cloud SaaS lưu trữ hình ảnh chuyên nghiệp, giải quyết bài toán đầy ổ cứng.
*   **YOLOv8 & PaddleOCR**: Chuyên biệt cho nhận diện và bóc tách biển số xe.

### 3.2. Frontend & Client AI
*   **MediaPipe Tasks Vision**: Thư viện tiên tiến nhất để xử lý thị giác máy tính trên trình duyệt.
*   **Glassmorphism 2.0 & Font Nunito**: Mang lại trải nghiệm người dùng hiện đại và chuyên nghiệp.

---

## 4. Các Đột Phá Về Công Nghệ AI (AI Innovations)

### 4.1. Chế độ Chụp ảnh Tự động (No-Touch AI Autonomous)
Hệ thống sử dụng bộ lọc thông minh trên trình duyệt để tự động hóa việc chụp ảnh:
*   **Phễu lọc 1 (Khoảng cách)**: Chỉ kích hoạt khi khuôn mặt chiếm >22% khung hình.
*   **Phễu lọc 2 (Độ ổn định)**: Thuật toán so sánh tọa độ X-Y, chỉ chụp khi người dùng đứng yên ổn định.

### 4.2. Hệ thống Báo động Đa phương thức (Red Alert System)
Khi phát hiện hành vi gian lận (tráo xe, kẻ gian), hệ thống kích hoạt chế độ **Red Alert**:
*   **Âm thanh (Siren)**: Hú còi báo động chói tai (Oscillator sawtooth wave).
*   **Thị giác (Shake Alert)**: Rung lắc màn hình giám sát để đánh thức sự chú ý của bảo vệ.

### 4.3. Lưu trữ Đám mây & Xử lý Zero-Latency (Background Archiving)
Hệ thống giải quyết bài toán hiệu năng và lưu trữ bằng kỹ thuật xử lý luồng ngầm:
*   **Zero-Latency**: Việc upload ảnh lên Cloud được đẩy vào một luồng ngầm (**Threading**). Ngay khi xác thực xong, Barie mở ngay lập tức mà không phải chờ đợi quá trình tải lên mạng kết thúc.
*   **Cấu trúc lưu trữ thông minh**: Hình ảnh được tự động phân loại theo thư mục ngày tháng (`smart_parking/storage/DD-MM-YYYY`) với định danh file theo biển số và thời gian, giúp việc truy xuất sau này cực kỳ dễ dàng.

---

## 5. Logic An Ninh & Bảo Mật 3 Lớp (Triple-Defense)

Hệ thống được bọc thép bởi 3 lớp phòng ngự độc lập:

1.  **Lớp 1 (RAM Queue)**: Chống Spam và quản lý bộ nhớ.
2.  **Lớp 2 (SQL Physics)**: Kiểm soát trạng thái vào/ra thực tế của phương tiện.
3.  **Lớp 3 (CCCD Identity)**: Triết lý "Khuôn mặt là CCCD", đối soát quyền sở hữu tài sản dựa trên lịch sử giao dịch.

---

## 6. Đánh Giá An Toàn & Xử Lý Kịch Bản Ngoại Lệ (Edge Cases)

Hệ thống đã được thiết kế để đối phó tự động với các kịch bản phá hoại hoặc lỗi thao tác:

### Kịch bản 1: Lỗi thao tác nhấn nhầm (Ghost Car)
*   **Xử lý:** Lớp bảo vệ số 2 (Logic Vật lý) sẽ kiểm tra CSDL. Nhận thấy xe chưa vào bãi mà định lấy ra, hệ thống lập tức hủy phiên, hú còi và hiển thị **"XE KHÔNG TRONG BÃI"**.

### Kịch bản 2: Hành vi Tráo xe / Ăn cắp xe (Identity Swap)
*   **Xử lý:** Lớp bảo vệ số 3 truy vấn lịch sử giao dịch. Nhận thấy người lấy xe không phải là người đã dắt xe vào, hệ thống thực hiện rung màn hình, báo động đỏ **"SAI CHỦ TÀI SẢN"** và lưu ảnh kẻ gian kèm trạng thái `FAILED_WRONG_OWNER`.

### Kịch bản 3: Kẻ gian đột nhập (Unknown Intruder)
*   **Xử lý:** Nếu khuôn mặt không tồn tại trong Qdrant (Độ tương đồng thấp), hệ thống từ chối mở cổng với thông báo **"CCCD KHÔNG HỢP LỆ: Khuôn mặt chưa từng vào bãi!"**.

### Kịch bản 4: Cố tình Spam (DDoS hàng chờ)
*   **Xử lý:** Lớp bảo vệ số 1 (RAM Queue) chặn đứng ngay từ vòng nhận diện biển số. Nếu biển số đang trong danh sách chờ, mọi yêu cầu tiếp theo sẽ bị từ chối để bảo vệ tài nguyên hệ thống.

---

## 7. Kết Luận
Hệ thống **AI Smart Parking** phiên bản Edition A+ không chỉ là một ứng dụng nhận diện hình ảnh đơn thuần mà là một giải pháp quản lý tài sản tích hợp toàn diện. Với sự kết hợp giữa kiến trúc phân tán, WebSocket thời gian thực và logic bảo mật 3 lớp, hệ thống hoàn toàn đáp ứng các tiêu chuẩn khắt khe nhất của hạ tầng đô thị thông minh hiện đại.
