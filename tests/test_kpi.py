"""Phase 5/6：kpi 純函式單元測試（不需 DB，CI 直接可跑）。"""
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from analysis import kpi  # noqa: E402


def _sample_jobs() -> pd.DataFrame:
    return pd.DataFrame([
        {"job_id": 1, "success": False, "cycle_time_steps": 1800, "failure_stage": "place_3"},
        {"job_id": 2, "success": False, "cycle_time_steps": 1800, "failure_stage": "place_3"},
        {"job_id": 3, "success": True, "cycle_time_steps": 896, "failure_stage": None},
        {"job_id": 4, "success": False, "cycle_time_steps": 1800, "failure_stage": "grasp_3"},
        {"job_id": 5, "success": True, "cycle_time_steps": 1207, "failure_stage": None},
    ])


def test_summary():
    s = kpi.summary(_sample_jobs())
    assert s["total"] == 5
    assert s["success"] == 2
    assert abs(s["success_rate"] - 0.4) < 1e-9


def test_failure_pareto():
    par = kpi.failure_pareto(_sample_jobs())
    counts = dict(zip(par["failure_stage"], par["n"]))
    assert counts["place_3"] == 2
    assert counts["grasp_3"] == 1


def test_spc_columns_present():
    jobs = kpi.add_rolling_success_rate(_sample_jobs(), window=5)
    jobs = kpi.add_spc_limits(jobs, window=5)
    for col in ["rolling_success_rate", "p_bar", "ucl", "lcl", "anomaly"]:
        assert col in jobs.columns


def test_cube_miss_rate():
    cubes = pd.DataFrame([
        {"cube_color": "green", "placed_correctly": False},
        {"cube_color": "green", "placed_correctly": False},
        {"cube_color": "blue", "placed_correctly": True},
    ])
    res = kpi.cube_miss_rate(cubes).set_index("cube_color")
    assert res.loc["green", "missed"] == 2
    assert res.loc["blue", "missed"] == 0


def test_add_spc_per_group():
    """每個 model_tag 各自算 SPC：中心線 p_bar 應為各組自己的成功率。"""
    df = pd.DataFrame([
        {"job_id": 1, "model_tag": "epoch_200", "success": True},
        {"job_id": 2, "model_tag": "epoch_200", "success": True},
        {"job_id": 3, "model_tag": "epoch_600", "success": False},
        {"job_id": 4, "model_tag": "epoch_600", "success": False},
    ])
    out = kpi.add_spc_per_group(df, window=5)
    assert len(out) == 4
    assert out[out["model_tag"] == "epoch_200"]["p_bar"].iloc[0] == 1.0
    assert out[out["model_tag"] == "epoch_600"]["p_bar"].iloc[0] == 0.0
