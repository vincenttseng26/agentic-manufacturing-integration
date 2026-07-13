# Agentic Manufacturing Integration — 專案規劃筆記

> LLM Agent 編排的智慧製造整合 Demo。
> 對準 TSMC **Automation Systems Integration Engineer (IMC)** 職缺打造的個人專案。

---

## 一句話說明

用 **LLM Agent（ChatGPT / Gemini）** 透過 **MCP** 編排一個模擬自動化工作站
（**Isaac Sim 三方塊分類手臂**），每次任務結果寫進 **SQL（PostgreSQL）**，用 **Power BI 雲端版**
監控良率與異常，並展示「**發現失敗 → 資料分析找根因 → 資料迴圈 → 量測改善**」的閉環。

---

## 專案目標與背景

這是為求職打造的 portfolio 專案，用來補齊履歷缺口。

- 既有作品：模仿學習機械手臂（Isaac Sim + BC-RNN-GMM，已發 Medium / GitHub）
  → 證明「能自學前沿技術、端到端落地」，但**沒展示 SQL / 資料分析 / 系統整合**。
- 本專案補上：**SQL、Power BI、資料分析、系統整合、SDLC / CI-CD**，
  並把手臂作品重新包裝成「自動化工作站」串進來，一魚兩吃。

### 對應 JD 的能力

| JD 要的 | 本專案怎麼證明 |
|---|---|
| SQL / 資料庫 / 資訊架構 | schema 設計 + 查詢 |
| Power BI / 資料分析 | 良率趨勢 / SPC / Pareto 儀表板（雲端版） |
| 系統整合 | 把 sim / agent / DB / BI 串成一條 pipeline |
| 用資料分析找產線問題 | 異常偵測 + 失敗根因（哪顆方塊 / 哪階段） |
| 熟悉 SDLC | CI/CD + 分層可測架構 |
| 自學新技術 | MCP / LLM Agent |

---

## 定位與敘事（面試講點，很重要）

這幾個「刻意的設計決策」本身就是面試加分題，別做反了：

1. **手臂 = 自動化工作站 / 數位分身**，不是宣稱「fab 自動化」。
   （TSMC 真實自動化主體是 AMHS 天車、MES、SECS/GEM，不是機械手臂。誠實定位。）
2. **LLM = 自然語言介面 + 分析副駕**，**不是排程者**。
   fab 排程要求確定性、可稽核，現實用規則 + OR 最佳化，不會讓 LLM 憑空生排程。
   讓 LLM 生排程反而會被懂的面試官看破。
3. **排程 / 優先序 = 規則式**（每小時觸發一批 job），決策邏輯不交給 LLM。
4. **「改進」不是修 ML 模型到完美**（那是研究員的活、很難）。
   本專案示範整合工程師該做的：**用資料把失敗診斷成一句可行動的話**
   （例：「綠方塊在 y<−0.15 起始時夾取失敗率 70%」），
   再跑一次**可量測**的資料迴圈（補錄示範 → Mimic 重生成 → 重訓 → 再量測）。
   不用修到 100%，能展示「發現→假設→行動→用資料驗證」的閉環就贏了。

---

## 技術棧（本次確定版）

| 層 | 元件 | 技術 | 備註 |
|---|---|---|---|
| 工作站 | 三方塊分類手臂 | 現成 Isaac Sim + BC-RNN 策略 | 跑在既有 `env_isaacsim` |
| 執行 | Task Runner | Python：把 `play.py` 包成 `run_job()` 回傳 JSON | sim 層 |
| 工具 | MCP Server | Python `mcp` SDK (FastMCP) | 開 run_job / query_kpi / query_sql |
| 大腦 | LLM Agent | **Google Gemini（雲端 API）— 已選定** | 免費額度佳；用 function calling 對接 MCP 工具 |
| 觸發 | 排程器 | APScheduler 或系統 cron | **規則式**，非 LLM |
| 資料 | 資料庫 | **PostgreSQL** | Docker 起 |
| 分析 | KPI / 異常 | pandas + SPC / 簡單統計 | |
| 呈現 | 儀表板 | **Power BI Service（雲端版）** | 見下方資料路徑注意事項 |
| 品質 | CI/CD | GitHub Actions | **只測編排/資料層**，sim 排除 |
| 打包 | 容器 | Docker + docker-compose | 只包 sim-independent 層 |

---

## 架構圖

```
                 ┌──────────────────┐
                 │ 排程觸發（每小時）  │  APScheduler / cron ← 規則式,非LLM
                 └────────┬─────────┘
                          │ 建立一批 job
   自然語言 ─►┌───────────▼──────────┐
   操作員     │ LLM Agent (GPT/Gemini)│
   查詢   ◄──│ ①NL→任務  ②NL→SQL 分析 │
             └────┬─────────────┬────┘
                  │ MCP 呼叫工具  │ 讀資料
                  ▼             │
            ┌───────────┐        │
            │ MCP Server │        │
            │ run_job    │        │
            │ query_kpi  │        │
            └─────┬─────┘        │
     ┌────────────┴───┐          │
     ▼（sim層,不進CI）  ▼          │
┌──────────────┐ ┌──────────────┐ │
│ Isaac Sim     │ │ PostgreSQL    │◄┘ 寫入結果
│ 3方塊分類工作站 │►│ jobs / 明細    │
│ (BC-RNN 策略)  │ │ KPI / 異常旗標  │
└──────────────┘ └──────┬───────┘
                        ▼
                 ┌──────────────┐
                 │ Power BI 雲端  │ 良率趨勢/Pareto/SPC
                 └──────────────┘
```

### 資料流（一句話）
每小時觸發 → 規則產生一批 N 個 job → MCP `run_job` 逐一叫 Isaac Sim 執行 →
結構化結果寫進 PostgreSQL → 分析層算 KPI＋標異常 → Power BI 呈現；
操作員隨時可用自然語言問 Agent。

---

## 資料表 schema（整個系統的資料契約，先定死；PostgreSQL 語法）

```sql
-- 一次 rollout = 一張「工單/批次」
CREATE TABLE jobs (
  job_id           BIGSERIAL PRIMARY KEY,
  batch_id         BIGINT,
  created_at       TIMESTAMP,
  finished_at      TIMESTAMP,
  seed             INT,
  success          BOOLEAN,
  cycle_time_steps INT,          -- 步數 ≈ cycle time
  failure_stage    VARCHAR(32),  -- 哪一階段失敗（grasp_1 / place_2 ...），成功則 NULL
  anomaly_flag     BOOLEAN DEFAULT FALSE
);

-- 每顆方塊的明細（畫「哪個顏色最常失敗」的 Pareto 用）
CREATE TABLE cube_results (
  job_id           BIGINT REFERENCES jobs(job_id),
  cube_color       VARCHAR(16),  -- blue / red / green
  placed_correctly BOOLEAN,
  final_x REAL, final_y REAL, final_z REAL
);
```

**KPI**：批次成功率、滾動成功率（SPC 用）、平均 cycle time、
依方塊顏色 / 失敗階段的 Pareto。

---

## 分階段施工（每階段都有可展示的產出）

- **Phase 0 — 骨架 & 解耦**：建 repo 結構，切開 sim 層與編排/資料層，
  先定死上面的結果 JSON / SQL schema（契約）。
- **Phase 1 — 手臂→結構化結果**：把現有 `play.py` 重構成 `run_job(seed)`，
  回傳 `{success, steps, failure_stage, per_cube[]}`。產出：跑一次印一筆 JSON。
- **Phase 2 — SQL 落地**：PostgreSQL 建表、寫入、基本查詢。產出：DB 有真實資料。（← 進 CI）
- **Phase 3 — MCP + Agent**：MCP 開 `run_job`/`query_sql`；Agent 做 NL→任務、NL→SQL。
  產出：對 Agent 說「跑 20 個 job」「這批成功率多少」它會做。
- **Phase 4 — 排程**：APScheduler 每小時（demo 設 1 分鐘）規則式產生一批 job。
- **Phase 5 — 分析 + Power BI**：算 KPI、SPC 異常偵測；Power BI 雲端接資料出儀表板。
- **Phase 5.5 — 改善閉環**（面試核心戲）：
  儀表板發現某區失敗率高 → 提根因假設 → 針對該區補錄示範 → Mimic 重生成 → 重訓
  → 再量測，儀表板顯示成功率上升。重點是**可被量測的閉環**，不是修到完美。
- **Phase 6 — CI/CD**：GitHub Actions 跑 ruff + pytest（mock 掉 sim）
  + 起拋棄式 PostgreSQL 測 schema + docker build。

---

## 環境建置 / 要裝什麼

### 兩個虛擬環境（務必分開）
- `env_isaacsim`（既有，脆弱，別動）：**只**跑 sim 層（`run_job` 包 play.py）。
- **新開 `env_agent`**（乾淨）：裝編排/資料層套件。兩邊透過 MCP 溝通。

```bash
# 新環境
python3.11 -m venv ~/env_agent && source ~/env_agent/bin/activate

# 編排/資料層套件
pip install mcp openai google-generativeai   # Agent（二選一或都裝）
pip install "psycopg[binary]"                 # PostgreSQL 驅動 (psycopg3)
pip install apscheduler pandas
pip install ruff pytest pytest-mock           # CI / 開發
```

### 要付費 / 要帳號的（只有兩樣）
1. **LLM API key**：OpenAI 或 Google Gemini，**設好用量上限**。
   例行 NL→SQL 用便宜模型，複雜分析才用強模型。
2. **Power BI**：用雲端 **Power BI Service**（有免費層；分享/協作某些功能可能需 Pro，實作前確認）。

### PostgreSQL（Docker 起，免污染系統、跟 CI 一致）
```bash
docker run -d --name mfg-postgres -p 5432:5432 \
  -e POSTGRES_PASSWORD=xxxx -e POSTGRES_DB=mfg postgres:16
```

### ⚠️ Power BI 雲端連資料庫的資料路徑（重要坑）
Power BI Service 在雲端、DB 在本機，要**先想好資料怎麼餵**，三選一：
- ① DB 也放雲端（雲端 PostgreSQL / 免費層）→ 雲端 Power BI 直連（最順）
- ② 上傳**彙總後的靜態資料**（CSV / import）→ 不會即時刷新，但 demo 夠用
- ③ 裝 on-premises data gateway（又是 Windows-only，最麻煩，不建議）

---

## 關鍵決策與踩雷（別重蹈覆轍）

- ⚠️ **Isaac Sim 不進 CI**：吃 GPU、太大、要授權，一般 runner 跑不動。
  CI 只測 sim-independent 層。這個切分本身是面試加分講點。
- ⚠️ **兩個 venv 分開**：別把 mcp/openai 裝進 `env_isaacsim`，那環境很脆弱
  （torch cu128 + pink 衝突的歷史坑）。
- ⚠️ **`play.py` 要重構成可程式呼叫、回傳結構化結果**的 `run_job()`：這是 Phase 1 主要工。
- ⚠️ **LLM 不當排程者**：排程 / 優先序用規則，別交給 LLM（見上方「定位與敘事」）。
- ⚠️ **Power BI 雲端資料路徑**：見上一節，先解決再開工。
- 💡 資安故事（備用）：若之後把 Agent 換成本機 Ollama（RTX 5080 跑得動），
  可主打「on-prem、資料不出廠」——命中半導體資安痛點。

---

## 相關路徑指標（給未來的自己 / Claude）

- 現有手臂 overlay repo：`/home/vincent/Downloads/imitation learning tutorial/isaac-lab-cube-sort`
- 原專案筆記（手臂/堆疊/分類完整指令）：`/home/vincent/Downloads/imitation learning tutorial/19_SMMG/CLAUDE.md`
- Isaac 環境：`source ~/env_isaacsim/bin/activate`，`cd ~/IsaacLab`
- 分類任務 ID：`Isaac-Sort-Cube-Franka-IK-Rel-v0`（play）、`...-Mimic-v0`（標注/生成）
- ⚠️ play.py 記得 `--horizon 1800`（否則假性 0%）；生成完立刻備份 hdf5。

---

## MVP 優先路線（別一路做到完美才收尾）

先打通一條端到端垂直切片，約 1 週全職就有可 demo 雛形：

```
Phase 0 → 1 → 2 → 極簡版 3（只做 run_job 工具）→ 5（先用靜態 CSV 上 Power BI）
```

先讓它會動、能講故事，再回頭補 NL→SQL 分析、SPC 異常、CI/CD、改善閉環（5.5）。

## Phase 1 結果 / 已知發現

- `sim/run_job.py` 完成並實測通過：啟動 sim 一次 → 跑 N 個 rollout → 每筆寫一行 JSONL（符合契約）。
- Sort checkpoint 路徑：
  `.../19_SMMG/training_logs/Isaac-Sort-Cube-Franka-IK-Rel-v0/bc_rnn_low_dim_franka_stack/20260612105251/models/model_epoch_XXXX.pth`
- 🔍 **發現（epoch 200、5 rollouts、40%）**：3 次失敗**全部卡在綠方塊（cube_3）**
  （place_3 ×2、grasp_3 ×1）。系統性弱點 = 末端子任務（累積誤差 + 綠盤在最遠 y=−0.2）。
  → 這是 Phase 5.5 改善閉環的素材：針對綠方塊 / 遠端區域補錄示範重訓，預期可提升。
- `placed_correctly` 已改為「純物理落點」判定（不看夾爪），與 `success` 分工；**改動後需重跑才會反映**。
- ⚠️ ruff 之後（Phase 6）要排除 `sim/` 的 E402（Isaac Lab 腳本必須 AppLauncher 後才 import，屬正常）。

## Phase 2 結果

- `env_agent` 已建（Python 3.11.15、psycopg 3.3.4、pytest、ruff）。
- Postgres + Adminer 用 `docker compose up -d` 起（容器名 `mfg-postgres`/`mfg-adminer`）；
  schema.sql 開機自動套用建表。Adminer：http://localhost:8080（PostgreSQL / 主機 `postgres` / `postgres`:`devpassword`）。
- `orchestration/db.py`：`insert_job_result()`、`query()`。
- `orchestration/load_results.py`：把 run_job 的 JSONL 灌進 DB。
  用法：`~/env_agent/bin/python orchestration/load_results.py data/results.jsonl --batch-id 1`
- 測試通過：`tests/test_db.py`（契約檔 + DB roundtrip）。
- ⚠️ **本機跑 pytest 要清 `PYTHONPATH`**：shell 有 source ROS 2 Jazzy，會把 `/opt/ros/jazzy`(py3.12)
  塞進 PYTHONPATH，pytest 自動載入 ROS 外掛而爆（No module named 'yaml'）。指令前面加 `PYTHONPATH=` 即可。
  （CI 是乾淨 ubuntu，無此問題。）
- 連線預設對齊 docker-compose：`PGHOST=localhost PGPORT=5432 PGDATABASE=mfg PGUSER=postgres PGPASSWORD=devpassword`。
- 📦 **repo 破例放行範例資料 `data/sample_sweep.jsonl`**（`.gitignore` 用 `!data/sample_sweep.jsonl`；其餘 data/ 照舊不進 git）：
  全 20 個 checkpoint × 300（seed 100-399）= 6000 筆，重現早停/過擬合曲線。**用途＝讓沒 GPU 的讀者**照著跑
  DB → 分析 → Power BI，不必自己跑 sim（呼應環境隔離主軸；配合 Medium 系列文）。
  載入：`~/env_agent/bin/python orchestration/load_results.py data/sample_sweep.jsonl --batch-id 1`。
  ⚠️ `.gitignore` **不支援行尾註解**，放行規則的 `#` 說明要獨立一行（踩過：inline 註解會被當成 pattern 一部分而失效）。

## Phase 5（資料側）結果

- `analysis/kpi.py`：純函式（summary / rolling 成功率 / p-chart SPC 管制界 / 失敗 Pareto / cube miss rate），無 sim 依賴、可進 CI。
- `analysis/export_powerbi.py`：從 DB 撈 → 算 KPI → 匯出兩張 CSV 給 Power BI 雲端 import。
  用法：`~/env_agent/bin/python analysis/export_powerbi.py --out-dir data`
  產出 `data/powerbi_jobs.csv`（含 SPC 欄位）、`data/powerbi_cube_results.csv`（job_id 關聯）。
- 測試：`tests/test_kpi.py`（4 個純函式測試，不需 DB）。全套 **6 passed**。
- Power BI 雲端資料路徑**已定：選 ② 上傳 CSV import**（demo 夠用，不用 gateway）。
- ⚠️ Power BI Service 剩「人工步驟」（需你的帳號）：上傳兩張 CSV、建 job_id 關聯、拉視覺
  （成功率卡片、SPC 線圖、cycle time 分布、failure_stage Pareto、cube miss 長條）。

## Phase 3 結果

- `orchestration/tools.py`：工具業務邏輯（純函式）— `get_kpi` / `query_db`（唯讀 SELECT 防護）/ `run_batch`。
- `orchestration/mcp_server.py`：FastMCP 把上述工具以 MCP 對外開放（供 Claude Desktop 等 MCP client）。
  啟動：`~/env_agent/bin/python -m orchestration.mcp_server`。
- `orchestration/agent.py`：**Gemini（gemini-2.5-flash）Agent，透過 MCP 呼叫工具**（Phase 3b 手動 bridge）。
  流程：連 MCP server → `list_tools` → 轉成 Gemini FunctionDeclaration → 手動 function-calling loop →
  工具經 `session.call_tool()` 在 MCP server 上執行。NL→分析、NL→SQL **已實測通過**
  （執行時 log 會出現 `ListToolsRequest` / `CallToolRequest`，即證明真的走 MCP）；
  `run_batch`（NL→任務）已接線但**未測**（需 GPU）。
  用法：互動聊天（推薦，可連續問、有上下文記憶）`~/env_agent/bin/python -m orchestration.agent`；
  或一次性 `... -m orchestration.agent "成功率多少?哪個階段最常失敗?"`。
- 測試 `tests/test_tools.py`（唯讀防護 + JSON 轉換，不需 DB/Gemini）。全套 **11 passed**。
- 🐞 **google-genai 三個踩雷（皆已解）**：
  1. **`from __future__ import annotations` 會讓 automatic function calling 爆**：annotation 變字串，
     SDK 對回傳值做 `isinstance(result, "list")` → `isinstance() arg 2 must be a type`。
     → **交給 Gemini 當工具的函式所在模組不可有 future annotations**（agent.py 已移除）。
  2. **Postgres `AVG()` 回傳 Decimal**，automatic function calling 序列化 JSON 會失敗 →
     `query_db` 已把 Decimal/datetime 轉成 JSON 安全型別（`_jsonable`）。
  3. 把 MCP `session` 當 tool 傳給 google-genai 會在 deepcopy config 時炸（無法 pickle asyncio.Future）。
     → 已解（Phase 3b）：改用**手動 bridge**——自己列工具、轉 FunctionDeclaration、跑手動 FC loop，
     不把 session 塞進 config。Agent 現在名副其實地經過 MCP。

## 常用指令：生更多資料 → 重匯出 → 上 Power BI

Power BI 上傳的是 `data/powerbi_data.xlsx`（jobs + cube_results 兩工作表）。
資料太少 dashboard 會很空，先在 GPU 上生 40 筆再上傳：

```bash
# 1) 生 40 筆（env_isaacsim, GPU, 數分鐘~半小時）
source ~/env_isaacsim/bin/activate && cd ~/IsaacLab
PROJ="/home/vincent/Documents/agentic-manufacturing-integration"
CKPT="/home/vincent/Downloads/imitation learning tutorial/19_SMMG/training_logs/Isaac-Sort-Cube-Franka-IK-Rel-v0/bc_rnn_low_dim_franka_stack/20260612105251/models/model_epoch_200.pth"
./isaaclab.sh -p "$PROJ/sim/run_job.py" --task Isaac-Sort-Cube-Franka-IK-Rel-v0 \
  --checkpoint "$CKPT" --num_rollouts 40 --seed 100 --horizon 1800 --headless --device cuda \
  --out "$PROJ/data/results.jsonl"

# 2) 清舊資料、重灌、重匯出（env_agent, 不需 GPU；db.py 預設連線已對齊 docker）
cd "$PROJ"
docker exec mfg-postgres psql -U postgres -d mfg -c "TRUNCATE jobs, cube_results RESTART IDENTITY CASCADE;"
PYTHONPATH= ~/env_agent/bin/python orchestration/load_results.py data/results.jsonl --batch-id 1
PYTHONPATH= ~/env_agent/bin/python analysis/export_powerbi.py --out-dir data
```

Power BI 雲端（登入 app.powerbi.com，學校帳號可用）：上傳 `powerbi_data.xlsx` →
建 5 個單表視覺（成功率卡片 / SPC 折線 rolling_success_rate+ucl+lcl / cycle_time 柱狀 /
failure_stage Pareto / cube_color 失敗長條）→ Publish 取分享連結。

Docker 容器（mfg-postgres/mfg-adminer）跨 session 會持續跑、資料存在 volume；要停 `docker compose down`（資料保留）。

## Power BI 儀表板（完成）

- 資料集：epoch 200、**40 rollouts、成功率 57.5%**（23/40）；已灌 DB、匯出 `data/powerbi_data.xlsx`。
- 上傳：Power BI Service（學校帳號，檔案存到 OneDrive/SharePoint）→ Power Query 把活頁簿拆成
  `jobs` + `cube_results` 兩張表（右鍵「參考」→ 點 Data 欄 `[Table]` 下鑽 → 需要時「使用第一列作為標題」）。
- 5 個視覺（皆單表、免關聯）：
  1. 卡片＝`success_int` 平均（0.58）
  2. 直條＝`cycle_time_steps` 平均 by `success`（失敗 ~1800 vs 成功 ~1000，成功較快）
  3. 折線 SPC＝`rolling_success_rate` + `ucl` + `lcl` by `job_id`（各值改「不摘要/平均」）
  4. 橫條 Pareto＝`failure_stage` 計數，篩掉「(空白)」（place_3=10 ≫ place_2=4 > place_1=2 > grasp_3=1）
  5. 橫條＝`cube_color` 計數（cube_results 表），篩 `placed_correctly=False`（綠 17 > 紅 6 > 藍 4）
- 資料敘事：抓取（grasp_1/2）從不失敗、失敗集中在「放置」且往後段（綠 / place_3）遞增 → 累積誤差根因。
- ⚠️ 踩雷：`placed_correctly=False` 篩選一定要放**「此視覺效果上的篩選」**；放到頁面層級會經 `job_id`
  關聯把卡片成功率也拉成 0（成功 job 三顆都放對、沒有 False 的 cube 列）。
- ⚠️ SPC 管制界目前 `ucl=1.0 / lcl=0.0`（40 筆、變異大被夾到 [0,1] 邊界，抓不到異常）；資料量更大才會收窄、異常偵測才有意義（面試可能被問）。
- 作品保存：**以截圖為主**（放 Medium / GitHub）。`app.powerbi.com/links/...` 共用連結綁帳號授權，
  免費版 / Pro 試用到期會失效，不當長期依靠。

## Phase 4 排程器（scheduler.py）

- `orchestration/scheduler.py`：APScheduler 定時觸發一批 rollout（規則式，非 LLM）。
  每批**遞增 seed** → 場景不同、資料隨時間變化；`max_instances=1` 不重疊（前批沒跑完不觸發）。
- 「每小時執行多少」= 兩旋鈕：**觸發頻率(`--interval-minutes`) × 批量(`--batch-size`)**。
  正式建議：每 **60 分**一批 × **20 個** = 20 筆/小時（≈480/天，SPC 才有料）。
- 用法：正式 `python -m orchestration.scheduler`；demo `--interval-minutes 2 --batch-size 5`；
  手動一批 `--once`；空跑測排程 `--dry-run`。
- 排程機制已用 **dry-run 實測**（遞增 seed 定時觸發）；**真跑需 GPU**（tick → tools.run_batch → sim）。

## Checkpoint 比較（model_tag）

- jobs 加了 `model_tag` 欄（哪個 checkpoint）。`run_job.py` 自動從 checkpoint 檔名推
  （`model_epoch_200` → `epoch_200`），也可 `--model-tag` 指定；db / export / contract 都已帶上。
  現有 40 筆已回填為 `epoch_200`。
- 比較策略：選 **200 / 1000 / 1100**（10 次掃描時成功率 >0.6 的三個），各用**相同 seed（100 起）40 個**
  跑，場景一致才公平。
- 生比較資料（各 epoch **用不同 output 檔**、載入用**不同 batch_id**、**不要 truncate**，要累積三組）：
  ```bash
  # env_isaacsim, GPU
  CKDIR="/home/vincent/Downloads/imitation learning tutorial/19_SMMG/training_logs/Isaac-Sort-Cube-Franka-IK-Rel-v0/bc_rnn_low_dim_franka_stack/20260612105251/models"
  PROJ="/home/vincent/Documents/agentic-manufacturing-integration"
  ./isaaclab.sh -p "$PROJ/sim/run_job.py" --task Isaac-Sort-Cube-Franka-IK-Rel-v0 \
    --checkpoint "$CKDIR/model_epoch_1000.pth" --num_rollouts 40 --seed 100 --horizon 1800 --headless --device cuda \
    --out "$PROJ/data/results_epoch1000.jsonl"   # 1100 同理換檔名
  # env_agent
  ~/env_agent/bin/python orchestration/load_results.py data/results_epoch1000.jsonl --batch-id 2
  ~/env_agent/bin/python orchestration/load_results.py data/results_epoch1100.jsonl --batch-id 3
  ~/env_agent/bin/python analysis/export_powerbi.py --out-dir data
  ```
- **20-checkpoint sweep**（`sim/sweep_checkpoints.py`，sim **只啟動一次**、內部換 policy）：
  先 `--calibrate`（跑一個估總時長），再全掃 `--epochs 100-2000:100 --num-rollouts 100 --seed 100 --out-dir data/sweep`。
  每個 checkpoint 一份 JSONL。完成後 **TRUNCATE → 迴圈 load `data/sweep/*.jsonl` → export**（sweep 會重生 200/1000/1100，故清空重來）。
- Power BI 比較視覺：**折線圖**（X＝`model_epoch` 數字、Y＝`success_int` 平均 → 可靠版的 epoch-成功率曲線）
  或長條圖（軸＝`model_tag`）。`model_epoch` 由 export 自動從 `model_tag` 抽數字，供 X 軸正確排序。
- ⚠️ **load_results 是 append，別對同一檔重載**（會重複；曾把 40 灌成 80、cube 240）。
  要重來先 `docker exec mfg-postgres psql -U postgres -d mfg -c "TRUNCATE jobs, cube_results RESTART IDENTITY CASCADE;"`。
- 📊 **Sweep 結果（20 ckpt × 50，seed 100-149；epoch_100=100，2026-07-03）**：成功率**早期高峰、後期下滑**——
  🥇 epoch 300/200＝**60%**、600＝54%、800＝46%、1000＝44%；**epoch 2000（最後一個、Medium 用的）僅 30%**（最佳的一半）；epoch 100＝3%。
  → 核心洞察：**訓練越久反而過擬合示範、成功率腰斬**（早停 early-stopping 教科書案例；別預設用最後一個 checkpoint）。
  → 統計：200/300/600 在 n=50 下**分不出**（60% 的 95% CI≈[46,74%]）；但「早期 vs 晚期(2000)」z≈3.2 **顯著**。
  → 決選＝**200/300/600**，要分第一需對這 3 個加碼樣本（新 seed 範圍）+ McNemar 配對檢定。
- 📈 **加碼到 n=300（fresh sweep，全 20 個 × 300、seed 100-399，2026-07-05；跑到 17/20 時的觀察）→ 排名分開了**：
  🥇 **epoch_300＝64%**（從「並列」變明顯領先）、epoch_200＝58%、epoch_1000＝47%、
  **epoch_600＝46%（從 54% 打回原形＝小樣本假象）**、epoch_100＝3%。
  → n=50 時 200/300 並列、600 看似第三；**n=300 後 300 拉開成第一、600 現出原形**——又一個「小樣本會騙人」的活教材。
  → **最終（20×300 全跑完、已載入 DB，2026-07-06）**：epoch_300=64.3%、200=58.3%、1000=46.7%、600=46.0%、2000=30%、100=3%。
  → **300 vs 200 即使用 matched-seed McNemar 仍不顯著**（300 場景：只 300 贏 80、只 200 贏 62，精確雙尾 **p=0.15**）
     → 誠實結論：**200/300 統計上並列（co-best）**，300 只是點估計較高、對戰勝場略多；**不宣稱 300 是唯一最佳**。
  → 但「早期(200/300~60%)**決定性**優於晚期(1000↓、2000=30%)」高度顯著（vs 1000 z≈4.4）。
  → 部署選 **epoch_300**（最佳猜測）或 200；要再分高下可用次要指標（cycle time）。
  → 教訓再現：**6% 差距，n=300 都分不出**（樣本數的殘酷 + 誠實勝過過度宣稱）。
  → ⚠️ **修正監控名單**：`scheduler.py` 原本 `DEFAULT_EPOCHS` 設 `200,300,600`，是沿用 n=50 時代「600 排第三」的舊決策；
     n=300 資料顯示 600 其實跟 1000 打平（46.0% vs 46.7%），已不算前段班 → 一度改成 `200,300,1000`。
  → ⚠️ **再次修正**：既然是「比較」，`epoch_1000`（46.7%）跟真決選 200/300（58~64%）差距明顯，放進去反而讓人誤以為它也是有競爭力的候選；
     `200/300` 才是統計上真正並列（McNemar 不顯著）的兩個決選 → **最終改成只監控 `200,300`**，`1000` 拿掉。

## 統計分析準則（checkpoint 評估 / 之後所有分析共用）

指標＝成功率（比例、Bernoulli 試驗）→ 用二項統計。

- **精度**：`SE = √(p(1-p)/n)`；95% CI ≈ ±1.96·SE。n=10→±31%（不可信）、40→±15%、50→±14%、100→±10%。
  `SE ∝ 1/√n`（誤差減半要 4 倍資料 → 報酬遞減，別過量）。
- **樣本數（精度 vs 成本權衡）**：廣掃各 **50**（差異大時夠找好區間）；決選 top 2-3 加大到 **100~200**（要分辨接近者）。
- **設計**：**配對 matched seeds**（各 checkpoint 用相同 seed）→ 消場景難易雜訊、增檢定力。
- **檢定**：排名用點估計＋CI；「A 是否真的贏 B」用 two-proportion z 檢定（獨立）或 **McNemar**（配對，較強）。
  多重比較（20 個兩兩比）會膨脹假陽性 → 只對**預先選定的決選者**做 confirmatory 檢定（避免 p-hacking）。
- **實例（n=40）**：200(57.5%) vs 1100(30%)→z≈2.6 **顯著**；200 vs 1000(50%)→z≈0.67 **分不出**（需更多樣本）。
- **子群分析**：失敗模式 / per-cube / cycle-time 是在子群做，n 更小；每個要比較的子群至少 ~30 個。
- **Power BI 敘事**：折線圖（X=`model_epoch`、Y=成功率、**加 CI 誤差棒**）=主軸；決選長條（含 CI，重疊=分不出）；
  失敗 Pareto / cube 以 `model_tag` 為圖例=失敗模式比較；cycle time=效率；SPC=上線後監控。
- **結論寫法**：報點估計＋CI，明說哪些差異顯著、哪些未定。**誠實 > 過度宣稱**（資料職最加分）。
- 故事線：天真 10 次(假象) → 統計醒悟(小樣本±31%) → 配對嚴謹重測 → 逆轉(1100 崩、200 最佳) → 根因(綠方塊累積誤差) → 選 200 上線 + SPC 監控。

## 下一步（待辦）

- [x] Phase 0：repo 骨架 + schema 契約
- [x] Phase 1：`run_job()` — 已實測
- [x] Phase 2：DB + docker postgres + pytest — 已實測
- [x] Phase 5（資料側）：kpi + CSV 匯出 — 已實測
- [x] Agent = **Gemini**、API key 已設（.env）
- [x] Phase 3（極簡版）：MCP server + Gemini Agent（NL→分析/SQL）— 已實測
- [x] 重跑 40 筆乾淨資料 → 重灌 DB → 重匯出（epoch 200、57.5%）
- [x] Power BI 雲端：5 視覺儀表板完成（作品以截圖保存）
- [x] Phase 4：APScheduler 排程 — 排程機制已測（dry-run）；真跑需 GPU
- [ ] 在你 GPU 機上實測 `run_batch`（NL→任務，會真的透過 agent/MCP 跑 sim）
- [ ] Phase 6：CI（ruff 排除 sim/ E402）
- [ ] 實作統計 helper（見「統計分析準則」）：`success_rate_ci`（每 model_tag 成功率+95%CI）、
      `compare_checkpoints`（McNemar 配對 / two-proportion z）、匯出 `powerbi_model_summary.csv`（含 CI 誤差棒）
- [ ] 加樣本策略：先 20×50（seed 100-149）；決選者才加碼，**用新 seed 範圍（200 起）+ 不同檔名**避免重複
- [ ] （選）Phase 5.5 改善閉環：針對綠方塊 / 遠端補錄示範 → 重生成 → 重訓 → 量測
- [x] Phase 3b：agent→MCP 手動 bridge — 已實測（log 見 ListTools/CallTool）
