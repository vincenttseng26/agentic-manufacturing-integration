"""Phase 3：MCP server（FastMCP），對 Agent 開放工具。

啟動（stdio）：
    cd <專案根> && ~/env_agent/bin/python -m orchestration.mcp_server

工具邏輯在 tools.py（純函式、可單獨測）；本檔只做 MCP 協定包裝。
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from orchestration import tools  # noqa: E402

mcp = FastMCP("agentic-manufacturing")


@mcp.tool()
def get_kpi() -> dict:
    """回傳目前 DB 的整體 KPI、失敗階段 Pareto、各顏色方塊失敗率。回答「成功率多少/哪裡最常失敗」用這個。"""
    return tools.get_kpi()


@mcp.tool()
def query_db(sql: str) -> list[dict]:
    """對 jobs / cube_results 兩張表執行唯讀 SELECT 查詢並回傳結果列。只允許單段 SELECT。"""
    return tools.query_db(sql)


@mcp.tool()
def run_batch(num_rollouts: int = 10, seed: int = 100) -> dict:
    """跑一批分類任務 rollout（需 GPU、耗時數分鐘），結果寫入 DB 後回傳摘要。使用者說「跑 N 個任務」時用這個。"""
    return tools.run_batch(num_rollouts=num_rollouts, seed=seed)


if __name__ == "__main__":
    mcp.run()
