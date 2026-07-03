# Copyright (c) 2022-2026, The Isaac Lab Project Developers.
# SPDX-License-Identifier: BSD-3-Clause
#
# Derived from Isaac Lab scripts/imitation_learning/robomimic/play.py.
"""sim 層：跑分類策略的 rollout，把每筆結果寫成 JSONL（符合 contracts/job_result.schema.json）。

⚠️ 這支跑在 env_isaacsim（吃 GPU），**不進 CI**。編排層用 subprocess 呼叫：
    cd ~/IsaacLab
    ./isaaclab.sh -p /path/to/sim/run_job.py \
        --task Isaac-Sort-Cube-Franka-IK-Rel-v0 \
        --checkpoint .../model_epoch_200.pth \
        --num_rollouts 10 --seed 100 --horizon 1800 --headless \
        --out /path/to/data/results.jsonl

啟動 Isaac Sim 一次、跑 N 個 rollout（攤掉啟動成本）；每個 rollout 輸出一行 JSON。
"""

import argparse

from isaaclab.app import AppLauncher

# --- CLI ---
parser = argparse.ArgumentParser(description="Run sort-task rollouts and emit structured JSONL results.")
parser.add_argument("--disable_fabric", action="store_true", default=False)
parser.add_argument("--task", type=str, default="Isaac-Sort-Cube-Franka-IK-Rel-v0")
parser.add_argument("--checkpoint", type=str, required=True, help="robomimic .pth checkpoint")
parser.add_argument("--horizon", type=int, default=1800, help="步數上限；分類軌跡長,別低於 1800")
parser.add_argument("--num_rollouts", type=int, default=10)
parser.add_argument("--seed", type=int, default=100, help="base seed；每個 rollout 用 seed+trial")
parser.add_argument("--out", type=str, required=True, help="輸出 JSONL 路徑")
parser.add_argument("--model-tag", type=str, default=None, help="模型標籤;預設從 checkpoint 檔名推(epoch_200)")
parser.add_argument("--norm_factor_min", type=float, default=None)
parser.add_argument("--norm_factor_max", type=float, default=None)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

# launch omniverse app
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

"""Rest everything follows."""

import copy
import json
import os
import random

import gymnasium as gym
import numpy as np
import robomimic.utils.file_utils as FileUtils
import robomimic.utils.torch_utils as TorchUtils
import torch

from isaaclab_tasks.utils import parse_env_cfg

# 子任務固定順序（藍→紅→綠）。failure_stage 依這順序找第一個未達成的階段。
SUBTASK_ORDER = ["grasp_1", "place_1", "grasp_2", "place_2", "grasp_3", "place_3"]
# 顏色 -> (場景中 cube 名稱, 對應平台容器)
CUBE_MAP = {
    "blue": ("cube_1", "container_blue"),
    "red": ("cube_2", "container_red"),
    "green": ("cube_3", "container_green"),
}
# placed_correctly 的物理門檻(與 cubes_sorted 一致,但刻意不看夾爪)
PLACE_XY_THRESHOLD = 0.06
PLACE_H_THRESHOLD = 0.06


def _scalar(t) -> bool:
    """把 [num_envs, ...] 的訊號 tensor 取第 0 個環境、轉 bool。"""
    return bool(t.reshape(-1)[0].item())


def rollout(policy, env, success_term, horizon, device) -> tuple[bool, int, str | None]:
    """跑一個 rollout。回傳 (success, cycle_time_steps, failure_stage)。"""
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

        # 累積子任務訊號（環境每步已算好，放在 subtask_terms group）
        if "subtask_terms" not in obs_dict:
            raise KeyError("obs_dict 沒有 'subtask_terms' group；確認用的是 sort 任務且該 obs group 未被停用")
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
    """讀每顆方塊的最終物理狀態:是否在對應平台上(不看夾爪) + 座標(env 相對)。

    placed_correctly 只看物理落點(xy + 高度),刻意不含夾爪張開條件,以便乾淨診斷。
    嚴格的「三顆同時放好且釋放」由 success (cubes_sorted) 判定。
    """
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


def main():
    # 沿用 play.py 的環境設定
    env_cfg = parse_env_cfg(args_cli.task, device=args_cli.device, num_envs=1, use_fabric=not args_cli.disable_fabric)
    env_cfg.observations.policy.concatenate_terms = False
    env_cfg.terminations.time_out = None
    env_cfg.recorders = None

    # 取出 success 判定,並從 termination 移除(改由我們手動檢查)
    success_term = env_cfg.terminations.success
    env_cfg.terminations.success = None

    env = gym.make(args_cli.task, cfg=env_cfg).unwrapped
    device = TorchUtils.get_torch_device(try_to_use_cuda=True)
    policy, _ = FileUtils.policy_from_checkpoint(ckpt_path=args_cli.checkpoint, device=device)

    # 模型標籤：優先用 --model-tag，否則從 checkpoint 檔名推（model_epoch_200 → epoch_200）
    model_tag = args_cli.model_tag or os.path.splitext(os.path.basename(args_cli.checkpoint))[0].replace("model_", "")

    results = []
    with open(args_cli.out, "w", encoding="utf-8") as f:
        for trial in range(args_cli.num_rollouts):
            seed = args_cli.seed + trial
            torch.manual_seed(seed)
            np.random.seed(seed)
            random.seed(seed)
            env.seed(seed)

            success, steps, failure_stage = rollout(policy, env, success_term, args_cli.horizon, device)
            # rollout 結束後,環境停在最終狀態,直接讀每顆方塊物理落點
            per_cube = collect_per_cube(env)

            result = {
                "model_tag": model_tag,
                "seed": seed,
                "success": success,
                "cycle_time_steps": steps,
                "failure_stage": failure_stage,
                "per_cube": per_cube,
            }
            results.append(success)
            f.write(json.dumps(result) + "\n")
            f.flush()
            print(f"[INFO] trial {trial} seed={seed}: success={success} steps={steps} fail={failure_stage}")

    n = len(results)
    print(f"\nSuccess rate: {sum(results)}/{n} = {sum(results) / n if n else 0:.2f}")
    print(f"Results written to: {args_cli.out}")
    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
