"""Phase 5：把 DB 資料 + KPI 匯出成 Power BI 雲端可 import 的 CSV。

資料路徑（見 CLAUDE.md）選 ②：匯出彙總 CSV 上傳 Power BI import（demo 夠用）。
Power BI 匯入兩張表（job_id 關聯），其餘 Pareto / cube 統計讓 Power BI 自己 group-by。

用法（從專案根目錄）：
    python analysis/export_powerbi.py --out-dir data
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from analysis import kpi  # noqa: E402
from orchestration.db import query  # noqa: E402


def export(out_dir: str = "data") -> dict:
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    jobs = pd.DataFrame(query(
        "SELECT job_id, batch_id, model_tag, created_at, seed, success, cycle_time_steps, "
        "failure_stage, anomaly_flag FROM jobs ORDER BY job_id"
    ))
    cubes = pd.DataFrame(query(
        "SELECT job_id, cube_color, placed_correctly, final_x, final_y, final_z "
        "FROM cube_results ORDER BY job_id, cube_color"
    ))

    if not jobs.empty:
        # 從 model_tag（epoch_200）抽數字 epoch，供 Power BI 折線圖 X 軸正確排序
        jobs["model_epoch"] = jobs["model_tag"].str.extract(r"(\d+)", expand=False).astype(float)
        jobs = kpi.add_spc_per_group(jobs, group_col="model_tag", window=5)  # 每個 checkpoint 各自算 SPC
        jobs["success_int"] = jobs["success"].astype(int)  # Power BI 加總方便

    jobs_path = out / "powerbi_jobs.csv"
    cubes_path = out / "powerbi_cube_results.csv"
    jobs.to_csv(jobs_path, index=False)
    cubes.to_csv(cubes_path, index=False)

    # 單一 xlsx（兩個工作表）給 Power BI 雲端上傳最順：一次上傳 = 兩張表。
    xlsx_path = out / "powerbi_data.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        jobs.to_excel(writer, sheet_name="jobs", index=False)
        cubes.to_excel(writer, sheet_name="cube_results", index=False)

    return {
        "jobs_csv": str(jobs_path),
        "cubes_csv": str(cubes_path),
        "xlsx": str(xlsx_path),
        "n_jobs": len(jobs),
        "n_cubes": len(cubes),
        "summary": kpi.summary(jobs) if not jobs.empty else {},
    }


def main():
    parser = argparse.ArgumentParser(description="Export DB data + KPIs to CSV for Power BI.")
    parser.add_argument("--out-dir", default="data")
    args = parser.parse_args()

    result = export(args.out_dir)
    print(f"jobs  -> {result['jobs_csv']} ({result['n_jobs']} 列)")
    print(f"cubes -> {result['cubes_csv']} ({result['n_cubes']} 列)")
    print(f"xlsx  -> {result['xlsx']} (jobs + cube_results 兩個工作表,上傳這個)")
    print(f"KPI: {result['summary']}")


if __name__ == "__main__":
    main()
