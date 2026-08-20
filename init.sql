-- ============================================================
-- api_test 数据库初始化脚本
-- 使用方式：mysql -u root -p < init.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS api_test
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE api_test;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    user_id     INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(64)  NOT NULL UNIQUE,
    password    VARCHAR(128) NOT NULL,
    avatar      VARCHAR(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 订单表
CREATE TABLE IF NOT EXISTS orders (
    order_id    VARCHAR(64)  NOT NULL PRIMARY KEY,
    user_id     INT          NOT NULL,
    product_id  VARCHAR(64)  NOT NULL,
    quantity    INT          NOT NULL DEFAULT 1,
    address     VARCHAR(255) DEFAULT '',
    status      VARCHAR(32)  NOT NULL DEFAULT 'pending',
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 项目表
CREATE TABLE IF NOT EXISTS projects (
    id          VARCHAR(64)  NOT NULL PRIMARY KEY,
    name        VARCHAR(128) NOT NULL,
    user_id     INT          NOT NULL,
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 任务表
CREATE TABLE IF NOT EXISTS tasks (
    id          VARCHAR(64)  NOT NULL PRIMARY KEY,
    project_id  VARCHAR(64)  NOT NULL,
    title       VARCHAR(255) NOT NULL,
    priority    VARCHAR(32)  NOT NULL DEFAULT 'medium',
    status      VARCHAR(32)  NOT NULL DEFAULT 'open',
    INDEX idx_project_id (project_id),
    CONSTRAINT fk_tasks_project FOREIGN KEY (project_id)
        REFERENCES projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 文件上传表
CREATE TABLE IF NOT EXISTS file_uploads (
    file_key    VARCHAR(64)  NOT NULL PRIMARY KEY,
    file_name   VARCHAR(255) NOT NULL,
    file_type   VARCHAR(64)  DEFAULT '',
    user_id     INT          NOT NULL,
    committed   TINYINT(1)   NOT NULL DEFAULT 0,
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 种子数据：测试用户
-- 密码明文存储（仅限测试环境，生产环境必须用 bcrypt 等）
-- ============================================================
INSERT INTO users (username, password) VALUES
    ('testuser', 'Test@123')
ON DUPLICATE KEY UPDATE password = VALUES(password);
