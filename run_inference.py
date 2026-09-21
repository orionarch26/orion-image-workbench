#!/usr/bin/env python3
"""Compatibility entry point for an API-format ComfyUI workflow."""
import argparse
import json
import sys
from pathlib import Path
from studio import OUTPUT, ROOT, run_workflow


def main():
    parser = argparse.ArgumentParser(description="提交 ComfyUI API 工作流，需先启动 ./start.sh")
    parser.add_argument("workflow", type=Path, nargs="?", default=ROOT / "workflow_qwen21_t2i.json")
    parser.add_argument("output", type=Path, nargs="?", default=OUTPUT)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--resume", action="store_true", help="只恢复记录中的后端任务，不重新生成")
    args = parser.parse_args()
    saved = json.loads(args.workflow.read_text())
    workflow = saved.get("workflow", saved)
    if args.resume and "prompt_id" not in saved:
        parser.error("--resume 需要带 prompt_id 的参数记录")
    result = run_workflow(workflow, args.output, args.timeout,
                          progress=lambda pid: print("任务 ID：" + pid, flush=True),
                          record=saved if args.resume else None)
    print(f"完成，耗时 {result['seconds']} 秒")
    for name in result["files"]:
        print(args.output / name)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
