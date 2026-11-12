-- ============================================================================
-- AgroScan Database Initialization Script (PostgreSQL 14+)
-- ============================================================================
-- Usage:
--   psql -U postgres -d agroscan -f scripts/init_db.sql
-- ============================================================================

-- 1. Create Schema / Tables
-- ----------------------------------------------------------------------------

DROP TABLE IF EXISTS inspection_results CASCADE;
DROP TABLE IF EXISTS evidence_images CASCADE;
DROP TABLE IF EXISTS inspection_sessions CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS product_criteria CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Users table (D-027, D-032)
CREATE TABLE users (
    username VARCHAR(50) PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('ADMIN', 'INSPECTOR', 'REVIEWER')),
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Products table (D-024)
CREATE TABLE products (
    code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    model_file VARCHAR(100) NOT NULL,
    detect_classes JSONB NOT NULL DEFAULT '["fresh", "bruised", "rotten"]'::jsonb,
    min_objects INT NOT NULL DEFAULT 5,
    min_confidence NUMERIC(4, 2) NOT NULL DEFAULT 0.60,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Defect criteria per product (D-023)
CREATE TABLE product_criteria (
    id SERIAL PRIMARY KEY,
    product_code VARCHAR(50) NOT NULL REFERENCES products(code) ON DELETE CASCADE,
    defect_class VARCHAR(50) NOT NULL,
    max_ratio NUMERIC(4, 3) NOT NULL, -- e.g. 0.100 = 10%
    is_critical BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (product_code, defect_class)
);

-- Orders table (D-019, D-022)
CREATE TABLE orders (
    order_code VARCHAR(50) PRIMARY KEY,
    product_code VARCHAR(50) NOT NULL REFERENCES products(code),
    supplier VARCHAR(150) NOT NULL,
    total_boxes INT NOT NULL CHECK (total_boxes > 0),
    expected_quantity INT NOT NULL CHECK (expected_quantity > 0),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Inspection sessions per box (D-019, D-020, D-021)
CREATE TABLE inspection_sessions (
    session_id VARCHAR(50) PRIMARY KEY,
    box_code VARCHAR(100) NOT NULL, -- AGS:DH00123-01/10
    order_code VARCHAR(50) NOT NULL REFERENCES orders(order_code),
    box_number INT NOT NULL,
    total_boxes INT NOT NULL,
    inspector VARCHAR(50) NOT NULL,
    station VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL CHECK (status IN ('In Progress', 'Pending Review', 'Completed')),
    notes TEXT DEFAULT '',
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_sessions_box_code ON inspection_sessions(box_code);
CREATE INDEX idx_sessions_status ON inspection_sessions(status);

-- Evidence images (D-026)
CREATE TABLE evidence_images (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(50) NOT NULL REFERENCES inspection_sessions(session_id) ON DELETE CASCADE,
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_auto_capture BOOLEAN NOT NULL DEFAULT FALSE,
    relative_path VARCHAR(255) NOT NULL,
    sha256 VARCHAR(64) NOT NULL
);

-- Inspection official results & human review decisions (D-023, D-026, D-027, D-030)
CREATE TABLE inspection_results (
    session_id VARCHAR(50) PRIMARY KEY REFERENCES inspection_sessions(session_id) ON DELETE CASCADE,
    total_objects INT NOT NULL DEFAULT 0,
    class_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    mean_confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.0,
    recommendation VARCHAR(20) NOT NULL CHECK (recommendation IN ('Pass', 'Fail', 'Needs Review')),
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    defect_ratios JSONB NOT NULL DEFAULT '{}'::jsonb,
    deep_analysis JSONB,
    decision VARCHAR(20) CHECK (decision IN ('Pass', 'Fail', 'Re-inspect')),
    reviewer VARCHAR(50),
    review_notes TEXT DEFAULT '',
    reviewed_at TIMESTAMP WITH TIME ZONE
);

-- ----------------------------------------------------------------------------
-- 2. Seed Default Data (Khởi tạo dữ liệu mẫu phục vụ demo)
-- ----------------------------------------------------------------------------

-- Users (Mật khẩu mặc định: AgroScan@2026)
INSERT INTO users (username, display_name, role, password_hash) VALUES
('admin', 'System Administrator', 'ADMIN', 'pbkdf2_sha256$260000$default_admin_hash'),
('inspector', 'Senior QC Inspector', 'INSPECTOR', 'pbkdf2_sha256$260000$default_inspector_hash'),
('reviewer', 'Quality Supervisor', 'REVIEWER', 'pbkdf2_sha256$260000$default_reviewer_hash');

-- Products
INSERT INTO products (code, name, category, model_file, detect_classes, min_objects, min_confidence) VALUES
('BANANA', 'Banana (Chuối tiêu)', 'Fruit', 'banana_defect.onnx', '["fresh", "bruised", "rotten"]'::jsonb, 5, 0.60),
('APPLE', 'Fuji Apple (Táo Fuji)', 'Fruit', 'apple_defect.onnx', '["fresh", "bruised", "rotten"]'::jsonb, 5, 0.60),
('MANGO', 'Cat Chu Mango (Xoài Cát Chu)', 'Fruit', 'mango_defect.onnx', '["fresh", "bruised", "rotten"]'::jsonb, 5, 0.60);

-- Criteria
INSERT INTO product_criteria (product_code, defect_class, max_ratio, is_critical) VALUES
('BANANA', 'bruised', 0.100, FALSE), -- Dập tối đa 10%
('BANANA', 'rotten', 0.000, TRUE),   -- Thối: 1 quả là hỏng ngay
('APPLE', 'bruised', 0.080, FALSE),  -- Dập tối đa 8%
('APPLE', 'rotten', 0.000, TRUE),
('MANGO', 'bruised', 0.120, FALSE),
('MANGO', 'rotten', 0.000, TRUE);

-- Sample Orders
INSERT INTO orders (order_code, product_code, supplier, total_boxes, expected_quantity) VALUES
('DH00123', 'BANANA', 'HAGL Agrico Gia Lai', 10, 500),
('DH00124', 'APPLE', 'VinEco Lam Dong', 8, 400),
('DH00125', 'MANGO', 'Dong Thap Fruit Co.', 12, 600);

