"""Run actual panel publish/ACK/timeout handlers with mocked Tuya transport; no hardware."""
import os
from pathlib import Path
import shutil
import subprocess

BUNDLE = Path(__file__).resolve().parents[1]
PANEL = BUNDLE / 'panel' if (BUNDLE / 'panel/package.json').is_file() else BUNDLE.parent
DEPENDENCY_PANEL = Path(os.environ.get('CJ96_DEPENDENCY_PANEL', str(PANEL)))
NODE = os.environ.get('CJ96_NODE') or shutil.which('node') or 'node'
RUNNER = r"""
const fs=require('fs'), path=require('path'), vm=require('vm'), assert=require('assert');
const ts=require(path.join(process.argv[1], 'node_modules/typescript'));
const source=fs.readFileSync(path.join(process.argv[2], 'src/pages/home/index.tsx'),'utf8');
const ast=ts.createSourceFile('panel.tsx', source, ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
const names=['describeManualValveCommand','manualValveTimeoutMs','matchesBoardCommandAck',
  'formatBoardCommandError','publishFrame','clearPendingBoardCommand','COMMAND_ACK_PREFIX',
  'COMMAND_ACK_STORAGE_PREFIX','DEVICE_SYNC_PREFIX','CJ96_DP_ID','BOARD_COMMAND_ACK_TIMEOUT_MS',
  'NETWORK_NONE_STATE_FRAME','NETWORK_ETHERNET_STATE_FRAME','NETWORK_WIFI_STATE_FRAME','NETWORK_4G_STATE_FRAME'];
const found={}; let ackEffect,timeoutEffect;
function visit(n) {
  if(ts.isFunctionDeclaration(n) && names.includes(n.name?.text)) found[n.name.text]=n.getText(ast);
  if(ts.isVariableDeclaration(n) && names.includes(n.name.getText(ast))) found[n.name.getText(ast)]='const '+n.getText(ast)+';';
  if(ts.isCallExpression(n) && n.expression.getText(ast)==='useEffect') {
    const text=n.arguments[0].getText(ast);
    if(text.includes('const ackParts = normalizedReportedFrame.split')) ackEffect=text;
    if(text.includes('Date.now() - pending.startedAt < pending.timeoutMs')) timeoutEffect=text;
  }
  ts.forEachChild(n,visit);
}
visit(ast); for(const n of names)assert(found[n],n); assert(ackEffect && timeoutEffect);
const code=ts.transpileModule(names.map(n=>found[n]).join('\n')+'\nconst receive='+ackEffect+
  '; const installTimeout='+timeoutEffect+'; globalThis.api={publishFrame,receive,installTimeout,manualValveTimeoutMs};',
  {compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText;
function setup() {
 let now=1000,timer;
 const s={deviceId:'test-device',deviceOnline:true,devices:[{type:'电磁阀',group:'1',address:231}],
  normalizedReportedFrame:'', manualValveProgress:'',w2TipText:'',green:false,successes:0,failures:0,
  Date:{now:()=>now}, setStorageSync:()=>{},showToast:()=>{},formatCallbackValue:()=>'',
  clearDeviceTableVersionFallback:()=>{},completeWindow2Opening:()=>{},
  setInterval:fn=>{timer=fn;return 1;},clearInterval:()=>{},
  publishDpsBase:args=>{s.transport=args;}};
 for(const name of ['pendingBoardCommandRef','sendingRef','lastAckSequenceRef','deviceTableHashRef',
  'syncRequestActiveRef','deviceTableReadPendingRef','syncTransferRef','syncGroupCapacitiesRef','syncDeadlineRef'])
   s[name]={current:name==='lastAckSequenceRef'?10:null};
 for(const name of ['Sending','ManualValveProgress','W2TipText','ShowW2ActionTip','DeviceReportPending',
  'SyncingDevices','TestDeviceTableReady']) s['set'+name]=v=>{s[name[0].toLowerCase()+name.slice(1)]=v;};
 vm.createContext(s); vm.runInContext(code,s); s.api.installTimeout();
 return {s, start:(command='device_state=231,1',kind='home')=>s.api.publishFrame('FRAME','开阀',
   ()=>{s.green=true;s.successes++;},false,()=>{s.failures++;},{kind,command}),
  receive:frame=>{s.normalizedReportedFrame=frame;s.api.receive();},tick:ms=>{now+=ms;timer();}};
}
let h=setup();h.start();
assert.strictEqual(h.s.manualValveProgress,'正在开阀门[231]');assert(!h.s.green);
h.s.transport.success();assert(!h.s.green,'cloud delivery cannot green the switch');
h.receive('CJACK1|old|11|SUCCEEDED|0|HOME|DEVICE_STATE=231,1');
assert(!h.s.green && h.s.pendingBoardCommandRef.current,'legacy queue ACK is insufficient');
h.receive('CJACK1|other|12|SUCCEEDED|0|HOME|DEVICE_STATE=230,1|CONFIRMED|-1');
assert(!h.s.green,'another valve cannot confirm 231');
h.receive('CJACK1|our|11|SUCCEEDED|0|HOME|DEVICE_STATE=231,1|CONFIRMED|-1');
assert(h.s.green && h.s.successes===1,'matching deferred ACK may arrive after unrelated newer sequence');
assert.strictEqual(h.s.manualValveProgress,'');assert.strictEqual(h.s.pendingBoardCommandRef.current,null);
h.receive('CJACK1|our|11|SUCCEEDED|0|HOME|DEVICE_STATE=231,1|CONFIRMED|-1');assert.strictEqual(h.s.successes,1);
for(const [code,phrase] of [[4006,'应答超时'],[4007,'拒绝'],[4008,'不匹配'],[4009,'总线'],[4010,'重启'],[4011,'关阀状态未确认']]) {
 h=setup();h.start();h.receive(`CJACK1|x|11|FAILED|${code}|HOME|DEVICE_STATE=231,1|CONFIRMED|231`);
 assert(!h.s.green && h.s.failures===1);assert(h.s.w2TipText.includes(phrase),h.s.w2TipText);
 assert.strictEqual(h.s.manualValveProgress,'');
}
h=setup();h.start('device_state=231,0');assert.strictEqual(h.s.manualValveProgress,'正在关阀门[231]');
h.receive('CJACK1|x|10|SUCCEEDED|0|HOME|DEVICE_STATE=231,0|CONFIRMED|-1');
assert(h.s.pendingBoardCommandRef.current,'cached old ACK must not complete current request');
h.tick(15000);assert(!h.s.green && h.s.failures===1 && h.s.w2TipText.includes('结果未确认'));
assert.strictEqual(h.s.manualValveProgress,'');
h=setup();h.s.devices=Array.from({length:8},()=>({type:'电磁阀',group:'1'}));h.start('group_state=1,1');
assert.strictEqual(h.s.pendingBoardCommandRef.current.timeoutMs,127000);
h.receive('CJACK1|x|11|SUCCEEDED|0|HOME|GROUP_STATE=1,1');assert(!h.s.green);
h.receive('CJACK1|x|11|FAILED|4006|HOME|GROUP_STATE=1,1|CONFIRMED|231');
assert(!h.s.green && h.s.w2TipText.includes('231号阀门'));
assert(h.s.w2TipText.includes('本组后续开阀已停止'));
h=setup();h.s.devices=Array.from({length:8},()=>({type:'电磁阀',group:'1'}));h.start('group_state=1,0');assert.strictEqual(h.s.pendingBoardCommandRef.current.timeoutMs,66000);h.receive('CJACK1|x|11|FAILED|4006|HOME|GROUP_STATE=1,0|CONFIRMED|231');
assert(!h.s.green && !h.s.w2TipText.includes('后续开阀已停止'));
h=setup();h.start('group_state=1,1');h.receive('CJACK1|x|11|SUCCEEDED|0|HOME|GROUP_STATE=1,1|CONFIRMED|-1');assert(h.s.green);
h=setup();h.start('on','round_irrigation');h.receive('AA55F10155AA');assert(!h.s.green,'round downlink echo is insufficient');
h.receive('CJACK1|x|11|SUCCEEDED|0|ROUND_IRRIGATION|ON|CONFIRMED|-1');assert(h.s.green);
h=setup();h.start();h.s.transport.fail({});assert(!h.s.green && h.s.failures===1);
assert.strictEqual(h.s.manualValveProgress,'');
console.log('PASS: physical completion gating, progress, identity, deferred/duplicate ACKs, batch failures, transport failure and timeout');
"""

if __name__ == '__main__':
    result = subprocess.run([str(NODE), '-e', RUNNER, str(DEPENDENCY_PANEL), str(PANEL)], cwd=PANEL)
    raise SystemExit(result.returncode)
