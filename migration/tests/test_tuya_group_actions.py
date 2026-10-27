"""Execute the APP's group handlers/rename JSX with mocked board and storage APIs.

This checks APP behavior around a confirmed command, not a phone/board round trip.
"""
import os
from pathlib import Path
import shutil
import subprocess

BUNDLE = Path(__file__).resolve().parents[1]
PANEL = BUNDLE / 'panel' if (BUNDLE / 'panel/package.json').is_file() else BUNDLE.parent
DEPENDENCY_PANEL = Path(os.environ.get('CJ96_DEPENDENCY_PANEL', str(PANEL)))
NODE = os.environ.get('CJ96_NODE') or shutil.which('node') or 'node'

JS = r"""
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const ts = require(path.join(process.argv[1], 'node_modules/typescript'));
const source = fs.readFileSync(path.join(process.argv[2], 'src/pages/home/index.tsx'), 'utf8');
const ast = ts.createSourceFile('home.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
function declaration(name) {
  let found;
  function visit(node) {
    if (ts.isFunctionDeclaration(node) && node.name?.text === name) found = node.getText(ast);
    if (ts.isVariableDeclaration(node) && node.name.getText(ast) === name) found = 'const ' + node.getText(ast) + ';';
    ts.forEachChild(node, visit);
  }
  visit(ast); assert(found, name); return found;
}
const names = ['clamp', 'extractGroupNumbers', 'removeGroupNumber', 'encodeUtf8Hex',
  'truncateUtf8Text', 'makeW2GroupRenameCommand', 'makeW2GroupScopeCommand',
  'formatPanelGroupName', 'formatPanelGroupSummary', 'readPanelGroupNames', 'writePanelGroupNames',
  'confirmW2Clear', 'confirmW2Rename', 'closeW2TransientDialogs', 'openW2GroupChoice',
  'openW2Rename', 'confirmW2GroupChoiceCurrent', 'isGroupBindableSensor',
  'toggleGroupSelection', 'confirmW2GroupBind', 'makeW2GroupBindCommand',
  'bindPanelDeviceGroup', 'openW2GroupBindEditor'];
const storage = new Map();
const context = vm.createContext({
  DEFAULT_DEVICE_COUNT: 6, deviceId: 'controller-a', w2SelectedGroupNo: 1,
  w2GroupChoiceNo: 1, w2GroupChoiceMode: 'rename', w2GroupName: '阀组[1]',
  w2GroupNames: {}, w2GroupNumbers: [1,2,3,4,72], w2GroupListRevision: 0,
  devices: [], w2GroupPreviewEnabled: true, w2GroupBindAllGroups: true,
  w2SelectedPumpIndexes: [0], w2SelectedSensorIndexes: [2],
  w2AutoAssignSnapshotRef: {current: []}, showW2Rename: true, showW2Editor: false,
  getStorageSync: ({key}) => ({data: storage.get(key)}),
  setStorageSync: ({key, data}) => storage.set(key, data),
  publishFrame: (...args) => { context.pending = args; },
});
for (const key of ['devices','w2SelectedGroupNo','w2GroupChoiceNo','w2GroupChoiceMode','w2GroupName',
  'w2GroupNames','w2GroupNumbers','w2GroupListRevision','w2GroupPreviewEnabled','w2GroupBindAllGroups',
  'w2SelectedPumpIndexes','w2SelectedSensorIndexes','showW2Rename','showW2Editor','showW2GroupChoice',
  'showW2GroupBind','showW2GroupBindScope','showW2Capacity','showW2DeviceRename','showW2ClearTip','showW2ActionTip']) {
  context['set' + key[0].toUpperCase() + key.slice(1)] = value => {
    context[key] = typeof value === 'function' ? value(context[key]) : value;
  };
}
function run(code) {
  return vm.runInContext(ts.transpileModule(code, {compilerOptions: {
    target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React
  }}).outputText, context);
}
run(names.map(declaration).join('\n'));
const plain = value => JSON.parse(JSON.stringify(value));
const sample = () => [
  {address:20,type:'电磁阀',name:'电磁阀20',group:'1'},
  {address:21,type:'电磁阀',name:'电磁阀21',group:'2'},
  {address:8,type:'传感器',name:'雨量传感器',group:'1,2'},
  {address:6,type:'传感器',name:'湿度传感器',group:'*'},
  {address:1,type:'水泵',name:'水泵1',group:'所有阀组'},
];
context.devices = sample();
run('confirmW2Clear(1, false)');
assert.deepStrictEqual(context.devices, sample(), 'no local mutation before board success');
context.pending[4]();
assert.deepStrictEqual(context.devices, sample(), 'failure preserves memberships');
assert.strictEqual(context.w2GroupPreviewEnabled, true);
assert.strictEqual(context.w2GroupListRevision, 0);
run('confirmW2Clear(1, false)');
assert.strictEqual(context.pending[0], 'AA55FB0155AA');
assert.strictEqual(context.pending[5].command, 'group_clear=1');
assert.strictEqual(context.pending[5].usesDeviceTableRevision, true);
context.pending[2]();
assert.strictEqual(context.devices[0].group, '-');
assert.strictEqual(context.devices[1].group, '2');
assert.strictEqual(context.devices[2].group, '2');
for (const index of [3,4]) {
  const remaining = context.devices[index].group.split(',').map(Number);
  assert.strictEqual(remaining.length, 127);
  assert(!remaining.includes(1)); assert(remaining.includes(2)); assert(remaining.includes(128));
}
assert.strictEqual(run('formatPanelGroupSummary(1, devices, null, w2GroupPreviewEnabled, 0, 20)'), '[空]');
assert.strictEqual(context.w2GroupPreviewEnabled, false);
assert.deepStrictEqual(plain(context.w2SelectedSensorIndexes), []);
assert.deepStrictEqual(plain(context.w2SelectedPumpIndexes), []);
assert.strictEqual(context.w2AutoAssignSnapshotRef.current, null);
assert(context.w2GroupNumbers.includes(72), 'single clear preserves other visible groups');
assert.strictEqual(context.w2GroupListRevision, 1);
context.devices = sample(); context.w2SelectedGroupNo = 72;
run('confirmW2Clear(72, true)'); context.pending[2]();
assert.strictEqual(context.pending[0], 'AA55FBFF55AA');
assert.strictEqual(context.pending[5].command, 'group_clear=255');
assert(context.devices.every(item => item.group === '-'));
assert.deepStrictEqual(plain(context.w2GroupNumbers), [1,2,3,4]);
assert.strictEqual(context.w2SelectedGroupNo, 1);
for (const group of context.w2GroupNumbers) {
  assert.strictEqual(run(`formatPanelGroupSummary(${group}, devices, null, w2GroupPreviewEnabled, 0, 20)`), '[空]');
}

// Render and operate the actual rename input/confirm/cancel JSX.
context.React = {createElement: (type, props, ...children) => ({type, props: {...props, children: children.flat(Infinity)}})};
for (const name of ['View','Text','Image','Input']) context[name] = name;
context.styles = new Proxy({}, {get: (_, key) => key});
for (const name of ['tipDialogBackground','w2GroupRenameEdit','w2PlainButtonBackground']) context[name] = name;
const start = source.indexOf('        {showW2Rename && (');
const end = source.indexOf('        {showW2ActionTip && (', start);
const section = source.slice(start, end);
const jsx = section.slice(section.indexOf('<View'), section.lastIndexOf('</View>') + 7);
run('const renderRename = () => (' + jsx + ');');
function all(node) {return node && typeof node === 'object' ? [node, ...node.props.children.flatMap(all)] : [];}
function find(tree, cls) {return all(tree).find(node => node.props.className === cls);}

// Main-valve meters remain in the device table but cannot be bound to groups,
// including renamed meters and stale selections from the previous UI.
context.devices = [...sample(),
  {address:9,type:'传感器',name:'主阀压力',group:'-'},
  {address:10,type:'传感器',name:'总流量',group:'-'}];
context.w2SelectedSensorIndexes = [2,3,5,6,999];
context.w2SelectedPumpIndexes = [4];
run('openW2GroupBindEditor(false, 3)');
assert.deepStrictEqual(plain(context.w2SelectedSensorIndexes), [2,3]);
run('toggleGroupSelection(5, false); toggleGroupSelection(6, false)');
assert.deepStrictEqual(plain(context.w2SelectedSensorIndexes), [2,3]);
context.w2SelectedSensorIndexes = [2,3,5,6];
const beforeBind = plain(context.devices);
run('confirmW2GroupBind()');
assert.strictEqual(context.pending[0], 'AA55FA030301080655AA');
assert.strictEqual(context.pending[5].command, 'group_bind=3,1,8,6');
assert.deepStrictEqual(plain(context.devices), beforeBind, 'binding waits for ACK');
context.pending[2]();
assert.strictEqual(context.devices[5].group, '-');
assert.strictEqual(context.devices[6].group, '-');
assert(context.devices[2].group.split(',').includes('3'));
assert(context.devices[4].group.split(',').includes('3'));
run('openW2GroupBindEditor(true, 3)');
run('confirmW2GroupBind()');
assert.strictEqual(context.pending[0], 'AA55FAFF0301080655AA');
context.selectOnImage = 'selected'; context.selectOffImage = 'unselected';
const sensorStart = source.indexOf('<View className={styles.w2GroupBindSensorGrid}>');
const sensorSection = source.slice(sensorStart, source.indexOf('</ScrollView>', sensorStart));
run('const renderBindSensors = () => (' + sensorSection.trim() + ');');
const sensorTree = run('renderBindSensors()');
const sensorLabels = all(sensorTree).filter(node => node.type === 'Text').map(node => node.props.children[0]);
assert.deepStrictEqual(sensorLabels, ['雨量传感器', '湿度传感器']);
context.w2SelectedGroupNo = 1;

context.w2GroupNames = {1:'西区'};
run('openW2Rename(); confirmW2GroupChoiceCurrent()');
assert.strictEqual(context.w2GroupName, '西区', 'reopening shows saved name');
let tree = run('renderRename()');
const input = find(tree, 'w2RenameInput');
assert.strictEqual(input.type, 'Input'); assert.strictEqual(input.props.maxLength, 32);
input.props.onInput({detail:{value:'东区'}});
find(tree, 'w2TipCancel').props.onClick();
assert.strictEqual(context.w2GroupNames[1], '西区', 'cancel never saves');
run('openW2Rename(); confirmW2GroupChoiceCurrent()');
tree = run('renderRename()');
find(tree, 'w2RenameInput').props.onInput({detail:{value:'  灌溉区域名称🌧'.repeat(5)}});
const draft = context.w2GroupName;
find(tree, 'w2TipOk').props.onClick();
assert.strictEqual(context.w2GroupNames[1], '西区', 'wait for board ACK before rename');
context.pending[4]();
assert.strictEqual(context.w2GroupNames[1], '西区', 'failed rename does not save');
const wire = context.pending[0];
const byteCount = parseInt(wire.slice(8,10),16);
const wireBytes = Buffer.from(wire.slice(10,-4), 'hex');
const wireName = wireBytes.toString('utf8');
assert.strictEqual(byteCount, wireBytes.length); assert(byteCount <= 32);
assert(!wireName.includes('\ufffd'), 'UTF-8 code points cannot be split');
assert.strictEqual(context.pending[5].command, 'group_rename=1,' + wireName);
assert(draft.trim().startsWith(wireName));
context.pending[2]();
assert.strictEqual(context.w2GroupNames[1], wireName);
assert.strictEqual(context.w2GroupName, wireName);
assert.strictEqual(run('formatPanelGroupName(1, w2GroupNames)'), wireName);
assert.strictEqual(run('readPanelGroupNames(deviceId)[1]'), wireName, 'saved name survives reload');
assert.deepStrictEqual(plain(run("readPanelGroupNames('controller-b')")), {}, 'controllers have separate names');
storage.set('cj96:group-names:controller-a', '{corrupt');
assert.deepStrictEqual(plain(run('readPanelGroupNames(deviceId)')), {});
const css = fs.readFileSync(path.join(process.argv[2], 'src/pages/home/index.module.less'), 'utf8');
assert(!/\.w2RenameInput\s*\{[^}]*color:\s*transparent/.test(css), 'rename text must be visible');
assert(/\.w2RenameInputBg\s*\{[^}]*pointer-events:\s*none/.test(css), 'background must not intercept input');
console.log('PASS: APP handlers with mocked ACK/storage: sensor clearing, shared/all memberships, four empty groups, preview/scroll reset, rename input/cancel/save/reload, UTF-8 frame and ACK consistency');
"""


def main():
    subprocess.run([NODE, '-e', JS, str(DEPENDENCY_PANEL), str(PANEL)], check=True)


if __name__ == '__main__':
    main()
