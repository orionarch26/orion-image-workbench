"""Command entry point; runtime is split into studio_app modules."""
import sys
from studio_app.config import ROOT, OUTPUT, BACKEND, MODELS, EXAMPLES
from studio_app.workflow import build_workflow
from studio_app.backend import request, ready, ensure_backend
from studio_app.cli import main, run_workflow

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('界面已关闭。后端任务保留；再次启动可继续跟踪。')
    except Exception as exc:
        print('错误：'+str(exc),file=sys.stderr)
        sys.exit(1)
