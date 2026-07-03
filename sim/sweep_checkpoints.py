# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# SPDX-License-Identifier: BSD-3-Clause
#
# Derived from sim/run_job.py (which derives from Isaac Lab play.py).
"""Checkpoint sweep：掃描多個 checkpoint，每個跑 N 個 rollout，各寫一份 JSONL。

sim **只啟動一次**、內部換 policy（省掉每個 checkpoint 重啟的 startup 稅）。
跑在 env_isaacsim（GPU），不進 CI。每個 checkpoint 一份 JSONL（跑一個存一個，中途當掉不會全丟）。

用法（透過 isaaclab.sh）：
    cd ~/IsaacLab
    ./isaaclab.sh -p "<PROJ>/sim/sweep_checkpoints.py" \
      --checkpoint-dir "<CKDIR>" \
      --epochs 100-2000:100 \
      --num-rollouts 100 --seed 100 --horizon 1800 --headless --device cuda \
      --out-dir "<PROJ>/data/sweep"

先估總時長：加 --calibrate（只跑第一個 checkpoint、印出推估的總時數後退出）。
--epochs 也可指定清單粗掃：--epochs 100,300,500,700,900,1100,1300,1500,1700,1900
"""
import argparse

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Sweep multiple checkpoints, N rollouts each.")
parser.add_argument("--disable_fabric", action="store_true", default=False)
parser.add_argument("--task", type=str, default="Isaac-Sort-Cube-Franka-IK-Rel-v0")
parser.add_argument("--checkpoint-dir", type=str, required=True, help="放 model_epoch_*.pth 的資料夾")
parser.add_argument("--epochs", type=str, required=True, help="如 100-2000:100 或 100,300,500")
parser.add_argument("--num-rollouts", type=int, default=100)
parser.add_argument("--seed", type=int, default=100, help="base seed；每個 rollout 用 seed+trial（各 checkpoint 相同）")
parser.add_argument("--horizon", type=int, default=1800)
parser.add_argument("--out-dir", type=str, required=True, help="每個 checkpoint 的 JSONL 輸出資料夾")
parser.add_argument("--calibrate", action="store_true", help="只跑第一個 checkpoint 計時、推估總時長後退出")
parser.add_argument("--norm_factor_min", type=float, default=None)
parser.add_argument("--norm_factor_max", type=float, default=None)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

"""Rest everything follows."""

import copy
import json
import pathlib
import random
import time

import gymnasium as gym
import numpy as np
import robomimic.utils.file_utils as FileUtils
import robomimic.utils.torch_utils as TorchUtils
import torch

from isaaclab_tasks.utils import parse_env_cfg

SUBTASK_ORDER = ["grasp_1", "place_1", "grasp_2", "place_2", "grasp_3", "place_3"]
CUBE_MAP = {
    "blue": ("cube_1", "container_blue"),
    "red": ("cube_2", "container_red"),
    "green": ("cube_3", "container_green"),
}
PLACE_XY_THRESHOLD = 0.06
PLACE_H_THRESHOLD = 0.06


def _scalar(t) -> bool:
    return bool(t.reshape(-1)[0].item())


def parse_epochs(spec: str) -> list[int]:
    """'100-2000:100' → [100,200,...,2000]；'100,300,500' → [100,300,500]。"""
    spec = spec.strip()
    if "-" in spec and ":" in spec:
        rng, step = spec.split(":")
        lo, hi = rng.split("-")
        return list(range(int(lo), int(hi) + 1, int(step)))
    return [int(x) for x in spec.split(",") if x.strip()]


def rollout(policy, env, success_term, horizon, device) -> tuple[bool, int, str | None]:
    """跑一個 rollout。回傳 (success, cycle_time_steps, failure_stage)。與 run_job 一致。"""
    policy.start_episode()
    obs_dict, _ = env.reset()
    ever = {k: False for k in SUBTASK_ORDER}
    success = False
    steps = 0
    for i in range(horizon):
        steps = i + 1
        obs = copy.deepcopy(obs_dict["policy"])
        for ob in obs:
            obs[ob] = torch.squeeze(obs[ob])
        actions = policy(obs)
        if args_cli.norm_factor_min is not None and args_cli.norm_factor_max is not None:
            actions = ((actions + 1) * (args_cli.norm_factor_max - args_cli.norm_factor_min)) / 2 + args_cli.norm_factor_min
        actions = torch.from_numpy(actions).to(device=device).view(1, env.action_space.shape[1])
        obs_dict, _, terminated, truncated, _ = env.step(actions)
        st = obs_dict["subtask_terms"]
        for k in SUBTASK_ORDER:
            if _scalar(st[k]):
                ever[k] = True
        if _scalar(success_term.func(env, **success_term.params)):
            success = True
            break
        if terminated or truncated:
            break
    failure_stage = None
    if not success:
        failure_stage = next((k for k in SUBTASK_ORDER if not ever[k]), None)
    return success, steps, failure_stage


def collect_per_cube(env) -> list[dict]:
    """每顆方塊最終物理落點（不看夾爪）。與 run_job 一致。"""
    origin = env.scene.env_origins[0]
    per_cube = []
    for color, (cube_name, container_name) in CUBE_MAP.items():
        cube_pos = env.scene[cube_name].data.root_pos_w[0]
        container_pos = env.scene[container_name].data.root_pos_w[0]
        diff = cube_pos - container_pos
        xy_dist = torch.linalg.vector_norm(diff[:2]).item()
        height_dist = abs(diff[2].item())
        placed = xy_dist < PLACE_XY_THRESHOLD and height_dist < PLACE_H_THRESHOLD
        per_cube.append({
            "cube_color": color,
            "placed_correctly": placed,
            "final_xyz": (cube_pos - origin).tolist(),
        })
    return per_cube


def run_one_checkpoint(env, success_term, device, epoch: int, out_dir: pathlib.Path) -> tuple[int, float]:
    """跑單一 checkpoint 的 N 個 rollout，寫 JSONL。回傳 (成功數, 用時秒)。"""
    ckpt = pathlib.Path(args_cli.checkpoint_dir) / f"model_epoch_{epoch}.pth"
    model_tag = f"epoch_{epoch}"
    policy, _ = FileUtils.policy_from_checkpoint(ckpt_path=str(ckpt), device=device)
    out_path = out_dir / f"results_epoch{epoch}.jsonl"

    t0 = time.time()
    n_ok = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for trial in range(args_cli.num_rollouts):
            seed = args_cli.seed + trial
            torch.manual_seed(seed)
            np.random.seed(seed)
            random.seed(seed)
            env.seed(seed)
            success, steps, failure_stage = rollout(policy, env, success_term, args_cli.horizon, device)
            per_cube = collect_per_cube(env)
            f.write(json.dumps({
                "model_tag": model_tag,
                "seed": seed,
                "success": success,
                "cycle_time_steps": steps,
                "failure_stage": failure_stage,
                "per_cube": per_cube,
            }) + "\n")
            f.flush()
            n_ok += int(success)
    return n_ok, time.time() - t0


def main():
    all_epochs = parse_epochs(args_cli.epochs)
    out_dir = pathlib.Path(args_cli.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 環境只建一次
    env_cfg = parse_env_cfg(args_cli.task, device=args_cli.device, num_envs=1, use_fabric=not args_cli.disable_fabric)
    env_cfg.observations.policy.concatenate_terms = False
    env_cfg.terminations.time_out = None
    env_cfg.recorders = None
    success_term = env_cfg.terminations.success
    env_cfg.terminations.success = None
    env = gym.make(args_cli.task, cfg=env_cfg).unwrapped
    device = TorchUtils.get_torch_device(try_to_use_cuda=True)

    run_epochs = all_epochs[:1] if args_cli.calibrate else all_epochs
    n = args_cli.num_rollouts
    print(f"[sweep] 掃 {len(all_epochs)} 個 checkpoint × {n} rollout；out_dir={out_dir}")

    summary = []
    for idx, epoch in enumerate(run_epochs, 1):
        ckpt = pathlib.Path(args_cli.checkpoint_dir) / f"model_epoch_{epoch}.pth"
        if not ckpt.exists():
            print(f"[sweep] 跳過 epoch {epoch}（找不到 {ckpt}）")
            continue
        n_ok, dt = run_one_checkpoint(env, success_term, device, epoch, out_dir)
        rate = n_ok / n if n else 0.0
        summary.append((epoch, rate))
        print(f"[sweep] ({idx}/{len(run_epochs)}) epoch_{epoch}: 成功率 {n_ok}/{n}={rate:.0%}  用時 {dt/60:.1f} 分")

        if args_cli.calibrate:
            print(f"\n[calibrate] 單一 checkpoint ≈ {dt/60:.1f} 分；"
                  f"全部 {len(all_epochs)} 個 ≈ 約 {dt * len(all_epochs) / 3600:.1f} 小時。")
            break

    if not args_cli.calibrate and summary:
        print("\n=== Sweep 結果（依成功率排序）===")
        for epoch, rate in sorted(summary, key=lambda x: x[1], reverse=True):
            print(f"  epoch_{epoch}: {rate:.0%}")

    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
