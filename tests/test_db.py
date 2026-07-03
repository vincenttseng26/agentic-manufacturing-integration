"""Phase 2/6：DB 與契約的單元測試（CI 用拋棄式 postgres service 跑）。

sim 層一律 mock 掉，不在 CI 跑 Isaac Sim。
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))

CONTRACT = pathlib.Path(__file__).parents[1] / "contracts" / "job_result.schema.json"


def test_contract_file_is_valid_json():
    """契約檔本身要是合法 JSON。"""
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert data["title"] == "JobResult"
    assert "per_cube" in data["properties"]


@pytest.fixture
def db_schema():
    """套用 schema（CI 的 postgres service 起始是空的；本地用 IF NOT EXISTS 冪等）。"""
    from orchestration.db import get_connection

    schema_sql = (pathlib.Path(__file__).parents[1] / "sql" / "schema.sql").read_text(encoding="utf-8")
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(schema_sql)


def test_insert_job_result_roundtrip(db_schema):
    """寫入一筆 job + cube_results，查回來核對，最後清掉。"""
    from orchestration.db import get_connection, insert_job_result, query

    sample = {
        "model_tag": "test_epoch",
        "seed": 999999,
        "success": True,
        "cycle_time_steps": 123,
        "failure_stage": None,
        "per_cube": [
            {"cube_color": "blue", "placed_correctly": True, "final_xyz": [0.6, 0.2, 0.03]},
            {"cube_color": "red", "placed_correctly": True, "final_xyz": [0.6, 0.0, 0.03]},
            {"cube_color": "green", "placed_correctly": False, "final_xyz": [0.5, 0.1, 0.02]},
        ],
    }
    job_id = insert_job_result(sample)
    try:
        rows = query("SELECT seed, success, cycle_time_steps FROM jobs WHERE job_id = %s", (job_id,))
        assert rows[0]["seed"] == 999999
        assert rows[0]["success"] is True

        cubes = query(
            "SELECT cube_color, placed_correctly FROM cube_results WHERE job_id = %s ORDER BY cube_color",
            (job_id,),
        )
        assert len(cubes) == 3
        assert {c["cube_color"] for c in cubes} == {"blue", "red", "green"}
    finally:
        # cleanup（cube_results 靠 FK ON DELETE CASCADE 一起刪）
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM jobs WHERE job_id = %s", (job_id,))
