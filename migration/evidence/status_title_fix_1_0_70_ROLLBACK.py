# 回滚脚本（Python 3；本项目禁用 PowerShell/CMD/BAT 按 AGENTS.md）
# 用法：python migration/evidence/status_title_fix_1_0_70_ROLLBACK.py
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
LESS = ROOT / 'src/pages/home/index.module.less'
TSX = ROOT / 'src/pages/home/index.tsx'

less = LESS.read_text(encoding='utf-8')
block = re.search(r'([.]statusTitle \{)([^}]*)(\})', less)
if not block:
    sys.exit('statusTitle rule not found; nothing changed')

body = block.group(2)
if 'white-space: nowrap' not in body:
    print('already rolled back (no nowrap)')
else:
    body = body.replace("""  /* Keep the original visual center: left + width/2 = 44.1%. The old 33.5% box
     was narrower than 4 glyphs at 6vh, so 设备离线 / 等待主机状态 wrapped. */
  left: 9.1%;""", '  left: 27.345845%;')
    body = body.replace('width: 70%;', 'width: 33.512064%;')
    body = body.replace('\n  white-space: nowrap;', '')
    less = less[:block.start(2)] + body + less[block.end(2):]
    LESS.write_text(less, encoding='utf-8')
    print('reverted .statusTitle to left 27.345845% / width 33.512064%')

tsx = TSX.read_text(encoding='utf-8')
if "PANEL_VERSION = '1.0.70'" in tsx:
    TSX.write_text(tsx.replace("PANEL_VERSION = '1.0.70'", "PANEL_VERSION = '1.0.69'"), encoding='utf-8')
    print("reverted PANEL_VERSION to 1.0.69")

print('now run: python dev.py build')
