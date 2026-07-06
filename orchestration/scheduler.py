"""Phase 4：規則式排程器（APScheduler）— 支援多 checkpoint 並行監控。

每一輪對 `--epochs` 列出的每個 checkpoint 各跑一批：
- 同一輪內三個 checkpoint 用**相同 seed**（配對比較，之後可 McNemar）；
- 跨輪 seed 遞增、不重疊，且從 SEED_BASE(100000) 起，避開既有資料(seed 100-199)。
批量、seed、要跑哪些都是規則式（非 LLM）。

用法（從專案根目錄）：
    # 穩定監控 200/300/1000，每小時各 20 個（需 GPU，長駐；Ctrl+C 停）
    ~/env_agent/bin/python -m orchestration.scheduler --epochs 200,300,1000 --interval-minutes 60 --batch-size 20
    # demo：每 2 分鐘一輪、各 5 個
    ~/env_agent/bin/python -m orchestration.scheduler --epochs 200,300,1000 --interval-minutes 2 --batch-size 5
    # 只跑一輪就結束
    ~/env_agent/bin/python -m orchestration.scheduler --epochs 200,300,1000 --once
    # 空跑測排程（不跑 sim）
    ~/env_agent/bin/python -m orchestration.scheduler --epochs 200,300,1000 --dry-run --interval-minutes 0.1
"""
import argparse
import pathlib
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from apscheduler.schedulers.blocking import BlockingScheduler  # noqa: E402

from orchestration import tools  # noqa: E402

DEFAULT_INTERVAL_MINUTES = 60
DEFAULT_BATCH_SIZE = 20
DEFAULT_EPOCHS = "200,300,1000"
SEED_BASE = 100000  # 監控用 seed 起點，避開既有資料（100-199）
_state = {"cycle": 0}


def _parse_epochs(spec: str) -> list[int]:
    return [int(x) for x in spec.split(",") if x.strip()]


def _tick(epochs: list[int], batch_size: int, dry_run: bool):
    _state["cycle"] += 1
    c = _state["cycle"]
    seed = SEED_BASE + (c - 1) * batch_size  # 本輪三個 checkpoint 共用；跨輪不重疊
    ts = datetime.now().strftime("%H:%M:%S")
    for epoch in epochs:
        if dry_run:
            print(f"[{ts}] (dry-run) 第 {c} 輪：epoch_{epoch} 本應跑 {batch_size} 個 rollout（seed={seed}）")
            continue
        print(f"[{ts}] 第 {c} 輪：epoch_{epoch} 開始跑 {batch_size} 個（seed={seed}）…")
        result = tools.run_batch(num_rollouts=batch_size, seed=seed, epoch=epoch, batch_id=c)
        print(f"[{ts}] 第 {c} 輪：epoch_{epoch} 完成 loaded={result['loaded']} kpi={result['kpi']}")


def main():
    p = argparse.ArgumentParser(description="規則式排程器：定時對多個 checkpoint 各跑一批。")
    p.add_argument("--epochs", type=str, default=DEFAULT_EPOCHS, help="逗號分隔，如 200,300,1000")
    p.add_argument("--interval-minutes", type=float, default=DEFAULT_INTERVAL_MINUTES)
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--once", action="store_true", help="立即跑一輪就結束")
    p.add_argument("--dry-run", action="store_true", help="不跑 sim，只印排程動作（測試用）")
    args = p.parse_args()

    epochs = _parse_epochs(args.epochs)

    if args.once:
        _tick(epochs, args.batch_size, args.dry_run)
        return

    sched = BlockingScheduler()
    sched.add_job(
        _tick, "interval",
        seconds=args.interval_minutes * 60,
        args=[epochs, args.batch_size, args.dry_run],
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    print(f"排程啟動：每 {args.interval_minutes} 分鐘一輪 × epochs={epochs} × {args.batch_size} rollout。Ctrl+C 停止。")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n排程停止。")


if __name__ == "__main__":
    main()
