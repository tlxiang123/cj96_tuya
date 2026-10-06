# CJ96 Tuya APP development instructions

Read 开始阅读_迁移与开发交接.md (or migration/开始阅读_迁移与开发交接.md) first.
Use Python 3 for automation, filesystem, images, packaging and build orchestration. Do not provide PowerShell/CMD/BAT scripts unless explicitly requested.
Keep memory generation/use enabled when available. On resume, read Context Keeper snapshots before project operations; reconcile with newest requests. Consult relevant local memories if present, but never treat historical runtime/build results as current proof.
APP source is panel/ in the standalone archive and repository root in GitHub. Do not restore the old mirror over it.
Maintain separate native image/background and Text elements. Measure actual visible icon bounds before scaling; preserve transparency and canvas dimensions.
Do not restore debug-only 未添加 or 清除表格 controls.
Preserve existing handlers, DP101/cj96_raw and device-sync/ack logic for visual-only changes.
Do not casually upgrade dependencies or rewrite yarn.lock. Validate build/tests; mocks are not phone/cloud/hardware validation.
Do not commit secrets, sessions, node_modules, dist, corrupt backups or personal screenshots. The GitHub repository is public.
Do not alter FlyThings Ctrl+Alt+R native deployment, plugins, progress window or system/network/proxy settings.
