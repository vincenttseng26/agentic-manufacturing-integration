"""Phase 3：MCP 工具的業務邏輯（純函式，與 MCP 協定解耦，方便測試）。

- get_kpi / query_db：唯讀分析，不需 GPU（可在此環境測）。
- run_batch：跑 sim（需 GPU，在 env_isaacsim 執行），透過 bash 跨環境橋接。
"""
from __future__ import annotations

import datetime
import decimal
import pathlib
import subprocess

import pandas as pd

from analysis import kpi
from orchestration import load_results
from orchestration.db import query

PROJECT_ROOT = pathlib.Path(__file__).parents[1]
DEFAULT_CHECKPOINT = (
    "/home/vincent/Downloads/imitation learning tutorial/19_SMMG/training_logs/"
    "Isaac-Sort-Cube-Franka-IK-Rel-v0/bc_rnn_low_dim_franka_stack/20260612105251/"
    "models/model_epoch_200.pth"
)
_FORBIDDEN = ("insert ", "update ", "delete ", "drop ", "alter ", "truncate", "create ", "grant ", "revoke ")


def get_kpi() -> dict:
    """整體 KPI + 失敗階段 Pareto + 各顏色方塊失敗率。"""
    jobs = pd.DataFrame(query("SELECT job_id, success, cycle_time_steps, failure_stage FROM jobs"))
    cubes = pd.DataFrame(query("SELECT cube_color, placed_correctly FROM cube_results"))
    return {
        "summary": kpi.summary(jobs) if not jobs.empty else {},
        "failure_pareto": kpi.failure_pareto(jobs).to_dict("records") if not jobs.empty else [],
        "cube_miss_rate": kpi.cube_miss_rate(cubes).to_dict("records") if not cubes.empty else [],
    }


def _jsonable(v):
    """把 DB 回傳的 Decimal / datetime 轉成 JSON 安全型別（automatic function calling 要序列化）。"""
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    return v


def query_db(sql: str) -> list[dict]:
    """唯讀 SELECT 查詢（NL→SQL 用）。只允許單段 SELECT，擋掉任何寫入關鍵字。"""
    cleaned = sql.strip().rstrip(";")
    low = cleaned.lower()
    if not low.startswith("select"):
        raise ValueError("只允許 SELECT 查詢")
    if ";" in cleaned:
        raise ValueError("不允許多段語句")
    if any(bad in low for bad in _FORBIDDEN):
        raise ValueError("偵測到非唯讀關鍵字，已拒絕")
    return [{k: _jsonable(v) for k, v in row.items()} for row in query(cleaned)]


def run_batch(
    num_rollouts: int = 10,
    seed: int = 100,
    checkpoint: str = DEFAULT_CHECKPOINT,
    batch_id: int | None = None,
) -> dict:
    """跑一批分類 rollout（需 GPU，在 env_isaacsim 執行），結果寫入 DB，回傳摘要。

    透過 `bash -lc` 啟用 env_isaacsim 再呼叫 isaaclab.sh（跨環境橋接：本檔在 env_agent）。
    """
    out = PROJECT_ROOT / "data" / "results.jsonl"
    inner = (
        "source ~/env_isaacsim/bin/activate && cd ~/IsaacLab && "
        f'./isaaclab.sh -p "{PROJECT_ROOT}/sim/run_job.py" '
        "--task Isaac-Sort-Cube-Franka-IK-Rel-v0 "
        f'--checkpoint "{checkpoint}" '
        f"--num_rollouts {num_rollouts} --seed {seed} --horizon 1800 --headless --device cuda "
        f'--out "{out}"'
    )
    subprocess.run(["bash", "-lc", inner], check=True)
    n = load_results.load_jsonl(str(out), batch_id=batch_id)
    return {"loaded": n, "kpi": get_kpi()["summary"]}
