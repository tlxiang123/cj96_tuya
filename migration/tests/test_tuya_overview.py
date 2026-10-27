"""Actual TS protocol, rendered JSX and foreground lifecycle; no cloud/phone claims."""
import os
from pathlib import Path
import shutil
import subprocess

BUNDLE = Path(__file__).resolve().parents[1]
PANEL = BUNDLE / 'panel' if (BUNDLE / 'panel/package.json').is_file() else BUNDLE.parent
DEPENDENCY_PANEL = Path(os.environ.get('CJ96_DEPENDENCY_PANEL', str(PANEL)))
NODE = os.environ.get('CJ96_NODE') or shutil.which('node') or 'node'

JS = r"""
const fs = require('fs'), path = require('path'), assert = require('assert');
const ts = require(path.join(process.argv[1], 'node_modules/typescript'));
const root = process.argv[2];
function load(name, dependencies = {}) {
  const source = fs.readFileSync(path.join(root, 'src/pages/home', name), 'utf8');
  const js = ts.transpileModule(source, {compilerOptions: {
    target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React,
    esModuleInterop: true
  }}).outputText;
  const exports = {};
  new Function('exports', 'require', js)(exports, name => {
    assert(Object.hasOwn(dependencies, name), name); return dependencies[name];
  });
  return exports;
}
const state = load('overview-state.ts');
const token = '12345678', zero = '0'.repeat(32);
function wire({session = 'A1-B2', sequence = 1, mode = 2, phase = 3, elapsed = 49,
  remaining = 5, group = 24, running = '000080' + '0'.repeat(26), fault = 0} = {}) {
  return ['CJOV1','S',token,1000,session,sequence,1792032000,mode,phase,group,elapsed,
    remaining,1792032100,1792032200,1792032600,1792032300,running,zero,zero,fault].join('|');
}
const sample = process.env.CJ96_OVERVIEW_NATIVE_FRAME || wire();
let now = 100000;
const parsed = state.parseOverview(sample, token, now);
assert(parsed && parsed.mode === 2 && parsed.phase === 3 && parsed.group === 24);
assert.deepStrictEqual(parsed.running, [24]);
assert.strictEqual(parsed.elapsed, 49); assert.strictEqual(parsed.remaining, 5);
if (process.env.CJ96_OVERVIEW_NATIVE_FRAME) {
  assert.deepStrictEqual(parsed.completed, [1]); assert.deepStrictEqual(parsed.waiting, [128]);
}
assert.strictEqual(state.parseOverview(sample, 'AAAAAAAA', now), null);
for (const [index, bad] of [[4,'session'],[5,'-1'],[7,'3'],[8,'7'],[9,'129'],[10,'9999999999'],
  [16,'xyz'],[19,'2']]) {
  const fields = sample.split('|'); fields[index] = bad;
  assert.strictEqual(state.parseOverview(fields.join('|'), token, now), null, String(index));
}
assert.strictEqual(state.parseOverview(sample + '|0', token, now), null);
assert.deepStrictEqual(state.decodeGroups('01'+'0'.repeat(28)+'80'), [1,128]);
assert.strictEqual(state.formatGroups([2,3,4,72]), '2-4,72');
assert.strictEqual(state.formatGroups([]), '--');
assert.strictEqual(state.overviewSeconds(parsed, now + 6000).elapsed, 55);
assert.strictEqual(state.overviewSeconds(parsed, now + 6000).remaining, 0);
assert.strictEqual(parsed.phase, 3, 'countdown zero cannot invent completion');
assert.strictEqual(state.overviewSeconds(parsed, now + 200000).elapsed, 134, 'freeze stale timer');
const messages = [];
const sub = new state.OverviewSubscription(s => messages.push(s), () => now, token);
assert.strictEqual(sub.accept(sample), null);
sub.start(); sub.start(); assert.deepStrictEqual(messages, ['CJOV1|Q|' + token]);
assert(sub.accept(sample)); assert.strictEqual(sub.accept(sample), null, 'duplicate sequence');
assert(sub.accept(wire({sequence:2}))); assert.strictEqual(sub.accept(wire()), null);
assert(sub.accept(wire({session:'A2-B3'})));
assert.strictEqual(sub.accept(wire({sequence:99})), null, 'retired GUI session');
now += 60000; sub.tick(); assert.strictEqual(messages.at(-1), 'CJOV1|K|' + token);
sub.stop(); sub.stop(); assert.strictEqual(messages.at(-1), 'CJOV1|U|' + token);
const before = messages.length; now += 200000; sub.tick(); assert.strictEqual(messages.length, before);
const retry = [];
const old = new state.OverviewSubscription(s => retry.push(s), () => now, token);
old.start();
for (let i = 0; i < 60; i++) { now += 10000; old.tick(); }
assert.strictEqual(retry.filter(s => s.includes('|Q|')).length, 4, 'bounded recovery on old firmware');

// Small hook runner: execute the real effects/cleanup with foreground events.
let cursor = 0, pending = [], slots = [], listeners = {}, intervals = new Set();
const realSetInterval = global.setInterval, realClearInterval = global.clearInterval;
global.setInterval = f => { intervals.add(f); return f; };
global.clearInterval = f => intervals.delete(f);
const react = {
  memo: f => f, Fragment: 'Fragment',
  createElement: (type, props, ...children) => ({type, props: props || {}, children: children.flat()}),
  useState: initial => {
    const i = cursor++; if (!slots[i]) slots[i] = {value: typeof initial === 'function' ? initial() : initial};
    return [slots[i].value, next => slots[i].value = typeof next === 'function' ? next(slots[i].value) : next];
  },
  useRef: initial => { const i = cursor++; return slots[i] ||= {current: initial}; },
  useEffect: (effect, deps) => {
    const i = cursor++, previous = slots[i];
    if (previous && deps.every((value, index) => Object.is(value, previous.deps[index]))) return;
    pending.push(() => { previous?.cleanup?.(); slots[i] = {deps, cleanup: effect()}; });
  }
};
const ray = {View:'View',Text:'Text',
  onAppShow:f => listeners.show=f, onAppHide:f=>listeners.hide=f,
  offAppShow:f=>{if(listeners.show===f)delete listeners.show;},
  offAppHide:f=>{if(listeners.hide===f)delete listeners.hide;}};
const styles = new Proxy({}, {get: (_, name) => name});
const runtime = load('overview-runtime.tsx', {'react':react,'@ray-js/ray':ray,
  './overview-state':state,'./index.module.less':styles});
const sent = [], send = f => sent.push(f);
function hook(enabled = true) {
  cursor = 0; runtime.useOverviewSubscription('board-a', enabled, '', send);
  const jobs = pending; pending = []; jobs.forEach(f => f());
}
hook(); assert.strictEqual(sent.length, 1); assert(sent[0].startsWith('CJOV1|Q|'));
hook(); assert.strictEqual(sent.length, 1, 'ordinary renders must not renew subscription');
listeners.hide(); hook(); assert(sent.at(-1).startsWith('CJOV1|U|')); assert.strictEqual(intervals.size, 0);
listeners.show(); hook(); assert(sent.at(-1).startsWith('CJOV1|Q|'));
hook(false); assert(sent.at(-1).startsWith('CJOV1|U|')); assert.strictEqual(intervals.size, 0);
slots.forEach(slot => slot?.cleanup?.()); slots = []; pending = [];
function text(tree) {
  if (tree == null || typeof tree === 'boolean') return '';
  if (typeof tree !== 'object') return String(tree);
  return tree.children.map(text).join('|');
}
function render(component, props) { cursor = 0; slots = []; pending = []; return text(component(props)); }
const fresh = {...parsed,receivedAt:Date.now()};
assert(render(runtime.OverviewMode, {snapshot:fresh,online:true}).includes('手动'));
assert(render(runtime.OverviewChart, {snapshot:fresh,online:true}).includes('已运行 0分 49秒'));
assert(render(runtime.OverviewChart, {snapshot:{...fresh,mode:1,phase:1},online:true}).includes('准备运行'));
assert(render(runtime.OverviewChart, {snapshot:{...fresh,mode:1,remaining:0},online:true}).includes('等待主机确认下一阶段'));
assert(render(runtime.OverviewChart, {snapshot:{...fresh,receivedAt:0},online:true}).includes('状态待更新'));
assert(render(runtime.OverviewChart, {snapshot:{...fresh,fault:true},online:true}).includes('存在异常'));
global.setInterval = realSetInterval; global.clearInterval = realClearInterval;
console.log('PASS overview: native-compatible frame, malformed/old packets, bounded recovery, local timers, foreground cleanup, actual JSX');
"""


def main():
    subprocess.run([NODE, '-e', JS, str(DEPENDENCY_PANEL), str(PANEL)], check=True)


if __name__ == '__main__':
    main()
