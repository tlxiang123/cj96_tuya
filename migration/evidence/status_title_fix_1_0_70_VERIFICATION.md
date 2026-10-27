# Verification — 状态卡标题单行显示（1.0.70）

日期：2026-10-26
工程：C:/Users/Administrator/Desktop/tuya
改动文件：`src/pages/home/index.module.less`（`.statusTitle`）、`src/pages/home/index.tsx`（`PANEL_VERSION`）

## 症状（基线）

真机截图 `Screenshot_2026-10-26-09-33-40-88_54aa0450b972c5.jpg`（2400×1080）实测：
状态卡内绿色标题被折成两行——

- 第一行 `设备离`：x 616–793，y 227–283
- 第二行 `线`：x 678–731，y 322–377

原因：`.statusTitle` 原 `width: 33.512064%`，卡片宽 379.3 px（1024 设计宽）→ 文本框仅 **127.1 px**；
而 `font-size: min(3.515625vw, 6vh)` 在 1024×600 下 = 36 px，四个汉字（Alibaba PuHuiTi）实测 **140 px** >
127.1 px，故换行。所有状态文案里最宽的是 `等待主机状态`（210 px），原框连 `状态待更新`（175 px）也放不下。

## 修复

中心点保持不动：原 `left 27.345845% + width 33.512064%/2 = 44.101877%`；新 `left 9.1% + width 70%/2 = 44.1%`（偏差 0.0019%，约 0.007 px）。

```less
.statusTitle {
  position: absolute;
  left: 9.1%;          /* 原 27.345845% */
  top: 6.521739%;
  width: 70%;          /* 原 33.512064%，265.5 px @1024 */
  color: #005bbb;
  font-size: min(3.515625vw, 6vh);
  line-height: min(5.371094vw, 9.166667vh);
  text-align: center;
  white-space: nowrap; /* 新增：状态文案永不换行 */
}
```

## 验证（executed）

| 检查 | 命令 | 结果 |
|---|---|---|
| 文本宽度 vs 文本框 | Pillow + `migration/reference/font/Alibaba-PuHuiTi-Regular.ttf` | `设备离线` 140 px、`等待主机状态` 210 px，文本框 265.5 px → 全部放得下；`fits: True` |
| 样式编译进产物 | 读 `dist/tuya/pages/home/index.css` | 命中 `.statusTitle__hVUxvq{color:#005bbb;text-align:center;white-space:nowrap;width:70%;font-size:min(3.51563vw,6vh);line-height:min(5.37109vw,9.16667vh);position:absolute;top:6.52174%;left:9.1%}` |
| 版本进入产物 | 读 `dist/tuya/pages/home/index.js` | `1.0.70` 存在，`1.0.69` 已不存在 |
| 构建 | `python dev.py build` | 退出码 0，Ray 2.1 s，`build done` |
| 回归 | `python dev.py test` | 10/10 PASS（含 `test_tuya_overview.py` 的 JSX 渲染断言） |
| 版式示意 | `migration/evidence/status_title_1_0_70_preview.png` | 1024×600 按 LESS 几何重绘，标题单行居中于卡片 |

## 未验证

- 真机/IDE 预览的实际渲染与字体度量（Ray 运行时字体可能与参考 TTF 有 1–2 px 差异；文本框 265.5 px 对 210 px 的最长文案仍有 55 px 余量，风险低）。
- 其它四个状态（`自动` / `手动` / `待机` / `状态待更新`）在真机上的表现；已由同一 nowrap 规则覆盖。

## 回滚

```text
把 .statusTitle 的 left 改回 27.345845%、width 改回 33.512064%、删掉 white-space: nowrap；
PANEL_VERSION 改回 '1.0.69'；python dev.py build。
```
