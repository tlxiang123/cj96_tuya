#!/usr/bin/env python3
# Portable Windows x64 entry point; paths are relative to this file.
from pathlib import Path
import os
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def main():
    args = sys.argv[1:] or ['doctor']
    if args[0] == 'verify-full':
        manifest = json.loads((ROOT / 'portable_checksums.json').read_text(encoding='utf-8'))
        bad = []
        for name, expected in manifest.items():
            path = ROOT / name
            # IDE skips .buildHash when checking whether preview needs a rebuild.
            if name.startswith('installers/') and not path.is_file():
                path = ROOT / '.buildHash' / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                bad.append(name)
        if bad:
            print('Missing or changed snapshot files:', *bad, sep='\n')
            return 1
        print('PASS: full portable snapshot verified:', len(manifest), 'files.')
        print('Normal source edits will change hashes; verify before editing.')
        return 0
    node = ROOT / 'runtime/node/node.exe'
    if not node.is_file():
        raise SystemExit('Missing bundled Node runtime. Copy the entire tuya folder.')
    if '--node' not in args:
        args += ['--node', str(node)]
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    env['PYTHONNOUSERSITE'] = '1'
    env.pop('NODE_PATH', None)
    env.pop('NODE_OPTIONS', None)
    env.pop('CJ96_DEPENDENCY_PANEL', None)
    env['PYTHONPATH'] = str(ROOT / 'runtime/python-test-libs')
    if 'test' in args and sys.version_info[:2] != (3, 14):
        print('Bundled test libraries require CPython 3.14 x64; use the included installer.', file=sys.stderr)
        return 1
    return subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'migration/dev.py'), *args],
                          cwd=ROOT, env=env).returncode

if __name__ == '__main__':
    sys.exit(main())
