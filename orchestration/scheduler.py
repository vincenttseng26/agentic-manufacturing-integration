"""Phase 4：規則式排程器（APScheduler）。

每隔固定時間觸發一批 rollout（透過 tools.run_batch → sim → DB）。
批量、seed 都是規則式（非 LLM）。每批用遞增 seed，讓場景不同、資料隨時間變化。

用法（從專案根目錄）：
    # 正式：每小時一批、每批 20 個（需 GPU，長駐執行；Ctrl+C 停）
    ~/env_agent/bin/python -m orchestration.scheduler
    # demo：每 2 分鐘一批、每批 5 個
    ~/env_agent/bin/python -m orchestration.scheduler --interval-minutes 2 --batch-size 5
    # 只跑一批就結束（手動觸發）
    ~/env_agent/bin/python -m orchestration.scheduler --once --batch-size 10
    # 空跑測試排程機制（不跑 sim）
    ~/env_agent/bin/python -m orchestration.scheduler --dry-run --interval-minutes 0.1
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
_state = {"batch": 0}


def _tick(batch_size: int, dry_run: bool):
    _state["batch"] += 1
    b = _state["batch"]
    seed = 1000 + b * 1000  # 每批不同 seed → 場景不同
    ts = datetime.now().strftime("%H:%M:%S")
    if dry_run:
        print(f"[{ts}] (dry-run) 第 {b} 批：本應跑 {batch_size} 個 rollout（seed={seed}）")
        return
    print(f"[{ts}] 第 {b} 批：開始跑 {batch_size} 個 rollout（seed={seed}）…")
    result = tools.run_batch(num_rollouts=batch_size, seed=seed, batch_id=b)
    print(f"[{ts}] 第 {b} 批完成：loaded={result['loaded']} kpi={result['kpi']}")


def main():
    p = argparse.ArgumentParser(description="規則式排程器：定時觸發一批 rollout。")
    p.add_argument("--interval-minutes", type=float, default=DEFAULT_INTERVAL_MINUTES)
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--once", action="store_true", help="立即跑一批就結束")
    p.add_argument("--dry-run", action="store_true", help="不跑 sim，只印出排程動作（測試用）")
    args = p.parse_args()

    if args.once:
        _tick(args.batch_size, args.dry_run)
        return

    sched = BlockingScheduler()
    sched.add_job(
        _tick, "interval",
        seconds=args.interval_minutes * 60,
        args=[args.batch_size, args.dry_run],
        max_instances=1,                 # 不重疊：前一批沒跑完不會再觸發
        coalesce=True,                   # 錯過的多次觸發合併成一次
        next_run_time=datetime.now(),    # 啟動就先跑一批
    )
    print(f"排程啟動：每 {args.interval_minutes} 分鐘一批 × {args.batch_size} 個 rollout。Ctrl+C 停止。")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n排程停止。")


if __name__ == "__main__":
    main()
