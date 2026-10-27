"""Check the actual Window4 JSX and handlers with mocked rendering/board APIs.

Native Android touch scrolling and physical device actions still need phone testing.
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
const css = fs.readFileSync(path.join(process.argv[2], 'src/pages/home/index.module.less'), 'utf8');
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
const declarations = ['WINDOW4_DEVICE_STATE_COMMAND', 'WINDOW4_GROUP_STATE_COMMAND',
  'makeWindow4StateFrame', 'describeManualValveCommand', 'formatBoardCommandError', 'formatPanelGroupName', 'window4OutputDevices',
  'window4SensorDevices', 'window4GroupNumbers', 'toggleWindow4Device',
  'toggleWindow4Group', 'openWindow4', 'renderTestPage'].map(declaration).join('\n');
const compiled = ts.transpileModule(declarations, {compilerOptions: {
  target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React
}}).outputText;
function all(node) {
  return node && typeof node === 'object' ? [node, ...node.props.children.flatMap(all)] : [];
}
function find(tree, cls) {
  return all(tree).filter(node => (node.props.className || '').split(' ').includes(cls));
}
function text(node) {
  return node == null ? '' : typeof node === 'object' ? node.props.children.map(text).join('') : String(node);
}
for (const count of [0, 1, 8, 212, 216]) {
  const items = Array.from({length:count}, (_, index) => ({
    address:20 + index, name:(index ? '电磁阀' : '水泵') + (20 + index),
    type:index ? '电磁阀' : '水泵', state:false
  }));
  const context = vm.createContext({
    React:{createElement:(type, props, ...children) => ({type, props:{...props, children:children.flat(Infinity)}})},
    View:'View', Text:'Text', Image:'Image', ScrollView:'ScrollView',
    styles:new Proxy({}, {get:(_, key) => key}),
    window4Region1:'device-bg', window4Region2:'group-bg', window4Region3:'sensor-bg',
    window3CycleToggleOnIcon:'on', window3CycleToggleOffIcon:'off',
    devices:[...items, {address:3, name:'雨量传感器', type:'传感器', status:'0'}],
    w2GroupNumbers:Array.from({length:72}, (_, index) => index + 1),
    w2GroupNames:{72:'东区'}, groupTestStates:Array(72).fill(false), sending:false,
    testDeviceTableReady:true, deviceReportPending:false, syncRequestActiveRef:{current:false},
    requestCurrentDeviceTable:() => {context.tableReads = (context.tableReads || 0) + 1;},
    setTestDeviceTableReady:value => {context.testDeviceTableReady = value;},
    setActivePage:value => {context.activePage = value;},
    roundMinutes:'1', roundSeconds:'0', setRoundMinutes:() => {}, setRoundSeconds:() => {},
    renderRoundNumberBox:() => null, irrigating:false, setShowRoundConfirm:() => {},
    publishFrame:(...args) => {context.pending = args;},
  });
  context.setDevices = update => {context.devices = update(context.devices);};
  context.setGroupTestStates = update => {context.groupTestStates = update(context.groupTestStates);};
  vm.runInContext(compiled, context);
  const tree = vm.runInContext('renderTestPage()', context);
  const columns = find(tree, 'testColumn');
  assert.strictEqual(columns.length, 3);
  const list = find(columns[0], 'deviceTestList')[0];
  assert(list, 'device rows must be inside their own native scroll container');
  assert.strictEqual(list.type, 'ScrollView');
  assert.strictEqual(list.props.scrollY, true);
  assert.strictEqual(list.props.enhanced, true);
  assert.strictEqual(find(list, 'testHeader').length, 0, 'header stays fixed outside scroll content');
  assert.strictEqual(find(columns[0], 'testHeader').length, 1);
  const rows = find(list, 'testRow');
  assert.strictEqual(rows.length, count);
  assert.strictEqual(find(columns[0], 'testRow').length, count, 'no stray clipped rows outside list');
  assert.strictEqual(find(list, 'sensorDataRow').length, 0);
  const groups = find(columns[1], 'groupTestList')[0];
  assert.strictEqual(groups.type, 'ScrollView');
  assert.strictEqual(groups.props.scrollY, true);
  assert.strictEqual(find(groups, 'testRow').length, 72);
  assert.strictEqual(text(find(groups, 'testRow')[71]), '72东区');
  assert.strictEqual(find(groups, 'roundControls').length, 0, 'round controls remain outside scrolling');
  assert.strictEqual(find(columns[1], 'roundControls').length, 1);
  if (count) {
    const last = rows[count - 1], button = find(last, 'testToggle')[0];
    const address = 20 + count - 1;
    assert.strictEqual(last.props.key, `device-test-${address}`);
    assert(text(last).includes(String(address)));
    context.sending = true;
    button.props.onClick();
    assert.strictEqual(context.pending, undefined, 'busy guard is preserved');
    context.sending = false;
    for (const lock of ['testDeviceTableReady', 'deviceReportPending', 'syncRequestActiveRef']) {
      if (lock === 'syncRequestActiveRef') context.syncRequestActiveRef.current = true;
      else context[lock] = lock !== 'testDeviceTableReady';
      button.props.onClick();
      assert.strictEqual(context.pending, undefined, `block device command while ${lock}`);
      context.testDeviceTableReady = true;
      context.deviceReportPending = false;
      context.syncRequestActiveRef.current = false;
    }
    button.props.onClick();
    assert.strictEqual(context.pending[0], `AA55E4${address.toString(16).padStart(2,'0').toUpperCase()}0155AA`);
    assert.strictEqual(context.pending[5].command, `device_state=${address},1`);
    assert.strictEqual(context.devices[count - 1].state, false, 'no state change before board ACK');
    context.pending[2]();
    assert.strictEqual(context.devices[count - 1].state, true);
    assert.strictEqual(context.devices[count - 1].status, '打开');
    assert(context.devices.slice(0, count - 1).every(item => !item.state));
  }
  const groupButton = find(find(groups, 'testRow')[71], 'testToggle')[0];
  groupButton.props.onClick();
  assert.strictEqual(context.pending[0], 'AA55E5480155AA');
  assert.strictEqual(context.pending[5].command, 'group_state=72,1');
  assert.strictEqual(context.groupTestStates[71], false);
  context.pending[2]();
  assert.strictEqual(context.groupTestStates[71], true);
  context.pending = undefined;
  vm.runInContext('openWindow4()', context);
  assert.strictEqual(context.activePage, 'test');
  assert.strictEqual(context.tableReads, 1, 'entering tests requests the current host table');
  assert.strictEqual(context.testDeviceTableReady, false);
  groupButton.props.onClick();
  assert.strictEqual(context.pending, undefined, 'block group commands before table verification');
  assert.strictEqual(find(vm.runInContext('renderTestPage()', context), 'testVerificationOverlay').length, 1);
  for (const [code, phrase] of [[4002,'稍后'],[4003,'设备类型'],[4004,'同步设备表'],[4005,'加入队列']]) {
    const message = vm.runInContext(`formatBoardCommandError('home', 'device_state=231,1', ${code})`, context);
    assert(message.includes('231') && message.includes(phrase), message);
  }
  assert.strictEqual(vm.runInContext("formatBoardCommandError('home', 'group_state=72,1', 4004)", context),
    '板端操作失败\n错误码 4004', 'valve errors must not mislabel other commands');
}
function rules(selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const block = css.match(new RegExp(escaped + '\\s*\\{([^}]*)\\}'));
  assert(block, selector);
  const body = block[1].replace(/\/\*[\s\S]*?\*\//g, '');
  return Object.fromEntries([...body.matchAll(/([a-z-]+):\s*([^;]+);/g)].map(m => [m[1],m[2]]));
}
const listRules = rules('.deviceTestList');
assert.strictEqual(listRules.position, 'absolute');
assert.strictEqual(listRules['overflow-y'], 'scroll');
assert.strictEqual(listRules['touch-action'], 'pan-y');
assert.strictEqual(listRules.top, rules('.groupTestList').top, 'lists begin below their headers');
assert(parseFloat(listRules.top) + parseFloat(listRules.height) <= 100, 'viewport stays in column');
assert.strictEqual(listRules['z-index'], '2', 'list stays above background image');
const rowRules = rules('.deviceTestList .testRow');
assert(rowRules.height.startsWith('min(') && !rowRules.height.includes('%'), 'rows must not collapse with native auto-sized content');
assert.strictEqual(rowRules['min-height'], rowRules.height);
assert.strictEqual(rowRules.height, rules('.testToggle').height, 'the last switch must fit entirely within the scroll content');
console.log('PASS: Window4 0/1/8/212/216 device lists, address 231 wire frame and ACK update, table verification locks and specific errors. Not phone touch/hardware validation.');
"""


if __name__ == '__main__':
    subprocess.run([NODE, '-e', JS, str(DEPENDENCY_PANEL), str(PANEL)], check=True)
