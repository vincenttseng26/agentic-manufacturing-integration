"""MCP 工具層煙霧測試：不接 LLM，直接當 MCP client 連 server，驗證工具探索與 DB 查詢。

用法（從專案根目錄、env_agent 環境）：
    python -m orchestration.check_mcp

預期輸出：三個工具名稱 + jobs 筆數。跑通代表 Client → Server → PostgreSQL 整條路連通，
之後接 Gemini 出問題時，除錯範圍可縮小到 Agent / schema 轉換 / function-calling 流程。
"""
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "orchestration.mcp_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print([t.name for t in (await session.list_tools()).tools])
            result = await session.call_tool("query_db", {"sql": "SELECT COUNT(*) FROM jobs"})
            print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
