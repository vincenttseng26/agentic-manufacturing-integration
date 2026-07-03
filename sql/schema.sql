-- Agentic Manufacturing Integration — PostgreSQL schema
-- 整個系統的資料契約。改這裡等於改契約，改前想清楚。

-- 一次 rollout = 一張「工單/批次」
CREATE TABLE IF NOT EXISTS jobs (
  job_id           BIGSERIAL PRIMARY KEY,
  batch_id         BIGINT,
  model_tag        VARCHAR(32),   -- 哪個 checkpoint（例：epoch_200），供跨模型比較
  created_at       TIMESTAMP DEFAULT NOW(),
  finished_at      TIMESTAMP,
  seed             INT,
  success          BOOLEAN,
  cycle_time_steps INT,          -- 步數 ≈ cycle time
  failure_stage    VARCHAR(32),  -- grasp_1 / place_1 / ... / place_3；成功則 NULL
  anomaly_flag     BOOLEAN DEFAULT FALSE
);

-- 每顆方塊的明細（畫「哪個顏色最常失敗」的 Pareto 用）
CREATE TABLE IF NOT EXISTS cube_results (
  id               BIGSERIAL PRIMARY KEY,
  job_id           BIGINT REFERENCES jobs(job_id) ON DELETE CASCADE,
  cube_color       VARCHAR(16),  -- blue / red / green
  placed_correctly BOOLEAN,
  final_x REAL, final_y REAL, final_z REAL
);

CREATE INDEX IF NOT EXISTS idx_jobs_batch    ON jobs(batch_id);
CREATE INDEX IF NOT EXISTS idx_jobs_created  ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_cube_job      ON cube_results(job_id);
