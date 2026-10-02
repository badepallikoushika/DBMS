-- =====================================================================
-- WAREHOUSE & INVENTORY MANAGEMENT SYSTEM - COMPLETE MYSQL COMMANDS
-- Run this entire script in MySQL Workbench or the MySQL Command Line Client.
-- It sets up the database, tables, constraints, views, triggers, stored procedures,
-- and inserts sample inventory data.
-- =====================================================================

-- ---------------------------------------------------------------------
-- STEP 1: CREATE AND SWITCH TO DATABASE
-- ---------------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS warehouse_db;
USE warehouse_db;

-- ---------------------------------------------------------------------
-- STEP 2: CLEANUP EXISTING OBJECTS (Allows safe re-running)
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS after_stock_update;
DROP PROCEDURE IF EXISTS transfer_stock;
DROP VIEW IF EXISTS category_stock_analytics;
DROP VIEW IF EXISTS product_stock_summary;
DROP TABLE IF EXISTS stock_audit_log;
DROP TABLE IF EXISTS warehouse_stock;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS warehouses;

-- ---------------------------------------------------------------------
-- STEP 3: CREATE TABLES WITH CONSTRAINTS & RELATIONSHIPS
-- ---------------------------------------------------------------------

-- Table 1: Warehouses (Stores storage hubs and capacity)
CREATE TABLE warehouses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    location VARCHAR(150) NOT NULL,
    capacity INT NOT NULL DEFAULT 1000,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Table 2: Products (Catalog definitions with CHECK constraint)
CREATE TABLE products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    sku VARCHAR(50) NOT NULL UNIQUE,
    category VARCHAR(100) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    quantity INT NOT NULL DEFAULT 0,
    reorder_level INT NOT NULL DEFAULT 10,
    description TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_product_price CHECK (price >= 0)
) ENGINE=InnoDB;

-- Table 3: Warehouse Stock (M:N Associative table with Composite Unique Constraint)
CREATE TABLE warehouse_stock (
    id INT AUTO_INCREMENT PRIMARY KEY,
    warehouse_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_ws_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE CASCADE,
    CONSTRAINT fk_ws_product FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    CONSTRAINT uq_product_warehouse UNIQUE (product_id, warehouse_id),
    CONSTRAINT chk_stock_quantity CHECK (quantity >= 0)
) ENGINE=InnoDB;

-- Table 4: Stock Audit Log (Maintained automatically by MySQL Trigger)
CREATE TABLE stock_audit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NULL,
    warehouse_id INT NULL,
    old_quantity INT NULL,
    new_quantity INT NULL,
    action VARCHAR(50) DEFAULT 'UPDATE',
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- STEP 4: CREATE PERFORMANCE INDEXES
-- ---------------------------------------------------------------------
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_sku ON products(sku);
CREATE INDEX idx_warehouse_stock_product ON warehouse_stock(product_id);
CREATE INDEX idx_warehouse_stock_warehouse ON warehouse_stock(warehouse_id);

-- ---------------------------------------------------------------------
-- STEP 5: CREATE DATABASE VIEWS
-- ---------------------------------------------------------------------

-- View 1: Product Stock Summary (Hides multi-table joins & calculates status)
CREATE OR REPLACE VIEW product_stock_summary AS
SELECT
    p.id AS product_id,
    p.name AS product_name,
    p.sku,
    p.category,
    p.price,
    COALESCE(SUM(ws.quantity), 0) AS total_stock,
    p.reorder_level,
    CASE
        WHEN COALESCE(SUM(ws.quantity), 0) <= p.reorder_level THEN 'LOW STOCK'
        ELSE 'IN STOCK'
    END AS status
FROM products p
LEFT JOIN warehouse_stock ws ON ws.product_id = p.id
GROUP BY p.id, p.name, p.sku, p.category, p.price, p.reorder_level;

-- View 2: Category Analytics (Computes valuation & unit counts per category)
CREATE OR REPLACE VIEW category_stock_analytics AS
SELECT
    p.category,
    COUNT(DISTINCT p.id) AS total_items,
    COALESCE(SUM(ws.quantity), 0) AS total_units,
    COALESCE(SUM(ws.quantity * p.price), 0) AS total_valuation,
    ROUND(AVG(p.price), 2) AS average_price
FROM products p
LEFT JOIN warehouse_stock ws ON ws.product_id = p.id
GROUP BY p.category;

-- ---------------------------------------------------------------------
-- STEP 6: CREATE TRIGGER (Automated Audit Trail on Stock Updates)
-- ---------------------------------------------------------------------
DELIMITER //

CREATE TRIGGER after_stock_update
AFTER UPDATE ON warehouse_stock
FOR EACH ROW
BEGIN
    IF OLD.quantity <> NEW.quantity THEN
        INSERT INTO stock_audit_log (product_id, warehouse_id, old_quantity, new_quantity, action)
        VALUES (NEW.product_id, NEW.warehouse_id, OLD.quantity, NEW.quantity, 'STOCK_UPDATE');
    END IF;
END //

DELIMITER ;

-- ---------------------------------------------------------------------
-- STEP 7: CREATE STORED PROCEDURE (Atomic ACID Stock Relocation)
-- ---------------------------------------------------------------------
DELIMITER //

CREATE PROCEDURE transfer_stock(
    IN p_product_id INT,
    IN p_from_warehouse INT,
    IN p_to_warehouse INT,
    IN p_qty INT
)
BEGIN
    DECLARE current_qty INT DEFAULT 0;

    -- Rollback automatically if any SQLEXCEPTION occurs
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF p_from_warehouse = p_to_warehouse THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Source and destination warehouses cannot be identical';
    END IF;

    IF p_qty <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Transfer quantity must be greater than zero';
    END IF;

    START TRANSACTION;

    -- Row-level locking to prevent concurrency race conditions
    SELECT quantity INTO current_qty
    FROM warehouse_stock
    WHERE product_id = p_product_id AND warehouse_id = p_from_warehouse
    FOR UPDATE;

    IF current_qty IS NULL OR current_qty < p_qty THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Insufficient stock in source warehouse for transfer';
    END IF;

    -- Debit source warehouse
    UPDATE warehouse_stock
    SET quantity = quantity - p_qty
    WHERE product_id = p_product_id AND warehouse_id = p_from_warehouse;

    -- Credit destination warehouse
    INSERT INTO warehouse_stock (product_id, warehouse_id, quantity)
    VALUES (p_product_id, p_to_warehouse, p_qty)
    ON DUPLICATE KEY UPDATE quantity = quantity + p_qty;

    -- Synchronize total quantity in products table
    UPDATE products
    SET quantity = (SELECT COALESCE(SUM(quantity), 0) FROM warehouse_stock WHERE product_id = p_product_id)
    WHERE id = p_product_id;

    COMMIT;
END //

DELIMITER ;

-- ---------------------------------------------------------------------
-- STEP 8: INSERT REALISTIC SAMPLE DATA
-- ---------------------------------------------------------------------

-- Insert Warehouses
INSERT INTO warehouses (name, location, capacity) VALUES
('Central Logistics Hub', 'Mumbai Industrial Corridor, Sector 4', 5000),
('North Distribution Depot', 'Delhi NCR Terminal, Gate 2', 3500),
('South Regional Warehouse', 'Bengaluru Electronics City, Phase 1', 4000),
('Western Transit Facility', 'Pune Auto Cluster, Chakan', 2500);

-- Insert Products
INSERT INTO products (name, sku, category, price, quantity, reorder_level, description) VALUES
('Industrial Barcode Scanner', 'SCN-001', 'Electronics', 4999.00, 45, 15, 'Rugged 2D wireless handheld barcode scanner with Bluetooth'),
('Ergonomic Mesh Office Chair', 'CHR-102', 'Furniture', 8500.00, 18, 10, 'High-back ergonomic swivel chair with lumbar support'),
('Thermal Shipping Label Printer', 'PRN-303', 'Office Equipment', 12450.00, 8, 10, 'High-speed 4x6 direct thermal commercial label printer'),
('Heavy-Duty Steel Storage Rack', 'RCK-404', 'Furniture', 15999.00, 5, 8, '4-tier industrial shelving unit holding up to 800kg per tier'),
('Wireless Bluetooth Warehouse Headset', 'AUD-505', 'Accessories', 3200.00, 60, 20, 'Noise-cancelling single-ear headset with voice picking support'),
('Digital Heavy Weighing Scale', 'SCL-606', 'Electronics', 7800.00, 12, 10, 'Platform parcel weighing scale up to 300kg with LCD indicator'),
('Automatic Tape Dispenser', 'PKG-707', 'Office Equipment', 6100.00, 25, 12, 'Commercial electric tape dispenser with preset cut lengths');

-- Map Stock to Warehouses
INSERT INTO warehouse_stock (warehouse_id, product_id, quantity) VALUES
(1, 1, 25), (2, 1, 15), (3, 1, 5),
(1, 2, 8),  (3, 2, 10),
(1, 3, 3),  (2, 3, 5),
(1, 4, 2),  (4, 4, 3),
(1, 5, 30), (2, 5, 20), (3, 5, 10),
(2, 6, 8),  (4, 6, 4),
(1, 7, 15), (3, 7, 10);

-- Initial Audit Log Records
INSERT INTO stock_audit_log (product_id, warehouse_id, old_quantity, new_quantity, action) VALUES
(1, 1, 0, 25, 'INITIAL_LOAD'),
(2, 1, 0, 8, 'INITIAL_LOAD'),
(3, 1, 0, 3, 'INITIAL_LOAD');

-- ---------------------------------------------------------------------
-- STEP 9: VERIFICATION QUERIES (Run these to confirm everything works)
-- ---------------------------------------------------------------------
-- 1. Check all tables
SHOW TABLES;

-- 2. View all products and quantities
SELECT id, name, sku, category, price, quantity, reorder_level FROM products;

-- 3. View warehouse distribution
SELECT w.name AS warehouse, p.name AS product, ws.quantity
FROM warehouse_stock ws
JOIN warehouses w ON w.id = ws.warehouse_id
JOIN products p ON p.id = ws.product_id;

-- 4. Query the Product Summary View
SELECT * FROM product_stock_summary;

-- 5. Query the Category Analytics View
SELECT * FROM category_stock_analytics;

-- 6. Check the Audit Log
SELECT * FROM stock_audit_log;
