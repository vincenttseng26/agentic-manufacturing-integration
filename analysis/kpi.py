"""Phase 5：KPI 與異常偵測（pandas，純資料運算、無 sim 依賴，全部可進 CI）。

輸入是從 DB 撈出的 DataFrame：
  jobs: job_id, success(bool), cycle_time_steps, failure_stage, ...
  cube_results: job_id, cube_color, placed_correctly(bool), ...
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def summary(jobs: pd.DataFrame) -> dict:
    """整體 KPI：總數、成功數、成功率、平均 cycle time。"""
    if jobs.empty:
        return {"total": 0, "success": 0, "success_rate": 0.0, "avg_cycle_time_steps": 0.0}
    return {
        "total": int(len(jobs)),
        "success": int(jobs["success"].sum()),
        "success_rate": float(jobs["success"].mean()),
        "avg_cycle_time_steps": float(jobs["cycle_time_steps"].mean()),
    }


def add_rolling_success_rate(jobs: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """加一欄滾動成功率（依 job_id 排序）。"""
    jobs = jobs.sort_values("job_id").reset_index(drop=True)
    jobs["rolling_success_rate"] = jobs["success"].astype(float).rolling(window, min_periods=1).mean()
    return jobs


def add_spc_limits(jobs: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """p-chart 管制界：以整體成功率 p 為中心線，±3σ 為上下界，標出異常點。

    σ = sqrt(p(1-p)/window)。需先呼叫 add_rolling_success_rate。
    """
    if jobs.empty:
        return jobs
    p = float(jobs["success"].astype(float).mean())
    sigma = np.sqrt(max(p * (1 - p), 1e-9) / window)
    jobs["p_bar"] = p
    jobs["ucl"] = min(1.0, p + 3 * sigma)
    jobs["lcl"] = max(0.0, p - 3 * sigma)
    jobs["anomaly"] = (jobs["rolling_success_rate"] > jobs["ucl"]) | (jobs["rolling_success_rate"] < jobs["lcl"])
    return jobs


def add_spc_per_group(jobs: pd.DataFrame, group_col: str = "model_tag", window: int = 5) -> pd.DataFrame:
    """對每個 checkpoint（group_col）各自算 rolling 成功率 + p-chart 管制界。

    多 checkpoint 監控時要 per-model 各算（不能全部混在一起），否則管制界會被跨模型的差異汙染。
    """
    if jobs.empty:
        return jobs
    if group_col not in jobs.columns:
        return add_spc_limits(add_rolling_success_rate(jobs, window), window)
    parts = []
    for _, group in jobs.groupby(group_col):
        group = add_rolling_success_rate(group, window)
        group = add_spc_limits(group, window)
        parts.append(group)
    return pd.concat(parts, ignore_index=True)


def failure_pareto(jobs: pd.DataFrame) -> pd.DataFrame:
    """失敗階段 Pareto（只看失敗的 job）。"""
    fails = jobs[~jobs["success"].astype(bool)]
    if fails.empty:
        return pd.DataFrame(columns=["failure_stage", "n"])
    return (
        fails.groupby("failure_stage").size().reset_index(name="n").sort_values("n", ascending=False)
    )


def cube_miss_rate(cubes: pd.DataFrame) -> pd.DataFrame:
    """各顏色方塊沒放對的次數 / 比率（找出最弱的那顆）。"""
    if cubes.empty:
        return pd.DataFrame(columns=["cube_color", "total", "missed", "miss_rate"])
    g = cubes.groupby("cube_color")["placed_correctly"].agg(total="count", placed="sum").reset_index()
    g["missed"] = g["total"] - g["placed"]
    g["miss_rate"] = g["missed"] / g["total"]
    return g[["cube_color", "total", "missed", "miss_rate"]].sort_values("missed", ascending=False)
