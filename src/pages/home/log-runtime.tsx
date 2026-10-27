import React, { useEffect, useRef, useState } from 'react';
import { View, Text, ScrollView, getStorageSync, setStorageSync, onAppHide, offAppHide, onAppShow, offAppShow, onDpDataChange, offDpDataChange } from '@ray-js/ray';
import { LogClient, LogSummary, LogDetail, LogView, groupLogDays } from './log-state';
import styles from './index.module.less';
const initialView: LogView = { rows:[],details:{},detailErrors:{},busy:false,detailId:null,queuedDetailId:null,more:false,message:'等待连接主机' };
export function useCloudLogs(deviceId: string | undefined, enabled: boolean, frame: string, send: (frame:string,onFail:()=>void)=>void) {
  const [foreground,setForeground]=useState(true);
  const [view,setView]=useState<LogView>(initialView);
  const client=useRef<LogClient|null>(null);
  const sendRef=useRef(send);sendRef.current=send;
  useEffect(()=>{
    const show=()=>setForeground(true);
    const hide=()=>{client.current?.setActive(false);setForeground(false);};
    onAppShow(show);onAppHide(hide);
    return ()=>{offAppShow(show);offAppHide(hide);};
  },[]);
  useEffect(()=>{
    setView(initialView);
    if(!deviceId)return undefined;
    const key=`cj96:cloud-log:1:${deviceId}`;let raw:any;
    try { const result:any=getStorageSync({key});raw=typeof result==='string'?result:result?.data; } catch (_) { raw=null; }
    const next=new LogClient(raw,(frame,onFail)=>sendRef.current(frame,onFail),()=>setView(next.view()),cache=>{
      try { setStorageSync({key,data:JSON.stringify(cache)}); } catch (_) { /* Reading remains usable if local storage is full. */ }
    });
    // Consume each DP event before React can coalesce it with a later status report.
    const receive=(event:{deviceId:string;dps:Record<string,unknown>})=>{
      if(event.deviceId!==deviceId)return;
      const value=event.dps?.['101'];
      if(typeof value==='string')next.accept(value.toUpperCase());
    };
    onDpDataChange(receive);
    client.current=next;setView(next.view());
    return ()=>{offDpDataChange(receive);next.dispose();client.current=null;};
  },[deviceId]);
  useEffect(()=>{client.current?.setActive(enabled&&foreground);},[deviceId,enabled,foreground]);
  useEffect(()=>{client.current?.accept(frame);},[frame]);
  return {view,refresh:()=>client.current?.refresh(),older:()=>client.current?.older(),detail:(id:number,more=false)=>client.current?.detail(id,more),cancelDetail:(id:number)=>client.current?.cancelDetail(id)};
}
function clock(seconds:number) {
  if(!seconds)return '--';const d=new Date(seconds*1000),pad=(n:number)=>String(n).padStart(2,'0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
const statusText=['执行中','已完成','有异常','已中断','结果待确认'];
const errorText=['','应答超时','发送失败','通信异常','设备拒绝','应答地址不符','应答状态不符','应答类型不符','请求未入队','离线跳过','结果未记录','总线故障','通信异常暂跳过','其他异常','关阀结果未记录'];
function detailText(d:LogDetail) {
  if(d.code===11 && d.count>1)return `总线故障，共 ${d.count} 项操作异常`;
  return `${d.group?`第${d.group}组 · `:''}${d.type===2?'解码器':'阀门'}${d.address} · ${d.open?'开':'关'} · ${errorText[d.code]}`;
}
function title(row:LogSummary) { return `${row.mode===1?'自动灌溉':'手动操作'}${row.name?` · ${row.name}`:''}`; }
export function CloudLogPanel({logs,online,scrollRequest=0,children}:{logs:ReturnType<typeof useCloudLogs>;online:boolean;scrollRequest?:number;children?:React.ReactNode}) {
  const [expanded,setExpanded]=useState<Record<number,boolean>>({});
  const [expandedDays,setExpandedDays]=useState<Record<string,boolean>>({});
  const {view}=logs;
  const days=groupLogDays(view.rows);
  const latestDay=days[days.length-1]?.key;
  const [scrollTarget,setScrollTarget]=useState('');
  const followEntryRead=useRef(true);
  const sawEntryRead=useRef(false);
  const previousScrollRequest=useRef(scrollRequest);
  useEffect(()=>{
    const clickedAgain=previousScrollRequest.current!==scrollRequest;
    previousScrollRequest.current=scrollRequest;
    if(!followEntryRead.current && !clickedAgain)return undefined;
    if(view.busy)sawEntryRead.current=true;
    if(!online || (sawEntryRead.current && !view.busy))followEntryRead.current=false;
    if(latestDay)setExpandedDays(current=>({...current,[latestDay]:true}));
    // Retarget after the expanded day has rendered, including the first reply after entry.
    // Once that read finishes, browsing older records/details must keep the user's position.
    setScrollTarget('');
    const timer=setTimeout(()=>setScrollTarget('cj96-cloud-log-bottom'),80);
    return ()=>clearTimeout(timer);
  },[view.busy,latestDay,online,scrollRequest]);
  return <View className={styles.cloudLogCard}>
    <View className={styles.cloudLogHeading}>
      <Text className={styles.cloudLogTitle}>灌溉日志</Text>
      <View className={`${styles.cloudLogButton} ${(!online||view.busy)?styles.cloudLogDisabled:''}`} onClick={()=>online&&!view.busy&&logs.refresh()}><Text>{view.busy?'读取中…':'刷新'}</Text></View>
    </View>
    <Text className={styles.cloudLogNotice}>按天查看 · 每轮一条简报 · 异常详情按需读取</Text>
    <Text className={styles.cloudLogMessage}>{online?view.message:'主机未在线，显示本机已缓存记录'}</Text>
    <ScrollView className={styles.cloudLogScroller} scrollY enhanced showScrollbar scrollIntoView={scrollTarget}>
      {view.more && view.rows.length<100 && <View className={styles.cloudLogMore} onClick={()=>online&&!view.busy&&logs.older()}><Text>加载更早20条</Text></View>}
      {!view.rows.length && <Text className={styles.cloudLogEmpty}>{view.busy?'正在读取简报…':'暂无主机简报'}</Text>}
      {days.map((day,index)=>{
        const open=expandedDays[day.key]??index===days.length-1;
        return <View key={day.key} className={styles.cloudLogDay}>
          <View className={styles.cloudLogDayHeading} onClick={()=>{
            setExpandedDays({...expandedDays,[day.key]:!open});
            if(open)day.rows.forEach(row=>logs.cancelDetail(row.id));
          }}>
            <Text>{day.key}</Text><Text>{open?'收起':'展开'}</Text>
          </View>
          <Text className={styles.cloudLogDayCounts}>已加载 {day.rows.length} 轮 · 成功 {day.ok} 项 · 异常 {day.bad} 项{day.pending?` · 待确认 ${day.pending} 项`:''}</Text>
          {open && day.rows.map(row=><View className={styles.cloudLogRow} key={row.id}>
        <View className={styles.cloudLogRowHeading}><Text>{title(row)}</Text><Text className={row.status===2||row.status===3?styles.cloudLogError:''}>{statusText[row.status]}</Text></View>
        <Text className={styles.cloudLogTime}>{clock(row.start)}{row.end?` 至 ${clock(row.end)}`:''}</Text>
        <Text className={styles.cloudLogCounts}>{row.groups}组 · 成功 {row.ok} 项 · 异常 {row.bad} 项{row.pending?` · 待确认 ${row.pending} 项`:''}</Text>
        {row.status===2 && row.bad===0 && <Text className={styles.cloudLogFootnote}>本轮组调度存在异常，完整原因请在主机查看。</Text>}
        {row.bad>0 && <View className={styles.cloudLogDetailButton} onClick={()=>{
          const open=!expanded[row.id];setExpanded({...expanded,[row.id]:open});if(open)logs.detail(row.id);else logs.cancelDetail(row.id);
        }}><Text>{expanded[row.id]?'收起异常':'查看异常详情'}</Text></View>}
        {expanded[row.id] && <View className={styles.cloudLogDetails}>
          {view.detailId===row.id && <Text>正在读取异常，最多等待15秒…</Text>}
          {view.queuedDetailId===row.id && <Text>等待当前读取完成后读取异常…</Text>}
          {view.detailErrors?.[row.id] && <Text className={styles.cloudLogError}>{view.detailErrors[row.id]}</Text>}
          {!view.details[row.id] && view.detailId!==row.id && view.queuedDetailId!==row.id && <View className={styles.cloudLogDetailButton} onClick={()=>online&&logs.detail(row.id)}><Text>{view.detailErrors?.[row.id]?'重试读取异常':'读取异常'}</Text></View>}
          {view.details[row.id]?.rows.length===0 && <Text>主机未返回可显示的异常，请刷新简报后重试</Text>}
          {view.details[row.id]?.rows.map((d,i)=><View className={styles.cloudLogFailure} key={i}><Text>{detailText(d)}</Text><Text className={styles.cloudLogTime}>{clock(d.time)}</Text></View>)}
          {view.details[row.id]?.more && view.detailId!==row.id && view.queuedDetailId!==row.id && <View className={styles.cloudLogDetailButton} onClick={()=>online&&logs.detail(row.id,true)}><Text>继续加载异常</Text></View>}
        </View>}
      </View>)}
        </View>;
      })}
      {view.rows.length>=100 && <Text className={styles.cloudLogFootnote}>APP 缓存最近100条，完整记录请在主机查看</Text>}
      <Text className={styles.cloudLogFootnote}>日期按灌溉开始时间归类；每日统计为已加载记录。开关分别计数，未确认不计成功。</Text>
      {children}
      <View id="cj96-cloud-log-bottom" className={styles.cloudLogBottom} />
    </ScrollView>
  </View>;
}
