// Compact, read-only log protocol. Successful operations never have per-valve payloads.
export interface LogSummary {
  id: number; revision: number; start: number; end: number; mode: number; status: number;
  groups: number; ok: number; bad: number; pending: number; name: string;
}
export interface LogDetail { time: number; group: number; address: number; open: number; type: number; code: number; count: number }
export interface LogDetails { revision: number; rows: LogDetail[]; next: number; more: boolean }
export interface LogCache { schema: 1; generation: string; cursor: number; older: number; more: boolean; rows: LogSummary[] }
export interface LogView { rows: LogSummary[]; details: Record<number, LogDetails>; detailErrors: Record<number, string>; busy: boolean; detailId: number | null; queuedDetailId: number | null; more: boolean; message: string }
export interface LogDay { key: string; rows: LogSummary[]; ok: number; bad: number; pending: number }
// Calendar days use the same local time as the visible run timestamps. A run belongs to its start day.
export function groupLogDays(rows: LogSummary[]): LogDay[] {
  const days = new Map<string, LogDay>();
  for (const row of rows) {
    const seconds = row.start || row.end;
    const d = new Date(seconds * 1000), pad = (n:number) => String(n).padStart(2,'0');
    const key = seconds ? `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}` : '日期未知';
    let day = days.get(key);
    if (!day) { day = {key,rows:[],ok:0,bad:0,pending:0}; days.set(key,day); }
    day.rows.push(row); day.ok+=row.ok; day.bad+=row.bad; day.pending+=row.pending;
  }
  // Match the host: oldest at the top, newest at the bottom. Cache/paging order stays unchanged.
  return [...days.values()].sort((a,b)=>a.key==='日期未知'?-1:b.key==='日期未知'?1:a.key.localeCompare(b.key))
    .map(day=>({...day,rows:day.rows.sort((a,b)=>(a.start||a.end)-(b.start||b.end)||a.id-b.id)}));
}
type Kind = 'L' | 'U' | 'D';
interface Reply { token: string; kind: Kind | 'E'; generation: string; watermark: number; next: number; more: boolean; rows: LogSummary[]; details: LogDetail[]; error: string }
interface Request { token: string; kind: Kind; cursor: number; argument: number; remaining: number; initialWatermark?: number }
const integer = (s: string) => /^(0|[1-9][0-9]{0,9})$/.test(s) && Number(s) <= 2147483647;
const generationValid = (s: string) => /^[0-9A-F]{16}$/.test(s);
function nameFromHex(hex: string) {
  if (hex === '-') return '';
  if (!/^(?:[0-9A-F]{2}){1,24}$/.test(hex)) throw new Error('name');
  return decodeURIComponent(hex.replace(/../g, byte => `%${byte}`));
}
export function parseLogReply(text: string): Reply | null {
  try {
    if (text.length > 900 || !/^[A-Z0-9|,;_-]+$/.test(text)) return null;
    const f = text.split('|');
    if (f.length !== 9 || f[0] !== 'CJLG1' || f[1] !== 'S' || !/^[0-9A-F]{8}$/.test(f[2]) ||
      !['L','U','D','E'].includes(f[3]) || !generationValid(f[4]) || !integer(f[5]) || !integer(f[6]) || !/^[01]$/.test(f[7])) return null;
    const reply: Reply = { token:f[2], kind:f[3] as Reply['kind'], generation:f[4], watermark:+f[5], next:+f[6], more:f[7]==='1', rows:[], details:[], error:'' };
    if (reply.kind === 'E') { if (!['RESET','MISSING'].includes(f[8]) || reply.more) return null; reply.error=f[8]; return reply; }
    const rows = f[8] ? f[8].split(';') : [];
    if (rows.length > 20 || (reply.more && !rows.length)) return null;
    for (const row of rows) {
      const v = row.split(','); const detail = reply.kind === 'D'; const count = detail ? 7 : 11;
      if (v.length !== count || !v.slice(0, detail ? 7 : 10).every(integer)) return null;
      const n = v.map(Number);
      if (detail) {
        if (n[3]>1 || ![1,2].includes(n[4]) || n[5]<1 || n[5]>14 || n[6]<1) return null;
        reply.details.push({time:n[0],group:n[1],address:n[2],open:n[3],type:n[4],code:n[5],count:n[6]});
      } else {
        if (!n[0] || !n[1] || ![1,2].includes(n[4]) || n[5]>4 || (n[3] && n[3]<n[2]) || n[1]>reply.watermark) return null;
        reply.rows.push({id:n[0],revision:n[1],start:n[2],end:n[3],mode:n[4],status:n[5],groups:n[6],ok:n[7],bad:n[8],pending:n[9],name:nameFromHex(v[10])});
      }
    }
    return reply;
  } catch (_) { return null; }
}
const emptyCache = (): LogCache => ({schema:1,generation:'',cursor:0,older:0,more:false,rows:[]});
function validSummary(r: any): r is LogSummary {
  return r && ['id','revision','start','end','mode','status','groups','ok','bad','pending'].every(k => Number.isInteger(r[k]) && r[k]>=0 && r[k]<=2147483647) &&
    r.id>0 && r.revision>0 && [1,2].includes(r.mode) && r.status<=4 && typeof r.name==='string' && r.name.length<=24;
}
export function restoreLogCache(raw: any): LogCache {
  try {
    const v = typeof raw==='string' ? JSON.parse(raw) : raw;
    if (!v || v.schema!==1 || !generationValid(v.generation) || !Number.isInteger(v.cursor) || v.cursor<0 || v.cursor>2147483647 ||
      !Number.isInteger(v.older) || v.older<0 || v.older>2147483647 || typeof v.more!=='boolean' || !Array.isArray(v.rows) || v.rows.length>100 || !v.rows.every(validSummary)) return emptyCache();
    if (new Set(v.rows.map((r: LogSummary)=>r.id)).size!==v.rows.length) return emptyCache();
    return {...v,rows:[...v.rows].sort((a,b)=>b.id-a.id)};
  } catch (_) { return emptyCache(); }
}
let tokenCounter = Math.floor(Math.random()*0xFFFFFFFF);
export class LogClient {
  cache: LogCache; details: Record<number,LogDetails> = {}; message='打开页面时读取简报；异常详情按需读取';
  detailErrors: Record<number,string> = {};
  private resets=0;
  private queuedDetail: {id:number;more:boolean} | null=null;
  active=false; request: Request | null=null; private timer: ReturnType<typeof setTimeout> | null=null;
  constructor(raw: any, private send: (frame:string,onFail:()=>void)=>void, private changed:()=>void, private save:(cache:LogCache)=>void) { this.cache=restoreLogCache(raw); }
  view(): LogView { return {rows:this.cache.rows,details:this.details,detailErrors:this.detailErrors,busy:!!this.request,detailId:this.request?.kind==='D'?this.request.argument:null,queuedDetailId:this.queuedDetail?.id??null,more:this.cache.more,message:this.message}; }
  private notify() { this.changed(); }
  private cancel() { if(this.timer!==null)clearTimeout(this.timer);this.timer=null;this.request=null; }
  private fail(token:string,message:string) {
    if(this.request?.token!==token)return;
    const id=this.request.kind==='D'?this.request.argument:this.queuedDetail?.id;
    if(id!==undefined)this.detailErrors={...this.detailErrors,[id]:message};
    if(this.queuedDetail)this.detailErrors={...this.detailErrors,[this.queuedDetail.id]:message};
    this.queuedDetail=null;this.cancel();this.message=message;this.notify();
  }
  setActive(active: boolean) {
    if(this.active===active)return;this.active=active;
    if(!active){this.queuedDetail=null;this.cancel();this.message=this.cache.rows.length?'显示已缓存简报':'等待进入日志页并连接主机';this.notify();return;}
    this.refresh();
  }
  dispose() { this.active=false;this.queuedDetail=null;this.cancel(); }
  private ask(kind:Kind,cursor:number,argument:number,remaining=20,initialWatermark?:number) {
    if(!this.active || this.request)return;
    const token=(++tokenCounter>>>0).toString(16).padStart(8,'0').toUpperCase();
    this.request={token,kind,cursor,argument,remaining,initialWatermark};this.message=kind==='D'?'正在读取异常详情':'正在读取主机简报';
    if(kind==='D'){this.detailErrors={...this.detailErrors};delete this.detailErrors[argument];}
    this.timer=setTimeout(()=>this.fail(token,'读取超时，主机未返回日志，请手动刷新或重试'),15000);
    this.notify();
    try { this.send(`CJLG1|Q|${token}|${kind}|${this.cache.generation||'0'}|${cursor}|${argument}`,()=>this.fail(token,'读取请求发送失败，请检查连接后重试')); }
    catch (_) { this.fail(token,'读取请求未发出，请手动刷新或重试'); }
  }
  refresh() { if(!this.active || this.request)return;this.resets=0;this.ask(this.cache.generation && this.cache.cursor ? 'U':'L',this.cache.generation&&this.cache.cursor?this.cache.cursor:0,20); }
  older() { if(this.cache.more&&this.cache.rows.length<100&&!this.request){this.resets=0;this.ask('L',this.cache.older,20);} }
  detail(id:number,more=false) {
    if(!this.active)return;
    const row=this.cache.rows.find(r=>r.id===id);if(!row || !row.bad)return;
    const previous=this.details[id];if(previous && previous.revision===row.revision && !more)return;
    if(this.request) {
      if(this.request.kind==='D' && this.request.argument===id)return;
      // Keep at most one user-selected request, with no polling or duplicate sends.
      this.queuedDetail={id,more};this.notify();return;
    }
    this.resets=0;this.ask('D',more&&previous?.revision===row.revision?previous.next:0,id);
  }
  cancelDetail(id:number) {
    if(this.queuedDetail?.id===id)this.queuedDetail=null;
    if(this.request?.kind==='D' && this.request.argument===id){this.cancel();this.message='已取消读取异常';this.finish();return;}
    this.notify();
  }
  private finish() {
    const pending=this.queuedDetail;this.queuedDetail=null;
    if(pending)this.detail(pending.id,pending.more);
    this.notify();
  }
  accept(text:string) {
    const q=this.request, r=parseLogReply(text);if(!this.active || !q || !r || r.token!==q.token)return false;
    if(r.kind!=='E' && r.kind!==q.kind)return false;
    if(r.kind!=='E' && q.kind!=='L' && r.generation!==this.cache.generation)return false;
    // Validate all pagination before consuming the token or mutating the cache.
    if(r.kind==='L' || r.kind==='U') {
      const keys=r.rows.map(row=>r.kind==='L'?row.id:row.revision);
      if(new Set(r.rows.map(row=>row.id)).size!==r.rows.length || keys.some((v,i)=>i>0&&(r.kind==='L'?v>=keys[i-1]:v<=keys[i-1])))return false;
      if(keys.length && (r.next!==keys[keys.length-1] || (q.cursor && (r.kind==='L'?keys[0]>=q.cursor:keys[0]<=q.cursor))))return false;
      if(!keys.length && (r.more || r.next!==q.cursor))return false;
      if(r.kind==='U' && r.watermark<q.cursor)return false;
      if(q.cursor && r.kind==='L' && r.generation!==this.cache.generation){this.cancel();this.cache=emptyCache();this.details={};this.detailErrors={};this.ask('L',0,20);return true;}
    }
    if(r.kind==='D' && (r.next!==q.cursor+r.details.length || (r.more && !r.details.length)))return false;
    if(r.kind==='E' && r.error==='RESET' && this.resets>=1){this.fail(q.token,'主机日志暂未就绪，请稍后手动刷新');return true;}
    this.cancel();
    if(r.kind==='E') {
      if(r.error==='RESET'){this.resets++;this.queuedDetail=null;this.cache=emptyCache();this.details={};this.detailErrors={};this.save(this.cache);this.ask('L',0,20);}
      else {this.message='该记录已超出主机保留范围，请刷新';if(q.kind==='D')this.detailErrors={...this.detailErrors,[q.argument]:this.message};this.finish();}return true;
    }
    if(r.kind==='D') {
      const row=this.cache.rows.find(v=>v.id===q.argument);
      if(!row || row.revision!==r.watermark){this.message='该轮记录已更新，请先刷新简报';this.detailErrors={...this.detailErrors,[q.argument]:this.message};this.finish();return true;}
      const previous=this.details[q.argument];
      this.details={...this.details,[q.argument]:{revision:r.watermark,rows:[...(q.cursor&&previous?previous.rows:[]),...r.details],next:r.next,more:r.more}};
      this.message=r.more?'已读取部分异常，可继续加载':r.details.length?'异常详情已更新':'主机未返回可显示的异常，请刷新简报后重试';this.finish();return true;
    }
    if(r.generation!==this.cache.generation){this.cache=emptyCache();this.details={};this.detailErrors={};}
    this.cache.generation=r.generation;
    const map=new Map(this.cache.rows.map(row=>[row.id,row]));
    for(const row of r.rows) {
      const old=map.get(row.id);
      if(!old || row.revision>=old.revision){map.set(row.id,row);if(this.details[row.id]?.revision!==row.revision)delete this.details[row.id];}
    }
    const sorted=[...map.values()].sort((a,b)=>b.id-a.id);
    // Retain the newest 100. Never advance the older cursor past a dropped page.
    this.cache.rows=sorted.slice(0,100);
    const count=r.rows.length,remaining=q.remaining-count;
    if(r.kind==='U')this.cache.cursor=r.more?r.next:r.watermark;
    else {
      if(!q.cursor || !this.cache.older || r.next<this.cache.older)this.cache.older=r.next;
      this.cache.more=r.more;
      if(!q.cursor || q.initialWatermark!==undefined)this.cache.cursor=q.initialWatermark??r.watermark;
      if(sorted.length>100){this.cache.older=this.cache.rows[this.cache.rows.length-1].id;this.cache.more=true;}
    }
    this.save(this.cache);
    if(r.more && remaining>0 && count>0) {
      this.ask(r.kind,r.next,remaining,remaining,r.kind==='L'?(q.initialWatermark??r.watermark):undefined);return true;
    }
    this.message=r.kind==='U'?(r.more?'已更新20条，点击刷新继续读取变化':'简报已更新'):
      !this.cache.rows.length?'主机暂无灌溉记录':`已缓存${this.cache.rows.length}条简报`;
    this.finish();return true;
  }
}
