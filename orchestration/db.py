"""Phase 2：PostgreSQL 寫入 / 查詢 helper（env_agent）。

連線資訊從環境變數讀，預設對齊 docker-compose.yml：
  PGHOST=localhost PGPORT=5432 PGDATABASE=mfg PGUSER=postgres PGPASSWORD=devpassword
"""
from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row


def _conninfo() -> str:
    return (
        f"host={os.getenv('PGHOST', 'localhost')} "
        f"port={os.getenv('PGPORT', '5432')} "
        f"dbname={os.getenv('PGDATABASE', 'mfg')} "
        f"user={os.getenv('PGUSER', 'postgres')} "
        f"password={os.getenv('PGPASSWORD', 'devpassword')}"
    )


def get_connection() -> psycopg.Connection:
    return psycopg.connect(_conninfo())


def insert_job_result(result: dict, batch_id: int | None = None) -> int:
    """寫入一筆 job + 對應的 cube_results，回傳 job_id。

    result 需符合 contracts/job_result.schema.json。
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO jobs
                (batch_id, model_tag, finished_at, seed, success, cycle_time_steps, failure_stage)
            VALUES (%s, %s, NOW(), %s, %s, %s, %s)
            RETURNING job_id
            """,
            (batch_id, result.get("model_tag"), result["seed"], result["success"],
             result["cycle_time_steps"], result["failure_stage"]),
        )
        job_id = cur.fetchone()[0]

        for cube in result["per_cube"]:
            xyz = cube.get("final_xyz") or [None, None, None]
            cur.execute(
                """
                INSERT INTO cube_results
                    (job_id, cube_color, placed_correctly, final_x, final_y, final_z)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (job_id, cube["cube_color"], cube["placed_correctly"], xyz[0], xyz[1], xyz[2]),
            )
    return job_id


def query(sql: str, params: tuple | None = None) -> list[dict]:
    """唯讀查詢，回傳 list[dict]。

    ⚠️ Phase 3 的 NL→SQL 只走這條、且需限制唯讀（見 agent.py）。
    """
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()
