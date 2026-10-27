# Exercise the production sync handler, timeout effect and popup with mocked APIs.
# This is not phone rendering, cloud delivery or hardware validation.
import os
from pathlib import Path
import shutil
import subprocess

BUNDLE = Path(__file__).resolve().parents[1]
PANEL = BUNDLE / 'panel' if (BUNDLE / 'panel/package.json').is_file() else BUNDLE.parent
DEPENDENCY_PANEL = Path(os.environ.get('CJ96_DEPENDENCY_PANEL', str(PANEL)))
NODE = os.environ.get('CJ96_NODE') or shutil.which('node') or 'node'

RUNNER = r"""
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const ts = require(path.join(process.argv[1], 'node_modules/typescript'));
const source = fs.readFileSync(path.join(process.argv[2], 'src/pages/home/index.tsx'), 'utf8');
const ast = ts.createSourceFile('home.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const names = ['DEVICE_SYNC_TIMEOUT_SECONDS', 'DEVICE_SYNC_FRAME', 'syncDeviceList'];
const declarations = {};
let timeout, tip;
function visit(node) {
  if (ts.isVariableDeclaration(node) && names.includes(node.name.getText(ast))) {
    declarations[node.name.getText(ast)] = 'const ' + node.getText(ast) + ';';
  }
  if (ts.isCallExpression(node) && node.expression.getText(ast) === 'useEffect' &&
      node.arguments[0].getText(ast).includes('if (!deviceReportPending) return undefined;')) {
    timeout = node.arguments[0].getText(ast);
  }
  if (ts.isJsxExpression(node) && node.expression && ts.isBinaryExpression(node.expression) &&
      node.expression.left.getText(ast) === 'showW2ActionTip') tip = node.expression.getText(ast);
  ts.forEachChild(node, visit);
}
visit(ast);
names.forEach(name => assert(declarations[name], name));
assert(timeout && tip);
assert(!/DEVICE_DISCOVERY_DISPLAY_SECONDS|syncDisplayDeadlineRef|setSyncRemaining|syncRemaining/.test(source));
const compiled = ts.transpileModule(names.map(name => declarations[name]).join('\n') +
  '\nconst installTimeout = ' + timeout + ';\nconst renderTip = () => (' + tip + ');' +
  '\nglobalThis.api = {syncDeviceList, installTimeout, renderTip};',
  {compilerOptions: {jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020}}).outputText;
function setup() {
  let now = 1000, timer;
  const published = [];
  const s = {
    Date: {now: () => now}, devices: [{address: 1}, {address: 20}],
    syncingDevices: false, sending: false, deviceReportPending: false,
    showW2ActionTip: false, w2TipText: '', manualValveProgress: '', closed: 0, completed: 0,
    View: 'View', Image: 'Image', Text: 'Text', actionTipBackground: 'background', styles: {},
    React: {createElement: (type, props, ...children) => ({type, props: {...props, children: children.flat(Infinity)}})},
    clearDeviceTableVersionFallback: () => {}, clearPendingBoardCommand: () => {},
    setInterval: (fn, ms) => {assert.strictEqual(ms, 1000); timer = fn; return 42;},
    clearInterval: id => {assert.strictEqual(id, 42); timer = null;},
    publishFrame: (...args) => published.push(args),
  };
  for (const [name, value] of Object.entries({syncButtonLockRef: false, pendingAutoAssignRef: false,
    deviceTableReadPendingRef: false, w2AutoAssignSnapshotRef: null, syncBaselineAddressesRef: null,
    syncTransferRef: null, syncGroupCapacitiesRef: null, syncRequestActiveRef: false,
    syncDeadlineRef: 0, pendingDeleteAddressRef: null})) s[name] = {current: value};
  for (const name of ['SyncingDevices', 'DeviceReportPending', 'ShowW2ActionTip', 'W2TipText',
    'W2GroupPreviewEnabled', 'ActivePage', 'TestDeviceTableReady']) {
    const key = name[0].toLowerCase() + name.slice(1);
    s['set' + name] = value => {s[key] = value;};
  }
  s.closeW2ActionTip = () => {s.closed++;};
  s.completeWindow2Opening = () => {s.completed++;};
  vm.createContext(s); vm.runInContext(compiled, s);
  return {s, published, tick: value => {now = value; if (timer) timer();}};
}
function text(node) {
  if (node === null || node === undefined || typeof node === 'boolean') return '';
  if (typeof node !== 'object') return String(node);
  return node.props.children.map(text).join('');
}
const h = setup(), s = h.s;
assert.strictEqual(s.api.renderTip(), false);
s.api.syncDeviceList();
assert.strictEqual(h.published.length, 1);
assert.strictEqual(h.published[0][0], 'AA55F50155AA');
assert.strictEqual(h.published[0][5].kind, 'device_sync');
assert.strictEqual(h.published[0][5].command, 'sync');
assert.strictEqual(s.activePage, 'device');
assert.strictEqual(s.syncingDevices, true);
assert.strictEqual(s.deviceReportPending, true);
assert.strictEqual(s.syncButtonLockRef.current, true);
assert.strictEqual(s.syncDeadlineRef.current, 91000);
const expected = '同步中，请等待\n正在等待主机同步结果';
assert.strictEqual(text(s.api.renderTip()), expected);
s.api.renderTip().props.onClick();
assert.strictEqual(s.closed, 0);
s.api.syncDeviceList();
assert.strictEqual(h.published.length, 1, 'repeated taps must not publish another sync');
const cleanup = s.api.installTimeout();
for (const now of [16000, 61000, 90000]) {
  h.tick(now);
  assert.strictEqual(s.syncingDevices, true, 'display time must not complete a sync');
  assert.strictEqual(text(s.api.renderTip()), expected);
}
h.tick(91000);
assert.strictEqual(s.syncingDevices, false);
assert.strictEqual(s.deviceReportPending, false);
assert.strictEqual(s.syncButtonLockRef.current, false);
assert.strictEqual(text(s.api.renderTip()), '同步超时\n请检查设备连接后重试');
h.tick(92000);
assert.strictEqual(s.completed, 1, 'timeout fires once');
cleanup();
s.w2TipText = '此次共添加\n电磁阀 数量2\n传感器 数量1';
assert.strictEqual(text(s.api.renderTip()), s.w2TipText, 'host result must replace waiting text');
s.api.renderTip().props.onClick();
assert.strictEqual(s.closed, 1);
s.manualValveProgress = '正在开阀门[231]';
assert.strictEqual(text(s.api.renderTip()), s.manualValveProgress);
s.api.renderTip().props.onClick();
assert.strictEqual(s.closed, 1, 'in-flight valve operation cannot dismiss its progress');
s.manualValveProgress = '';
for (const [flag, message] of [['pendingAutoAssignRef', '一键添加超时\n请重新同步'],
  ['deviceTableReadPendingRef', '设备表读取超时\n请重试']]) {
  const other = setup(); other.s.deviceReportPending = true; other.s[flag].current = true;
  const stop = other.s.api.installTimeout(); other.tick(91000);
  assert.strictEqual(other.s.w2TipText, message); stop();
}
console.log('PASS: sync retained, truthful waiting text, duplicate-tap/dismiss locks, result text and 90-second timeouts');
"""

if __name__ == '__main__':
    result = subprocess.run([str(NODE), '-e', RUNNER, str(DEPENDENCY_PANEL), str(PANEL)],
                            capture_output=True, text=True, encoding='utf-8')
    print(result.stdout, end='')
    if result.returncode:
        print(result.stderr, end='')
        raise SystemExit(result.returncode)
