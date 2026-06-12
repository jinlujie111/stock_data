-- 行业资金流网站用户表（stock_data 库）
CREATE TABLE IF NOT EXISTS app_user (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    username      VARCHAR(64)  NOT NULL COMMENT '登录名',
    email         VARCHAR(128) NULL COMMENT '邮箱',
    password_hash VARCHAR(255) NOT NULL COMMENT 'bcrypt 哈希',
    status        TINYINT      NOT NULL DEFAULT 1 COMMENT '1=正常 0=禁用',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_app_user_username (username),
    UNIQUE KEY uk_app_user_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业资金流网站用户';
