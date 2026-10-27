import React, { useEffect, useRef, useState } from 'react';
import { View, Text, onAppHide, offAppHide, onAppShow, offAppShow } from '@ray-js/ray';
import { OverviewState, OverviewSubscription, OVERVIEW_STALE_MS, overviewSeconds, formatGroups } from './overview-state';
import styles from './index.module.less';

export function useOverviewSubscription(deviceId: string | undefined, enabled: boolean,
  frame: string, send: (frame: string) => void) {
  const [foreground, setForeground] = useState(true);
  const [snapshot, setSnapshot] = useState<OverviewState | null>(null);
  const lease = useRef<OverviewSubscription | null>(null);
  useEffect(() => {
    const show = () => setForeground(true);
    const hide = () => setForeground(false);
    onAppShow(show); onAppHide(hide);
    return () => { offAppShow(show); offAppHide(hide); };
  }, []);
  useEffect(() => {
    setSnapshot(null);
    if (!deviceId || !enabled || !foreground) return undefined;
    const token = Math.floor(Math.random() * 0x100000000).toString(16).padStart(8, '0').toUpperCase();
    const subscription = new OverviewSubscription(send, Date.now, token);
    lease.current = subscription;
    subscription.start();
    const timer = setInterval(() => subscription.tick(), 10000);
    return () => { clearInterval(timer); subscription.stop(); lease.current = null; };
  }, [deviceId, enabled, foreground, send]);
  useEffect(() => {
    const next = lease.current?.accept(frame);
    if (next) setSnapshot(next);
  }, [frame]);
  return snapshot;
}

function useDisplayClock(snapshot: OverviewState | null) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!snapshot) return undefined;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [snapshot]);
  return now;
}
function clock(epoch: number) {
  if (!epoch) return '--:--';
  const d = new Date(epoch * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
function duration(seconds: number) { return `${Math.floor(seconds / 60)}分 ${String(seconds % 60).padStart(2, '0')}秒`; }

export const OverviewMode = React.memo(({ snapshot, online }: { snapshot: OverviewState | null; online: boolean }) => {
  const now = useDisplayClock(snapshot);
  const fresh = snapshot && online && now - snapshot.receivedAt < OVERVIEW_STALE_MS;
  const text = !online ? '设备离线' : !snapshot ? '等待主机状态' : !fresh ? '状态待更新'
    : snapshot.mode === 1 ? '自动' : snapshot.mode === 2 ? '手动' : '待机';
  return <Text className={styles.statusTitle} style={{ color: fresh && snapshot.mode === 2 ? '#ff8000' : '#159640' }}>{text}</Text>;
});

export const OverviewChart = React.memo(({ snapshot, online, children }: {
  snapshot: OverviewState | null; online: boolean; children?: React.ReactNode;
}) => {
  const now = useDisplayClock(snapshot);
  const fresh = snapshot && online && now - snapshot.receivedAt < OVERVIEW_STALE_MS;
  const seconds = snapshot ? overviewSeconds(snapshot, now) : null;
  let title = !online ? '设备离线' : '正在获取主机状态';
  let detail = '等待状态快照';
  if (snapshot) {
    const group = snapshot.group ? `阀组[${snapshot.group}]` : '';
    title = !fresh ? '状态待更新' : [ '暂无灌溉任务', `${group}准备运行`, `${group}正在开阀`,
      `${group}灌溉中`, `${group}正在关阀`, '本轮正在收尾', '今日灌溉已结束' ][snapshot.phase];
    detail = !fresh ? '请等待重新连接' : snapshot.phase === 1 ? `${clock(snapshot.nextStart)} 即将开阀`
      : snapshot.phase === 3 ? snapshot.mode === 2 ? `已运行 ${duration(seconds.elapsed)}`
        : seconds.remaining > 0 ? `剩余 ${duration(seconds.remaining)}` : '等待主机确认下一阶段'
      : snapshot.phase === 6 ? `已于 ${clock(snapshot.completedAt)} 完成`
      : snapshot.phase === 2 || snapshot.phase === 4 || snapshot.phase === 5 ? '等待主机确认' : '';
  }
  const compact = (groups: number[]) => {
    const text = formatGroups(groups);
    return text.length > 16 ? `${groups[0]}…${groups[groups.length - 1]}` : text;
  };
  return <>
    <View className={styles.donut}>
      <View className={styles.donutHole} />
      <Text className={styles.overviewWaiting}>{snapshot ? compact(snapshot.waiting) : '--'}</Text>
      <Text className={styles.overviewCompleted}>{snapshot ? compact(snapshot.completed) : '--'}</Text>
      <Text className={styles.overviewRunning}>{snapshot ? compact(snapshot.running) : '--'}</Text>
      <View className={styles.overviewCenter}>
        <Text className={styles.overviewTitle}>{title}</Text>
        <Text className={styles.overviewDetail}>{detail}</Text>
        {fresh && snapshot.mode === 1 && snapshot.roundEnd > 0 && <Text className={styles.overviewEta}>本轮预计结束 {clock(snapshot.roundEnd)}</Text>}
        {fresh && snapshot.fault && <Text className={styles.overviewFault}>存在异常，请查看日志</Text>}
      </View>
    </View>
    <View className={styles.legend}>
      <View className={styles.legendRow}><View className={`${styles.legendDot} ${styles.runningDot}`} /><Text className={styles.runningText}>灌溉中</Text></View>
      <View className={styles.legendRow}><View className={`${styles.legendDot} ${styles.waitingDot}`} /><Text className={styles.waitingText}>等待</Text></View>
      <View className={styles.legendRow}><View className={`${styles.legendDot} ${styles.completedDot}`} /><Text className={styles.completedText}>完成</Text></View>
    </View>
    <Text className={styles.overviewUnit}>单位：阀组</Text>
    {fresh && snapshot.mode === 1 && snapshot.dayEnd > 0 && <Text className={styles.overviewDayEnd}>当天预计结束 {clock(snapshot.dayEnd)}</Text>}
    {children}
  </>;
});
