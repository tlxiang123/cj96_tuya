// Exercise the production hook and panel with deterministic React hooks and a fake Ray transport.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('node:assert/strict'),ts=require('typescript');
const transpile=file=>ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/pages/home',file),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
let timers=new Map(),nextTimer=0;
const timerApi={setTimeout:fn=>{timers.set(++nextTimer,fn);return nextTimer;},clearTimeout:id=>timers.delete(id)};
const state={exports:{},...timerApi};vm.runInNewContext(transpile('log-state.ts'),state);
let slots=[],cursor=0,effects=[],dirty=false,renderFn,result;
const React={
 useState(initial){const i=cursor++;if(!slots[i])slots[i]={value:typeof initial==='function'?initial():initial};return [slots[i].value,value=>{const next=typeof value==='function'?value(slots[i].value):value;if(next!==slots[i].value){slots[i].value=next;dirty=true;}}];},
 useRef(value){const i=cursor++;if(!slots[i])slots[i]={current:value};return slots[i];},
 useEffect(fn,deps){const i=cursor++,old=slots[i];if(!old||deps.some((v,k)=>!Object.is(v,old.deps[k]))){effects.push(()=>{old?.cleanup?.();slots[i]={deps,cleanup:fn()};});}},
 createElement(type,props,...children){return {type,props:props||{},children:children.flat(Infinity).filter(x=>x!==null&&x!==undefined&&x!==false)};}
};
React.default=React;
function render(fn){renderFn=fn;let passes=0;do{dirty=false;cursor=0;effects=[];result=renderFn();const todo=effects;effects=[];todo.forEach(fn=>fn());assert(++passes<30,'render loop');}while(dirty);return result;}
function unmount(){for(const slot of slots)slot?.cleanup?.();slots=[];dirty=false;}
const gen='12345678AABBCCDD',saved={schema:1,generation:gen,cursor:1,older:1,more:false,rows:[{id:1,revision:1,start:1792602000,end:1792605600,mode:1,status:2,groups:1,ok:2,bad:1,pending:0,name:'程序3'}]};
const listeners={},transport=[],sendFailures=[];
const ray={View:'View',Text:'Text',ScrollView:'ScrollView',getStorageSync:()=>JSON.stringify(saved),setStorageSync:()=>{},onAppShow:fn=>listeners.show=fn,offAppShow:()=>{},onAppHide:fn=>listeners.hide=fn,offAppHide:()=>{},onDpDataChange:fn=>listeners.dp=fn,offDpDataChange:()=>delete listeners.dp};
const runtime={exports:{},require:name=>name==='react'?React:name==='@ray-js/ray'?ray:name==='./log-state'?state.exports:{default:new Proxy({},{get:(_,key)=>key})},...timerApi};
vm.runInNewContext(transpile('log-runtime.tsx'),runtime);
const {useCloudLogs,CloudLogPanel}=runtime.exports;
let frame='',enabled=true;
// Deliberately change send identity every render to reproduce lifecycle churn.
const hook=()=>useCloudLogs('device-a',enabled,frame,(s,fail)=>{transport.push(s);sendFailures.push(fail);});
render(hook);assert.equal(transport.length,1);assert.equal(timers.size,1);
for(let i=0;i<4;i++)render(hook);assert.equal(transport.length,1,'rendering must not rerequest');
result.detail(1);render(hook);assert.equal(result.view.queuedDetailId,1);assert.equal(transport.length,1);
const q=transport[0].split('|');frame=`CJLG1|S|${q[2]}|U|${gen}|1|1|0|`;
render(hook);assert.equal(transport.length,2);assert.equal(result.view.detailId,1);
const d=transport[1].split('|');
// Reply followed by an unrelated report before a render must still be consumed.
listeners.dp({deviceId:'other-device',dps:{101:`CJLG1|S|${d[2]}|D|${gen}|1|1|0|150,1,1,0,1,1,1`}});
assert.equal(result.view.busy,true);
listeners.dp({deviceId:'device-a',dps:{101:`CJLG1|S|${d[2]}|D|${gen}|1|1|0|150,1,1,0,1,1,1`}});
frame='UNRELATED-STATUS';
render(hook);assert.equal(result.view.busy,false);assert.equal(result.view.details[1].rows.length,1);
render(hook);assert.equal(transport.length,2);
listeners.hide();render(hook);assert.equal(timers.size,0);
listeners.show();render(hook);assert.equal(transport.length,3);
for(const fn of [...timers.values()])fn();render(hook);assert.equal(result.view.busy,false);assert.equal(transport.length,3);
result.detail(1,true);render(hook);assert.equal(result.view.detailId,1);
sendFailures[sendFailures.length-1]();render(hook);
assert.equal(result.view.busy,false);assert.match(result.view.detailErrors[1],/发送失败/);
unmount();assert.equal(timers.size,0);assert.equal(listeners.dp,undefined);
// Date expansion is local UI state and must not cause a transport request.
const row=saved.rows[0],time=(day,h)=>new Date(2026,9,day,h).getTime()/1000;
let detailCalls=0,olderCalls=0;
const panelLogs={view:{rows:[{...row,id:2,start:time(22,2),end:time(22,3)},{...row,start:time(21,2),end:time(21,3)}],details:{},busy:true,detailId:null,queuedDetailId:null,more:true,message:'正在读取主机简报'},refresh:()=>{},older:()=>olderCalls++,detail:()=>detailCalls++,cancelDetail:()=>{}};
let scrollRequest=0;
const panel=()=>CloudLogPanel({logs:panelLogs,online:true,scrollRequest});
const nodes=tree=>typeof tree==='object'?[tree,...tree.children.flatMap(nodes)]:[];
const texts=tree=>typeof tree==='object'?tree.children.map(texts).join(''):String(tree);
const flushScroll=()=>{assert.equal(timers.size,1);for(const [id,fn] of [...timers]){timers.delete(id);fn();}render(panel);assert.equal(nodes(result).find(n=>n.type==='ScrollView').props.scrollIntoView,'cj96-cloud-log-bottom');};
render(panel);flushScroll();
assert.deepEqual(nodes(result).filter(n=>n.props.className==='cloudLogDayHeading').map(texts),['2026-10-21展开','2026-10-22收起']);
assert(nodes(result).some(n=>n.props.id==='cj96-cloud-log-bottom'));
assert.equal(detailCalls,0);assert.equal(olderCalls,0);
// Initial replies arriving after mounting must retarget to the bottom after rendering.
panelLogs.view.rows.unshift({...row,id:3,start:time(22,4),end:time(22,5)});
panelLogs.view.busy=false;render(panel);
assert.equal(nodes(result).find(n=>n.type==='ScrollView').props.scrollIntoView,'');flushScroll();
const visible=nodes(result).filter(n=>n.props.className==='cloudLogRow').map(texts);
assert(visible[0].includes('02:00:00'));assert(visible[1].includes('04:00:00'));
assert.equal(nodes(result).filter(n=>n.props.className==='cloudLogDayHeading').length,2);
assert.equal(nodes(result).filter(n=>n.props.className==='cloudLogRow').length,2);
const previous=nodes(result).find(n=>n.props.className==='cloudLogDayHeading'&&texts(n).includes('2026-10-21'));
previous.props.onClick();render(panel);
assert.equal(nodes(result).filter(n=>n.props.className==='cloudLogRow').length,3);assert.equal(detailCalls,0);
const detailButton=nodes(result).find(n=>n.props.className==='cloudLogDetailButton');
detailButton.props.onClick();render(panel);assert.equal(detailCalls,1);assert.equal(timers.size,0);
// Timeout must replace the spinner with a visible retry in the expanded row.
const expandedRow=nodes(result).find(n=>n.props.className==='cloudLogRow'&&texts(n).includes('读取异常'));
assert(expandedRow);
panelLogs.view.detailId=1;panelLogs.view.busy=true;render(panel);
assert(texts(result).includes('最多等待15秒'));
panelLogs.view.detailId=null;panelLogs.view.busy=false;
panelLogs.view.detailErrors={1:'读取超时，主机未返回日志，请手动刷新或重试'};
render(panel);assert(texts(result).includes('读取超时'));assert(texts(result).includes('重试读取异常'));
assert(!texts(result).includes('最多等待15秒'));

// Manual history loading and detail reads must not force the user back to the bottom.
const older=nodes(result).find(n=>n.props.className==='cloudLogMore'&&texts(n)==='加载更早20条');
older.props.onClick();assert.equal(olderCalls,1);
panelLogs.view.busy=true;render(panel);assert.equal(timers.size,0);
panelLogs.view.rows.push({...row,id:4,start:time(20,2),end:time(20,3)});
panelLogs.view.busy=false;render(panel);assert.equal(timers.size,0);
// Tapping the selected log tab again also jumps down, without another summary request.
scrollRequest++;render(panel);flushScroll();assert.equal(olderCalls,1);assert.equal(detailCalls,1);
panelLogs.view.busy=true;render(panel);assert.equal(timers.size,0);
panelLogs.view.busy=false;render(panel);assert.equal(timers.size,0);
unmount();
// Returning to the log page starts a fresh entry scroll without any request from the panel.
render(panel);flushScroll();assert.equal(detailCalls,1);assert.equal(olderCalls,1);
assert.equal(nodes(result).filter(n=>n.props.className==='cloudLogRow').length,2);
unmount();assert.equal(timers.size,0);
console.log('PASS: stable hook lifecycle, queued detail replies, foreground/timeout recovery, chronological days/runs, entry/reply scroll, undisturbed history browsing');
