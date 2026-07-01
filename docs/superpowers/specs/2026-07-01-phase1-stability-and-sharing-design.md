# Phase 1 设计:操作稳定性、音频准确性、可分享游戏 URL

- 日期:2026-07-01
- 分支:`feat/stability-sharing`(基于 `dev`)
- 状态:待用户复核 → 转 writing-plans

## 背景与目标

用户的两个核心诉求:
1. **用户操作更稳定、更准确**
2. **生成的游戏更多样、更好玩**

三路并行代码审计(前端操作流、音频准确性+翻译多样性、生成层+可玩性)确认这两个目标背后是 4 个相对独立的病灶,横跨前端/音频/翻译/生成四层。因此拆成两期:

- **Phase 1(本设计)= 目标 1「稳定 & 准确」+ 一个传播向新特性(可分享游戏 URL)。**
- **Phase 2 = 目标 2「多样 & 好玩」**(见文末"不纳入")。

新增诉求(用户本轮提出):**最终生成的游戏以独立 URL 呈现**,便于分享传播;浏览器返回键行为为「游戏页 → 生成页 → 主页」三级。

## 范围

### 纳入 (In scope)

- **A. 前端 · `useGenerationJob` 任务控制器**:把 `录音→分析→翻译→生成→轮询` 整条生命周期从 `App.tsx` 抽成一个 reducer 驱动的状态机 hook,统一持有中断/超时/重试/会话钉死/进度单一真相源/断线重连。
- **B. 前端 · 路由与可分享游戏 URL**:新增 `/create`、`/game/{id}` 两条路由,形成「主页 → 生成页 → 游戏页」三级历史栈;游戏页可分享、可直连、带分享按钮与引流 CTA。
- **C. 前端 · Recorder 按住录音 + 麦克风错误细分**:真·hold-to-bark(Pointer 事件),空录音/权限错误精确处理。
- **D. 后端 · 生成可靠性**:`max_tokens` 截断检测 + 续写、生成重试预算、空壳目录清理、模型 id 自检。
- **E. 后端 · 音频准确性**:RMS 强度归一化、无音高显式 UNKNOWN、启发式回退也能拒绝非狗叫。

### 不纳入 (Out of scope → Phase 2)

- Playwright 冒烟校验门 + 失败重抽(用户明确留 Phase 2;涉及服务器无头 Chromium 内存问题需专门设计)。
- 多样性:每会话独立去重档案(消除全站共用 `default.json` 的污染)、风格卡随狗叫特征选择、per-cell 去重、3/5 候选数修正与强制、`_select` 结构化新颖度。
- 好玩:juice 底线(震屏/粒子/hitstop)强制、狗叫 DNA 真正注入游戏代码、最高分 `localStorage` 持久化、生成层去重/重抽。
- 更高分辨率的 entropy / game_params。

> 说明:3/5 候选数矛盾虽是明确 bug,但它属于翻译多样性范畴,与 Phase 2 的 `_select`/档案改造同处一片代码,合并到 Phase 2 一次改完,避免两次触碰同一文件。

## 现状问题(实证摘要)

| # | 问题 | 证据 | 归属 |
|---|---|---|---|
| 1 | 整条 `handleRecorded` 异步链卸载/切会话不中断,resolve 后回灌旧状态 | `App.tsx:207`(poll 未传 signal)、`App.tsx:123`(唯一 effect 只跳表);`api.ts:352-359` 有 AbortSignal 却没接 | A |
| 2 | 会话 id 按调用闭包捕获,翻译用会话 A、生成提交会话 B | `App.tsx:117,160,180` | A |
| 3 | 生成无总超时,轮询 `while(true)` 可无限卡 BUILDING | `api.ts:356-367` | A |
| 4 | 单次 `getJob` 502 直接把任务打成 error(后端仍在跑,成品只能去 /works 捞) | `api.ts:360-366` → `App.tsx:233` | A |
| 5 | 进度双通道(轮询 + SSE)不同步,SSE 终态帧只 close 不驱动跳转,页面最多滞后 5s | `App.tsx:207` vs `EventStream.tsx:93`/`api.ts:406` | A |
| 6 | "按住模仿狗叫"未实现,实为点两下 | `Recorder.tsx:87,117,124` 全 onClick | C |
| 7 | 麦克风错误不区分,静默面板还误导"没拿到权限" | `Recorder.tsx:68-71`、`App.tsx:318-335` | C |
| 8 | 约 33% 生成是空壳(只有 CLAUDE.md、无 game.html) | 48 目录中 16 个空壳 | D |
| 9 | `max_tokens` 截断不可检测且致命(cap 16000 对 28–33KB 游戏不够) | `_api_backend.py:439` 只处理 delta/stop;`settings.py:49` | D |
| 10 | 失败零重试、空壳不清理 | `routes/game.py:164` | D |
| 11 | YAMNet 异常即回退,而回退把一切判为狗叫 → 拒非狗叫防线蒸发 | `classify.py:32-69,84-89` | E |
| 12 | RMS 强度未归一,吃麦克风增益 → 翻转 mood/难度 | `tokens.py:11-25` | E |
| 13 | 无音高静默判 LOW(应为 UNKNOWN) | `tokens.py:29-30` | E |

## 设计

### A. 前端 · `useGenerationJob` 任务控制器

新增 `frontend/src/lib/useGenerationJob.ts`——reducer 驱动的状态机 hook,独占整条生成生命周期。`App.tsx` 从 445 行"一肩挑"瘦回"编排 + 展示"。

**单一 phase 真相源(判别联合):**

```
idle
analyzing
rejected   { reason: 'no_sound' | 'not_a_bark', detail }
translating
generating { jobId, sessionId, startedAt, elapsedS, lastEventAt, progress }
playable   { gameId, concept }
error      { stage, message, recoverable, jobId? }
```

**职责:**

1. **中断**:每次运行创建一个 `AbortController`,贯穿 analyze/translate/generate/poll。在组件**卸载**与**会话切换**(cleanup 依赖 `sessionId`)时 abort。彻底消除"resolve 回灌旧状态/弹旧游戏"。
2. **会话钉死**:run 开始时把当前 `sessionId` 捕获进本次运行状态,后续所有请求都用它;切会话触发 abort + 不影响已在途 run 的归属。
3. **进度单一真相源**:SSE 为实时进度源;其终态帧(`done`/`failed`/`cancelled`)立即触发一次 `getJob` 完成跳转(消除最多 5s 滞后);轮询降为**兜底对账**(SSE 断了才起作用)。装饰进度条由真实 `elapsedS`/`lastEventAt` 驱动,不再自顾自爬。
4. **poll 容错**:每次 `getJob` 包 try/catch;连续失败计数 + 退避后才判致命,区分「暂时性·重连中」与「致命」。单次 502 不再打死任务。
5. **总超时**:墙钟上限(默认 10min)→ 进入 `error{ recoverable:true, reason:'stuck' }`,给"重试 / 查看作品"出口,不再无限 BUILDING。
6. **断线重连**:活跃 `{ jobId, sessionId, gameId? }` 存 `localStorage`;组件 mount 时若有未完成 job → 恢复 poll/SSE(重新接管);若已有完成的 gameId → 可还原结果页。覆盖刷新 / 误触返回。
7. **取消**:修掉 `jobId` 尚为 null 的竞态;`cancelJob` 失败也停 UI + 记录意图;与 abort 协同。

**UI 契约**:`App.tsx` 只消费 `state` 与动作 `start(blob) / cancel() / reset() / reattach()`。附带修复:开启 `noUncheckedIndexedAccess`,`STATUS[phase.kind]`(`App.tsx:64`)加兜底,消除潜在 `undefined.cn` 崩溃。

### B. 前端 · 路由与可分享游戏 URL

**三级页面 = 三个历史条目:**

| 层级 | 路由 | 内容 |
|---|---|---|
| 主页 | `/` | 落地/发现:大录音按钮(按住)+ 作品集预览 |
| 生成页 | `/create` | `useGenerationJob` 宿主:分析 → 翻译 → 生成 → 概念卡/结果 |
| 游戏页 | `/game/{id}` | 全屏游戏(iframe → `/api/game/{id}/play`)+ 分享按钮 + "🐕 做一个你自己的" CTA |

**历史栈与返回:**

```
/  ──分析确认是狗叫──▶  /create  ──playable·自动跳转──▶  /game/{id}
主页                     生成页                            游戏页(独立URL)
        ◀──── 二次返回 ────        ◀──── 一次返回 ────
```

- 录音留在 `/`(用户选择:改动小、即录即做)。松手 → `start(blob)`,**分析在 `/` 进行**;`no_sound`/`not_a_bark` 直接在 `/` 内重录(不 push 历史,失败尝试不污染返回栈);分析确认是狗叫 → `navigate('/create')`(push)继续 translate→generate。
- 到 `playable` → 控制器把 `gameId` 交给路由 → `navigate('/game/{id}')`(push,自动跳转,契合"直接以新 URL 出现")。
- 游戏页返回 → `/create`(那局概念卡/结果,即"制作游戏的那一级");再返回 → `/`。
- 概念卡在返回后仍可见(控制器状态在内存中);若在 `/create` 刷新则走断线重连恢复,恢复不了则回 `/`。
- "做一个你自己的" / "再来一个" → `navigate('/')` 并 `reset()`(用 pushState 而非堆叠,避免历史膨胀)。

**路由实现:** 扩展 `frontend/src/lib/router.ts`,新增极小的参数匹配(如 `useRoute()` 返回 `{ name, params }`,匹配 `/game/:id`)。`navigate()` 现成(pushState + routechange 事件),天然产生历史条目。

**游戏页解耦:** `/game/{id}` **不依赖生成管线**,仅按 id 渲染 iframe + chrome,刷新/直连独立还原。新增 `frontend/src/components/GamePage.tsx`(或路由级组件)。

**分享:** 游戏页分享按钮:`navigator.share`(移动端原生)可用则用,否则复制链接到剪贴板 + toast。链接形如 `https://bark2game.zhangrg.top/game/9e2b9dcc3321`。

**`/works` 一致化:** 作品卡"打开作品"统一 `navigate('/game/{id}')`,返回天然回 `/works`。

**部署:** nginx 已有 SPA 兜底 `try_files $uri $uri/ /index.html`(`deploy/nginx/zhangrg-bark.conf:37-38`),直连 `/game/{id}`、`/create` 已可正确回落 index.html,**无需改 nginx**。

### C. 前端 · Recorder 按住录音 + 麦克风错误

`frontend/src/components/Recorder.tsx` 用 Pointer 事件重写:

- `onPointerDown` → 开始;`onPointerUp / onPointerCancel / onPointerLeave` → 停止;`setPointerCapture` 保证手指滑出按钮也能正常停。桌面鼠标同为按住。
- 不支持 `PointerEvent` 时回退点击切换(渐进增强)。
- 松手停止后由 `App` 调 `start(blob)` → `navigate('/create')`。
- **空录音**改为**基于数据**判定(chunks 真有内容),空则报"录音为空,请再试一次";替换现有仅墙钟 300ms 的 guard(`Recorder.tsx:57`)。
- **麦克风错误**按 `err.name` 分支:`NotAllowedError` → 权限引导 + 重试;`NotFoundError` → 无设备;其它 → 通用。删掉静默面板(`App.tsx:318`)里误导的"没拿到权限"一条。
- 修复 `onRecorded` 第二参(时长)被 `App.tsx:136` 丢弃的契约不一致(采用或移除)。

### D. 后端 · 生成可靠性

**`backend/bark_to_game/generate/_api_backend.py`:**

- `_handle_event`(`:439`)捕获 `message_delta.delta.stop_reason`。遇 `max_tokens`:发**续写请求**("continue the HTML from where you stopped")并拼接,直至块闭合或达到续写次数上限。
- `_extract_fenced_blocks`(`:408`)显式识别"未闭合的 ```html 块"→ 触发续写,而非直接抛"no html block"。
- `API_MAX_OUTPUT_TOKENS` 16000 → **32000**(`settings.py:49`),降低截断频率(与续写互补)。

**`backend/bark_to_game/routes/game.py`(`_run_job`):**

- **重试预算**:`generate()` 包 1–2 次重试(针对续写后仍失败/停滞等瞬时态);**不**对 `RateLimitedError` 重试。
- **空壳清理**:终态失败 `rmtree` 该 job 目录;并做一次性清扫已存在的 16 个空壳目录(独立脚本/启动时一次)。
- **模型 id 自检**:启动时校验配置的模型 id 可解析,坏 id 给清晰报错(线上现可跑说明当前 id 有效,此为防回归)。

### E. 后端 · 音频准确性

**`backend/bark_to_game/audio/`:**

- **强度归一化**:RMS 先按本片峰值(或 dBFS)归一,再分 SOFT/NORMAL/LOUD(`tokens.py:11-25`)。消除麦克风增益依赖,稳定 mood 与 `game_params.intensity`。
- **无音高 UNKNOWN**:`f0_mean_hz is None` 时输出显式 `UNKNOWN`,不再默认偏低 `LOW`(`tokens.py:29-30`)。
- **回退拒非狗叫**:YAMNet 不可用改用启发式时,加一道轻量能量/谱判据(不再无脑 `is_dog_like=True`),明显人声/静音/噪声仍可判 `not_a_bark`(`classify.py:32-69`);响应带 `degraded: true` 标记,供前端与后续翻译层参考。

## 数据流(端到端,Phase 1 后)

```
/ 主页:hold-to-bark(Pointer)──松手──▶ start(blob)
     useGenerationJob:
       AbortController = new()  (卸载/切会话即 abort)
       sessionId 钉死
       postAnalyze ─┬─ rejected(no_sound|not_a_bark) → 在 / 内重录(不 push 历史)
                    └─ ok(是狗叫) → navigate('/create')       [history: /, /create]
  /create:
       postTranslate → 概念卡
       postGenerate (202 + jobId) → localStorage 持久化 {jobId, sessionId}
       SSE(实时进度) ─终态帧→ getJob → playable{gameId}
          轮询(兜底对账 + 容错重试 + 10min 总超时)
       playable → navigate('/game/{id}')                      [history: /, /create, /game/{id}]
  /game/{id}:iframe(/api/game/{id}/play) + 分享按钮 + "做一个你自己的" CTA(纯按 id,免管线)
       返回 → /create(概念卡)  再返回 → /
```

## 错误处理

- **前端**:所有网络请求经容错层;瞬时错误 → 重连中(不致命);致命 → `error{recoverable}` 带明确出口;abort 不算错误(静默)。
- **总超时/卡死**:`error{reason:'stuck'}` → "重试 / 查看作品"。
- **后端截断**:续写补救;续写仍失败 → `_run_job` 重试;彻底失败 → 清空壳 + 友好 SSE 错误帧。
- **音频**:静音/非狗叫 → 明确 `rejected`;回退降级 → `degraded` 标记但不致命。

## 测试策略(TDD:先写失败测试)

- **前端 Vitest**:`useGenerationJob` reducer 全转移(中断 / 超时 / poll 容错重试 / 会话钉死 / 断线重连 / 取消竞态);`router` 参数匹配 + 历史栈;Recorder 的 Pointer 行为与空录音守卫。
- **后端 pytest**:截断续写、重试预算、空壳清理、RMS 归一化、UNKNOWN、回退拒非狗叫。
- **Playwright(桌面 + 移动)**:录音流程、三级返回、分享按钮、直连 `/game/{id}`、模拟中途切会话/瞬时 502(mock 后端)。遵循 CLAUDE.md 验收标准走全旅程(含边界/错误流)。

## 实现顺序(里程碑,各自可独立测试 + 独立 PR 到 dev)

1. **后端生成可靠性(D)** —— 最痛最便宜,先消除 33% 空壳。
2. **前端任务控制器(A)** —— 稳定性地基。
3. **路由与可分享游戏 URL(B)** —— 依赖 A(控制器交出 gameId)。
4. **Recorder 按住录音(C)** —— 独立,依赖 A 的 `start()` 契约。
5. **音频准确性(E)** —— 独立,后端内聚改动。

## 风险与缓解

- **控制器抽取回归**:先补 reducer 单测锁定所有转移,再迁移 `App.tsx`;保持外部行为等价。
- **续写拼接边界**:续写点可能落在标签中间 → 以"未闭合 ```html"为准继续,拼接后整体校验能提取到完整块;拿真实截断样本回归。
- **Pointer 事件跨端差异**:iOS Safari / 桌面鼠标 / 触控笔分别在 Playwright 移动 + 桌面视口验证;保留 click 回退。
- **历史栈膨胀**:重录/再来用 `navigate('/')` 而非无限 push;必要处用 replaceState。
