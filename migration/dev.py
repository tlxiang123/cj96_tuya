#!/usr/bin/env python3
# Python 3 portable developer launcher. No shell scripts or machine-fixed paths.
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PANEL = ROOT / 'panel' if (ROOT / 'panel/package.json').is_file() else ROOT.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(args, cwd=PANEL, env=None):
    print('RUN:', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), cwd=cwd, env=env, check=True)


def verify():
    manifest = json.loads((ROOT / 'checksums.json').read_text(encoding='utf-8'))
    bad = []
    for name, expected in manifest.items():
        path = PANEL / name[6:] if name.startswith('panel/') else ROOT / name
        if not path.is_file() or digest(path) != expected:
            bad.append(name)
    if bad:
        print('Changed or missing files:')
        print('\n'.join(bad))
        return 1
    print('PASS: all', len(manifest), 'snapshot files match SHA256.')
    print('Additional files are not checked; normal edits will change snapshot hashes.')
    return 0


def main():
    parser = argparse.ArgumentParser(description='CJ96 APP migration/development helper')
    parser.add_argument('action', choices=['verify', 'doctor', 'install', 'build', 'start', 'test'])
    parser.add_argument('--node', help='Full path to node executable if not on PATH')
    parser.add_argument('--npm-cli', help='Full path to npm-cli.js when discovery fails')
    parser.add_argument('--yarn-js', help='Full path to Yarn Classic 1.22.22 yarn.js')
    parser.add_argument('--dependency-panel', help='TEST ONLY: borrow existing node_modules from this panel')
    args = parser.parse_args()
    if args.action == 'verify':
        return verify()
    found = args.node or shutil.which('node')
    if not found:
        raise RuntimeError('Node.js not found. Install Node.js or pass --node.')
    node = Path(found).resolve()
    env = os.environ.copy()
    env['PATH'] = str(node.parent) + os.pathsep + env.get('PATH', '')
    env['PYTHONUTF8'] = '1'
    npm_candidates = [node.parent / 'node_modules/npm/bin/npm-cli.js',
                      node.parent.parent / 'lib/node_modules/npm/bin/npm-cli.js']
    npm = Path(args.npm_cli) if args.npm_cli else next((p for p in npm_candidates if p.is_file()), None)
    yarn_candidates = [ROOT / '.tools/yarn/node_modules/yarn/bin/yarn.js',
                       node.parent / 'node_modules/yarn/bin/yarn.js',
                       node.parent.parent / 'lib/node_modules/yarn/bin/yarn.js']
    if os.environ.get('APPDATA'):
        yarn_candidates.append(Path(os.environ['APPDATA']) / 'npm/node_modules/yarn/bin/yarn.js')
    yarn = Path(args.yarn_js) if args.yarn_js else next((p for p in yarn_candidates if p.is_file()), None)
    if args.action == 'doctor':
        print('Bundle:', ROOT)
        print('Python:', sys.version)
        print('Node:', node)
        execute([node, '--version'], env=env)
        print('npm CLI:', npm)
        if npm:
            execute([node, npm, '--version'], env=env)
        print('Yarn CLI:', yarn)
        if yarn:
            execute([node, yarn, '--version'], env=env)
        print('Dependencies installed:', (PANEL / 'node_modules').is_dir())
        print('Build output exists:', (PANEL / 'dist/tuya').is_dir())
        print('This checks local tools only, not Tuya login, permissions or phone connectivity.')
        return 0
    if args.action == 'test':
        env['CJ96_NODE'] = str(node)
        if args.dependency_panel:
            env['CJ96_DEPENDENCY_PANEL'] = str(Path(args.dependency_panel).resolve())
            print('TEST ONLY: using external dependencies:', env['CJ96_DEPENDENCY_PANEL'])
        else:
            env.pop('CJ96_DEPENDENCY_PANEL', None)
        tests = sorted((ROOT / 'tests').glob('test_tuya_*.py'))
        for path in tests:
            execute([sys.executable, '-X', 'utf8', path], cwd=ROOT, env=env)
        print(f'PASS: {len(tests)} regression scripts. Does NOT certify phone rendering or cloud/board delivery.')
        return 0
    if args.action == 'install':
        if not yarn:
            if not npm:
                raise RuntimeError('npm CLI not found; pass --npm-cli or --yarn-js.')
            execute([node, npm, 'install', '--prefix', ROOT / '.tools/yarn',
                     '--no-audit', '--no-fund', '--ignore-scripts', 'yarn@1.22.22'], cwd=ROOT, env=env)
            yarn = ROOT / '.tools/yarn/node_modules/yarn/bin/yarn.js'
        version = subprocess.check_output([str(node), str(yarn), '--version'], env=env, text=True).strip()
        if version != '1.22.22':
            raise RuntimeError('Expected Yarn 1.22.22, found ' + version + '. Pass --yarn-js.')
        lock = PANEL / 'yarn.lock'
        before = digest(lock)
        execute([node, yarn, 'install', '--frozen-lockfile', '--non-interactive'], env=env)
        if before != digest(lock):
            raise RuntimeError('Lockfile changed unexpectedly. Inspect before continuing.')
        return 0
    if not npm:
        raise RuntimeError('npm CLI not found; pass --npm-cli.')
    if not (PANEL / 'node_modules').is_dir():
        raise RuntimeError('Missing dependencies. Run python dev.py install first.')
    execute([node, npm, 'run', args.action], env=env)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print('ERROR:', error, file=sys.stderr)
        sys.exit(1)
