// Production TypeScript state machine with deterministic foreground/timeouts.
const fs=require('fs'), path=require('path'),vm=require('vm'),assert=require('node:assert/strict');
const ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../src/pages/home/log-state.ts'),'utf8');
let timers=new Map(),timerId=0;
const sandbox={exports:{},setTimeout:(fn)=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id)};
vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText,sandbox);
const {LogClient,parseLogReply,restoreLogCache,groupLogDays}=sandbox.exports;
const gen='12345678AABBCCDD';
const row=(id,rev,ok=2,bad=0)=>`${id},${rev},100,200,1,${bad?2:1},1,${ok},${bad},0,E8AF95E9AA8C`;
const response=(q,data='',opts={})=>['CJLG1','S',q.token,opts.kind||q.kind,opts.gen||gen,opts.watermark??1,opts.next??(q.kind==='D'?q.cursor+1:+data.split(';').pop().split(',')[q.kind==='U'?1:0]),opts.more?1:0,data].join('|');
function client(raw){const sent=[],saved=[];const c=new LogClient(raw,s=>sent.push(s),()=>{},v=>saved.push(JSON.parse(JSON.stringify(v))));return {c,sent,saved};}
function reply(c,data,opts){return c.accept(response(c.request,data,opts));}
let t=client();assert.equal(t.sent.length,0);t.c.refresh();assert.equal(t.sent.length,0);
t.c.setActive(true);assert.equal(t.sent.length,1);assert.equal(t.c.request.kind,'L');
assert.equal(t.c.accept(response({...t.c.request,token:'DEADBEEF'},row(1,1))),false);
assert(reply(t.c,row(1,1)));assert.equal(t.c.cache.rows[0].name,'试验');assert.equal(t.c.cache.rows[0].ok,2);
const cached=JSON.stringify(t.c.cache);assert.equal(restoreLogCache(cached).rows.length,1);
t.c.refresh();assert.equal(t.c.request.kind,'U');assert.equal(t.c.request.cursor,1);
assert(reply(t.c,row(1,2,1,1),{watermark:2}));assert.equal(t.c.cache.rows.length,1);assert.equal(t.c.cache.rows[0].bad,1);
t.c.detail(1);assert.equal(t.c.request.kind,'D');assert(reply(t.c,'150,1,1,0,1,1,1',{watermark:2,next:1}));assert.equal(t.c.details[1].rows.length,1);
let n=t.sent.length;t.c.detail(1);assert.equal(t.sent.length,n); // detail cache prevents rereads
// Update invalidates stale detail and preserves the same run ID.
t.c.refresh();assert(reply(t.c,row(1,3),{watermark:3}));assert.equal(t.c.cache.rows.length,1);assert.equal(t.c.details[1],undefined);
t.c.refresh();n=t.sent.length;t.c.setActive(false);assert.equal(timers.size,0);
assert.equal(t.c.accept(response({token:'00000001',kind:'U'},row(2,4),{watermark:4,next:2})),false);
t.c.refresh();t.c.older();t.c.detail(1);assert.equal(t.sent.length,n);
t.c.setActive(true);for(const fn of [...timers.values()])fn();assert.equal(t.c.request,null);assert.equal(timers.size,0);assert.match(t.c.message,/手动刷新/);n=t.sent.length;assert.equal(t.sent.length,n);t.c.dispose();
// 900-byte pages chain only until the explicit 20-row budget.
t=client();t.c.setActive(true);const initialWatermark=50;
for(let page=0;page<4;page++){
  const rows=Array.from({length:5},(_,i)=>row(50-page*5-i,50-page*5-i)).join(';');
  assert(reply(t.c,rows,{watermark:initialWatermark,next:46-page*5,more:true}));
}
assert.equal(t.sent.length,4);assert.equal(t.c.request,null);assert.equal(t.c.cache.rows.length,20);assert.equal(t.c.cache.cursor,50);assert.equal(t.c.cache.older,31);
t.c.older();assert.equal(t.c.request.cursor,31);assert(reply(t.c,row(30,30),{watermark:55,next:30}));assert.equal(t.c.cache.cursor,50); // older reads must not skip concurrent changes
// Detail must have exactly the current summary revision.
t.c.refresh();assert(reply(t.c,row(50,56,1,1),{watermark:56,next:56}));t.c.detail(50);
assert(reply(t.c,'150,1,1,0,1,1,1',{watermark:57,next:1}));assert.equal(t.c.details[50],undefined);assert.match(t.c.message,/先刷新/);
t.c.refresh();assert(reply(t.c,'RESET',{kind:'E',gen:'AAAABBBBCCCCDDDD',watermark:0,next:0}));assert.equal(t.c.cache.rows.length,0);assert.equal(t.c.request.kind,'L');assert.equal(t.c.request.cursor,0);t.c.dispose();
// Limit retained rows to 100; reject malformed protocol/cache data.
t=client({schema:1,generation:gen,cursor:100,older:1,more:true,rows:Array.from({length:100},(_,i)=>({id:i+1,revision:i+1,start:100,end:200,mode:1,status:1,groups:1,ok:2,bad:0,pending:0,name:''}))});
t.c.setActive(true);assert(reply(t.c,row(101,101),{watermark:101,next:101}));assert.equal(t.c.cache.rows.length,100);assert.equal(t.c.cache.rows[99].id,2);n=t.sent.length;t.c.older();assert.equal(t.sent.length,n);t.c.dispose();
const good='CJLG1|S|1234ABCD|L|'+gen+'|1|1|0|'+row(1,1);
assert(parseLogReply(good));
for(const s of [good+'|',good.replace('E8AF95E9AA8C','FF'),good.replace('|1|1|0|','|0|1|0|'),good.replace('1234ABCD','1234abcd'),'A'.repeat(901)])assert.equal(parseLogReply(s),null);
assert.equal(restoreLogCache('{').rows.length,0);assert.equal(restoreLogCache({...JSON.parse(cached),rows:[null]}).rows.length,0);
// Firmware-generated production frame is independently parsed by the actual APP parser.
if(process.argv[2]){const f=fs.readFileSync(process.argv[2],'utf8').split(/\r?\n/).find(s=>s.startsWith('CJLG1|S|'));const parsed=parseLogReply(f);assert(parsed);assert(parsed.rows.length>0);assert.equal(parsed.rows[0].name,'一二三四五六七八');}
assert.equal(timers.size,0);
console.log('PASS: APP protocol, 20-row budget, same-run updates, detail cache, generation resets, 100-row cap, foreground-only reads');

// A click during a summary refresh is queued once and sent after the refresh.
t=client(cached);t.c.cache.rows[0].bad=1;t.c.setActive(true);
n=t.sent.length;t.c.detail(1);t.c.detail(1);
assert.equal(t.sent.length,n);assert.equal(t.c.view().detailId,null);assert.equal(t.c.view().queuedDetailId,1);
assert(reply(t.c,'',{next:1,watermark:1}));assert.equal(t.c.request.kind,'D');assert.equal(t.sent.length,n+1);
assert.equal(t.c.view().queuedDetailId,null);assert.equal(t.c.view().detailId,1);
t.c.detail(1);assert.equal(t.sent.length,n+1);
assert(reply(t.c,'150,1,1,0,1,1,1',{watermark:1,next:1}));assert.equal(t.c.view().busy,false);
t.c.refresh();t.c.detail(1,true);t.c.cancelDetail(1);assert.equal(t.c.view().queuedDetailId,null);
assert(reply(t.c,'',{next:1,watermark:1}));assert.equal(t.c.request,null);
t.c.refresh();t.c.detail(1,true);n=t.sent.length;
for(const fn of [...timers.values()])fn();
assert.equal(t.c.request,null);assert.equal(t.c.view().queuedDetailId,null);assert.equal(t.sent.length,n);
t.c.detail(1,true);assert.equal(t.c.request.kind,'D');t.c.setActive(false);assert.equal(timers.size,0);t.c.dispose();
// Days are grouped by the local start date, newest first, including midnight crossings.
const base=JSON.parse(cached).rows[0];
const secs=(day,hour)=>Math.floor(new Date(2026,9,day,hour).getTime()/1000);
const grouped=groupLogDays([
 {...base,id:1,start:secs(21,23),end:secs(22,1),ok:2,bad:1},
 {...base,id:2,start:secs(22,2),end:secs(22,3),ok:4,bad:0},
 {...base,id:3,start:secs(21,10),end:secs(21,11),ok:3,bad:2},
 {...base,id:4,start:0,end:0,ok:0,bad:0},
]);
assert.equal(grouped.length,3);assert.equal(grouped[0].key,'日期未知');
assert.equal(grouped[1].key,'2026-10-21');assert.equal(grouped[1].rows.length,2);
assert.equal(grouped[1].rows[0].id,3);assert.equal(grouped[1].rows[1].id,1);assert.equal(grouped[1].ok,5);assert.equal(grouped[1].bad,3);
assert.equal(grouped[2].key,'2026-10-22');assert.equal(groupLogDays([]).length,0);
console.log('PASS: queued detail, duplicate clicks, cancellation, timeout recovery, daily grouping and midnight attribution');

// Asynchronous publish failures, cancelled reads and stale callbacks are token-bound.
let failures=[];
const failClient=new LogClient(cached,(frame,fail)=>failures.push(fail),()=>{},()=>{});
failClient.cache.rows[0].bad=1;failClient.setActive(true);
assert(reply(failClient,'',{next:1,watermark:1}));
failClient.detail(1);const staleFailure=failures[failures.length-1];
failClient.cancelDetail(1);assert.equal(failClient.view().busy,false);assert.equal(timers.size,0);
failClient.detail(1);staleFailure();assert.equal(failClient.view().detailId,1);
failures[failures.length-1]();assert.equal(failClient.view().busy,false);assert.match(failClient.view().detailErrors[1],/发送失败/);
failClient.detail(1);for(const fn of [...timers.values()])fn();
assert.equal(failClient.view().busy,false);assert.match(failClient.view().detailErrors[1],/超时/);
failClient.detail(1);assert.equal(failClient.view().detailErrors[1],undefined);failClient.dispose();
// A host repeatedly returning RESET cannot keep the page loading or sending forever.
t=client(cached);t.c.setActive(true);
assert(reply(t.c,'RESET',{kind:'E',watermark:0,next:0}));
n=t.sent.length;assert(reply(t.c,'RESET',{kind:'E',watermark:0,next:0}));
assert.equal(t.sent.length,n);assert.equal(t.c.view().busy,false);assert.match(t.c.message,/稍后手动刷新/);
t.c.dispose();assert.equal(timers.size,0);
console.log('PASS: asynchronous send failures, active cancellation, stale callbacks, per-detail timeout and bounded RESET recovery');
