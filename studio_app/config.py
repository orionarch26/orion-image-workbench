import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = tomllib.loads((ROOT / 'studio.toml').read_text())
SERVER = CONFIG['server']
GENERATION = CONFIG['generation']
MODELS = CONFIG['models']
BACKEND = f"http://127.0.0.1:{SERVER['backend_port']}"
OUTPUT = Path(os.environ.get('STUDIO_OUTPUT_DIR', ROOT / 'output')).resolve()
STATE = Path(os.environ.get('STUDIO_STATE_DIR', ROOT / 'state')).resolve()
EXAMPLES = {
    'photo': '一只橘猫坐在窗边的木桌上，旁边放着白色陶瓷咖啡杯，清晨柔和阳光，背景是虚化的绿色植物，真实摄影，自然毛发细节，无文字。',
    'poster': '极简咖啡海报，奶油色背景，中央一杯拿铁，柔和侧光。顶部用清晰的中文大字写着“慢慢喝”，底部小字写着“享受此刻”，留白充足，整洁排版。',
    'sticker': 'A cute orange cat astronaut sticker, full body, clean bold outline, centered, no text.',
    'edit': '保留图片中猫的外貌、姿势和构图，把背景改成夜晚的宇宙空间站，窗外可以看到地球，不添加文字。',
}
