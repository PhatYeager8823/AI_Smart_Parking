-- SMART PARKING DATABASE SETUP SCRIPT
-- RUN THIS IN PGADMIN 4 OR YOUR SQL TOOL

-- 1. Xóa các bảng cũ nếu tồn tại (Lưu ý: Hành động này sẽ xóa sạch dữ liệu cũ)
DROP TABLE IF EXISTS parking_logs CASCADE;
DROP TABLE IF EXISTS parking_users CASCADE;
DROP TABLE IF EXISTS family_vehicles CASCADE;
DROP TABLE IF EXISTS families CASCADE;

-- 2. Tạo bảng Hộ Gia Đình (Sổ hộ khẩu)
CREATE TABLE families (
    family_id SERIAL PRIMARY KEY,
    room_number VARCHAR(50) UNIQUE NOT NULL, -- Ví dụ: 'A12.05'
    owner_name VARCHAR(100),
    monthly_fee INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tạo bảng Xe của Hộ Gia Đình
CREATE TABLE family_vehicles (
    plate_number VARCHAR(20) PRIMARY KEY,
    family_id INTEGER REFERENCES families(family_id) ON DELETE CASCADE,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tạo bảng quản lý Chủ xe (Khách & Cư dân)
CREATE TABLE parking_users (
    user_id SERIAL PRIMARY KEY,
    face_id VARCHAR(100) UNIQUE NOT NULL, 
    plate_number VARCHAR(20),    -- Cư dân có thể không cần điền biển số ở đây
    full_name VARCHAR(255),               
    family_id INTEGER REFERENCES families(family_id) ON DELETE SET NULL,
    role VARCHAR(20) DEFAULT 'guest', -- 'guest' hoặc 'resident'
    face_url TEXT,                    -- URL ảnh đại diện gốc trên Cloudinary
    face_public_id VARCHAR(255),      -- ID định danh ảnh trên Cloudinary (để quản lý/xóa)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Tạo bảng Nhật ký hoạt động ra vào (Transaction Board)
CREATE TABLE parking_logs (
    log_id SERIAL PRIMARY KEY,
    session_id VARCHAR(100),              -- Mã phiên giao dịch để khớp lúc vào - lúc ra
    user_id INTEGER REFERENCES parking_users(user_id) ON DELETE SET NULL,
    plate_detected VARCHAR(20),           
    face_similarity FLOAT,                
    action_type VARCHAR(10),              -- IN / OUT
    status VARCHAR(20),                   
    face_url TEXT,                        -- URL ảnh khuôn mặt trên Cloudinary
    face_public_id VARCHAR(255),          -- ID ảnh khuôn mặt trên Cloudinary
    plate_url TEXT,                       -- URL ảnh biển số trên Cloudinary
    plate_public_id VARCHAR(255),         -- ID ảnh biển số trên Cloudinary
    parking_fee INTEGER DEFAULT 0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
