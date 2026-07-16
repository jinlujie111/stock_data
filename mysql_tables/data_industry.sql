-- ============================================================================
-- data_industry：行业资金流网站等业务数据（与 stock_data 股票库分离）
-- 首次：root 执行 mysql_tables/data_industry_grants.sql 建库并授权
-- 建表：source dw-utils/func.sh && init_data_industry_schema
--
-- 注意：板块轮动 rotation_* 表在 stock_data，不在本库。
-- ============================================================================

USE data_industry;

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

CREATE TABLE IF NOT EXISTS app_user_board_favorite (
    id            BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id       BIGINT       NOT NULL COMMENT 'app_user.id',
    industry_code VARCHAR(32)  NOT NULL COMMENT '东财板块代码',
    industry_name VARCHAR(128) NULL COMMENT '板块名称',
    content_type  VARCHAR(16)  NULL COMMENT '行业/概念',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_board (user_id, industry_code),
    KEY idx_board_fav_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户板块自选';

CREATE TABLE IF NOT EXISTS app_user_stock_favorite (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id     BIGINT       NOT NULL COMMENT 'app_user.id',
    ts_code     VARCHAR(16)  NOT NULL COMMENT '股票TS代码',
    stock_name  VARCHAR(64)  NULL COMMENT '股票简称',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_stock (user_id, ts_code),
    KEY idx_stock_fav_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户股票自选';
