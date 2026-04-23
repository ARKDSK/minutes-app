-- 素のPHP版 議事録アプリ用スキーマ (MySQL 5.7+ / 8.x)
CREATE DATABASE IF NOT EXISTS minutes_app
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE minutes_app;

CREATE TABLE IF NOT EXISTS minutes (
  id                  CHAR(36)      NOT NULL,
  date_str            DATE          NOT NULL,
  title               VARCHAR(255)  NOT NULL,
  participants        VARCHAR(500)  NOT NULL DEFAULT '',
  tags                VARCHAR(500)  NOT NULL DEFAULT '',
  content             MEDIUMTEXT    NOT NULL,
  analysis            JSON          NULL,
  summary_3           JSON          NULL,
  transcript_segments JSON          NULL,
  bigrams             JSON          NULL,
  created_at          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_date (date_str),
  FULLTEXT KEY ft_content (title, content, tags) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
