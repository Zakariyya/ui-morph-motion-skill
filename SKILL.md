---
name: ui-morph-motion
description: Use when the user wants a high-quality 2D motion-design promotional video, continuous UI morph, music-synced interface showcase or looping short with editable HTML (二维宣传片、UI变形动效、音乐卡点). Also use for rendering, visual QA and targeted repair of these timelines. Not for building a production app, live-action editing or ordinary website hover effects.
---

# UI Morph Motion

版本：**1.2.0**（2026-10-18）。保留解析弹簧、子帧渲染和音频工具，新增对象契约、Camera Rig、视觉 QA 与证据 Gate。

交付高品质二维动效视频及可编辑、离线可复现的 HTML/资源。运动语言服务产品：可克制、几何、弹性、排版、图表或图像驱动；不强制 Apple 风格、单根容器、镜头推拉、固定 BPM、时长或状态数。审美、文字与节奏仍需真实视觉判断。

## 输入与创意确认

先核对项目事实、目标观众/设备、画幅、时长、运动强度、文案、素材/许可、声音和循环要求；只问缺失关键项。制作前展示分镜、对象交接、节拍/秒数、光标、镜头和声音方案，让用户确认创意；已有批准不重复询问。维护 Skill 本身不启动影片素材收集。

首次分镜确认可提供常速/2 倍速/两版选项，但不默认双份制作。视频速度与音乐速度分别决定；临时静音预览不等于最终静音许可。授权自行安排声音时直接制作并说明；缺失最终声音选择要在前期明确。

按产品特征选语言。需要夸张动感时读 [expressive-motion.md](references/expressive-motion.md)；品牌发布/玻璃/照片案例按需读 [keynote-launch-film.md](references/keynote-launch-film.md)，其中 54 拍等仅是案例约束。不要把技术示例当定制成片。

## 制作闭环与 Gate

详细状态/证据格式见 [quality-gates.md](references/quality-gates.md)。必须区分 PASS、FAIL、BLOCKED、NEEDS_REVIEW；代码写好、HTML 打开和单元测试通过不是视觉放行依据。

1. **Preflight**：核对项目事实/许可；运行 `motion_qa.py doctor` 和 `preflight`，保留日志与最小截图。缺浏览器或依赖标 BLOCKED，按报告恢复，不绕过安全限制。
2. **Motion Blueprint**：分镜、对象关系、时间轴、阅读窗口、独立镜头/光标与技术方案；创意批准后实施。阅读 [continuity-and-camera.md](references/continuity-and-camera.md)，为重要对象写 Object Continuity Contract。
3. **Visual Proof**：用最终 `await seek(t)` 实现核心连续形变短动画；真实浏览器截图、逐拍联系表、边界扫描与回放。核心问题未解决不扩展全片。
4. **Full Production**：完成全时间轴、资源、声音和镜头。复用 [motion.js](assets/motion.js)，对象自身、场景、镜头与屏幕光标分离；任意时间独立渲染，可缓存静态资源。
5. **Verification**：完整 QA、编码/解码、正式帧、播放器、音画与需要时的循环检查。自动候选需要查看；未试听/未回放如实列出。依赖或代码变化后重跑相关证据。

同一对象的边界、位置和路径默认连续；遮罩退出后显示新对象不算连续形变。合并/分裂/替换允许明确的视觉交接契约，不强制单一根对象。内部内容需随几何重排，避免压缩叠字、底色拼接或空壳窗口。

## 执行工具

先读 [production.md](references/production.md) 获取旧渲染/音频接口，再读 [visual-qa.md](references/visual-qa.md) 配置遥测、阈值和命令。

- `scripts/motion_qa.py render --time …`：真实时间轴任意截图；`beats`：节拍联系表；`scan`：逐帧/边界、帧差、文字、轨迹与交接检查。
- `assets/qa-probe.js`：DOM 标注测量；Canvas 可返回同源 `motionQA()`。自动 Canvas 文字探针不掌握复杂裁切，不能冒充完整遥测。
- `scripts/render.py preview / render`：保留原四子帧 tmix→H.264 MP4、帧数/PTS/容器检查；预览凭据绑定当前 HTML 和本地依赖。
- `scripts/media.py analyze / mix`：节拍候选、精确音效锚点与混音。音频/速度变更另读 [audio-and-speed.md](references/audio-and-speed.md)。歌曲 downbeat、听感及授权不能由程序猜测。

完整字体内嵌不是要求。允许项目内相对资源、内嵌子集或合理自包含方案，保证离线解码、字体稳定及许可；不要默认把完整 CJK 字体转 Base64。

## 定向修复与交付

Render → Inspect → Diagnose → Patch → Re-render → Verify。先定位异常时间和对象，查看相邻帧，分析时间/几何/遮罩/层级/渲染原因，只改相关实现。使用 `motion_qa.py repair` 保留 before/after 哈希与局部复测，再回归受影响边界和全片。禁止靠降帧、删除动作、隐藏对象或淡入淡出假装修复。

明确标注 Concept Still（设计概念）、Timeline Still（seek 提取）、Rendered Frame（正式视频解码）。Concept Still 不能作为动画已实现证据。

同一任务沿用首次产出目录和主文件路径；并存版本在同目录明确命名，更新前按需保留旧版。交付 MP4、可编辑 HTML/所需资源、分镜/对象契约、素材许可、联系表和 QA/渲染报告；说明实际尺寸/帧率/帧数/时长/声音/循环与未验收项。生成不代表获准发布。

[example.html](assets/example.html) 保留旧技术演示，非通用美术模板。测试通过不证明审美、许可或真实音频试听通过。
