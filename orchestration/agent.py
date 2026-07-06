"""Phase 3b：Gemini Agent 透過 MCP 呼叫工具（手動 bridge）。

繞過 google-genai「把 MCP session 當 tool → deepcopy config 時炸」的問題：
自己去 MCP server 列工具、轉成 Gemini FunctionDeclaration，跑手動 function-calling loop，
工具實際執行透過 MCP `session.call_tool()`。→ Agent 名副其實地「經過 MCP」。

用法（從專案根目錄）：
    # 互動聊天模式（推薦，可連續問、有上下文記憶）
    ~/env_agent/bin/python -m orchestration.agent
    # 一次性提問
    ~/env_agent/bin/python -m orchestration.agent "成功率多少?哪個階段最常失敗?"

⚠️ 不當排程者：排程 / 優先序是規則式（scheduler.py）。API key 從 .env 讀（GEMINI_API_KEY）。
"""
import asyncio
import os
import pathlib
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = pathlib.Path(__file__).parents[1]
MODEL = "gemini-2.5-flash"
MAX_STEPS = 6

SYSTEM_INSTRUCTION = """你是「智慧製造工作站」的監控助理。可用工具（透過 MCP）：
- get_kpi：整體成功率 / 失敗階段 Pareto / 各顏色方塊失敗率。
- query_db：對下面兩張表跑唯讀 SELECT。
- run_batch：跑一批分類任務 rollout（需 GPU、耗時），結果寫入 DB。

資料表：
  jobs(job_id, batch_id, model_tag, created_at, finished_at, seed, success BOOL,
       cycle_time_steps,
       failure_stage [grasp_1/place_1/grasp_2/place_2/grasp_3/place_3 或 NULL], anomaly_flag)
  cube_results(job_id, cube_color [blue/red/green], placed_correctly BOOL, final_x, final_y, final_z)

checkpoint / epoch 通常記在 jobs.model_tag（例：epoch_200、epoch_300）。
使用者問「各 checkpoint 成功率」時，用 query_db 依 model_tag 分組：
COUNT(*) 任務數、SUM(success::int) 成功數、AVG(success::int) 成功率，並用 model_tag 排序或依成功率排序。
回答一般 KPI 問題時優先用 get_kpi；要更細的統計才寫 SELECT 給 query_db。
用繁體中文簡潔回答，並點出重點發現。"""

_TYPE_MAP = {
    "object": "OBJECT", "string": "STRING", "integer": "INTEGER",
    "number": "NUMBER", "boolean": "BOOLEAN", "array": "ARRAY",
}


def _to_schema(js: dict) -> types.Schema | None:
    """JSON Schema（MCP inputSchema，小寫 type）→ google-genai types.Schema（大寫 type）。"""
    if not isinstance(js, dict):
        return None
    t = js.get("type", "string")
    if isinstance(t, list):  # 例如 ["string","null"]
        t = next((x for x in t if x != "null"), "string")
    kw: dict = {"type": _TYPE_MAP.get(t, "STRING")}
    if js.get("description"):
        kw["description"] = js["description"]
    if js.get("enum"):
        kw["enum"] = js["enum"]
    if t == "object":
        props = js.get("properties") or {}
        if props:
            kw["properties"] = {k: _to_schema(v) for k, v in props.items()}
        if js.get("required"):
            kw["required"] = js["required"]
    if t == "array" and js.get("items"):
        kw["items"] = _to_schema(js["items"])
    return types.Schema(**kw)


def _mcp_tools_to_genai(mcp_tools) -> types.Tool:
    decls = []
    for t in mcp_tools:
        schema = t.inputSchema or {}
        params = _to_schema(schema) if schema.get("properties") else None
        decls.append(types.FunctionDeclaration(
            name=t.name, description=t.description or "", parameters=params,
        ))
    return types.Tool(function_declarations=decls)


def _tool_payload(result) -> dict:
    """把 MCP call_tool 結果轉成給 Gemini 的 function_response（需為 dict）。"""
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict):
        return sc
    texts = [getattr(c, "text", "") for c in (result.content or []) if getattr(c, "text", None)]
    return {"result": "\n".join(texts)}


def _child_env() -> dict:
    """MCP server 子行程的乾淨環境（隔離 ROS 的 PYTHONPATH 污染 + 補 PG 連線）。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = ""
    env.setdefault("PGHOST", "localhost")
    env.setdefault("PGPORT", "5432")
    env.setdefault("PGDATABASE", "mfg")
    env.setdefault("PGUSER", "postgres")
    env.setdefault("PGPASSWORD", "devpassword")
    return env


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "orchestration.mcp_server"],
        env=_child_env(),
        cwd=str(PROJECT_ROOT),
    )


async def _converse(client, session, config, contents, model) -> str:
    """跑一輪對話（可能含多次工具呼叫），回傳最終文字；contents 會就地更新（保留上下文）。"""
    for _ in range(MAX_STEPS):
        resp = await client.aio.models.generate_content(model=model, contents=contents, config=config)
        calls = resp.function_calls
        if resp.candidates:
            contents.append(resp.candidates[0].content)  # model 這輪（含 text 或 function_call）
        if not calls:
            return resp.text
        for call in calls:
            result = await session.call_tool(call.name, dict(call.args or {}))
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_function_response(name=call.name, response=_tool_payload(result))],
            ))
    return "(達到最大步數，未得到最終回答)"


async def ask(prompt: str, model: str = MODEL) -> str:
    """一次性提問。"""
    load_dotenv(PROJECT_ROOT / ".env")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=[_mcp_tools_to_genai(listed.tools)],
            )
            contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
            return await _converse(client, session, config, contents, model)


async def chat(model: str = MODEL):
    """互動聊天模式：開一次 MCP session，連續問答並保留上下文。"""
    load_dotenv(PROJECT_ROOT / ".env")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    loop = asyncio.get_event_loop()
    print("智慧製造監控助理（輸入 exit / quit 離開）")
    print("可問：成功率、失敗分布、cycle time…，或叫它「跑 10 個任務」(需 GPU)。\n")
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=[_mcp_tools_to_genai(listed.tools)],
            )
            contents: list = []
            while True:
                q = (await loop.run_in_executor(None, input, "你 > ")).strip()
                if q.lower() in {"exit", "quit", "q", ""}:
                    print("掰掰 👋")
                    break
                contents.append(types.Content(role="user", parts=[types.Part(text=q)]))
                answer = await _converse(client, session, config, contents, model)
                print(f"\n助理 > {answer}\n")


def main():
    args = sys.argv[1:]
    if args:
        print(asyncio.run(ask(" ".join(args))))
    else:
        asyncio.run(chat())


if __name__ == "__main__":
    main()
