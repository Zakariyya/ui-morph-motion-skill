# Visual QA、环境恢复与定向修复

依赖沿用 production.md 的 Python 3.10+、NumPy、Pillow、Playwright/Chromium、FFmpeg。无需前端框架。
所有路径相对当前工作目录；固定本任务产出目录，下列 `qa/` 为示例。命令 `--help` 查看参数。

```sh
python3 "$SKILL/scripts/motion_qa.py" doctor --out qa/environment
python3 "$SKILL/scripts/motion_qa.py" preflight assets.json --out qa/assets
python3 "$SKILL/scripts/motion_qa.py" render scene.html --time 4.25 --out qa/frame.png
python3 "$SKILL/scripts/motion_qa.py" beats scene.html --bpm 120 --beats 28 --out qa/beats
python3 "$SKILL/scripts/motion_qa.py" scan scene.html --config qa-config.json --out qa/full
python3 "$SKILL/scripts/motion_qa.py" gate gates.json --out qa/gates
```

120/28 只是 CLI 示例；实际使用分镜 BPM/拍数。不传这两个参数时取 scene.beats。
scan 默认逐输出帧采样并添加边界 ±1ms、±1/2 帧位置；支持 `--start --end --fps`。降低 QA 采样密度必须记录，不能声称已做逐帧检查；不改变最终导出 FPS。
`replay scene.html --out qa/replay` 运行实际 requestAnimationFrame 回放，保存时间日志和末帧；它不代替人类观看。

输出 PNG、report.json、候选/边界联系表。报告含时间、阈值、遥测、源/依赖哈希和截图哈希。帧差在缩小至 160px 的画面上计算；细小局部瑕疵可能漏检，原尺寸 PNG 保留。
随机次序 seek 复测实际截图；帧差/邻域孤帧检测仅作 NEEDS_REVIEW；高速形变本身不是失败。

## 探针和配置

保留原 `seek()` 返回有限数字的 flat probe。另增同步或异步 `motionQA()`，在 seek 完成后读取同一次绘制的数据：

```js
return {
 objects:[{id:'hero',box:[x,y,w,h],opacity:1}],
 texts:[{id:'title',box:[x,y,w,h],fontSize:28,opacity:1,clip:[cx,cy,cw,ch]}],
 camera:{x:0,y:0,zoom:1,anchor:{x:320,y:320},matrix:[1,0,0,1,320,320]},
 cursor:{x:100,y:100,pressed:true,dragging:true,target:[100,100]}
};
```

box、clip、fontSize 为最终画布屏幕空间（已包含镜头/局部缩放），不是设计稿坐标。DOM 可加载 assets/qa-probe.js，标注 `data-motion-id`、`data-qa-text` 自动测量；不要嵌套重复标注同一文字。旋转文字的轴对齐框、非矩形遮罩与刻意叠字需人工复核。Canvas 使用绘制时的 measureText 与当前矩阵计算边界，禁止猜测或硬编码“合格框”。

```json
{
 "boundaries":[1.5,4.25],
 "cameraRequired":true,
 "limits":{"cursorX":{"speed":2000,"acceleration":80000},"width":{"speed":6000,"acceleration":200000}},
 "readability":{"deviceWidth":360,"minFont":12,"safeMargin":32},
 "continuity":[{"start":0,"end":5,"ids":["hero","successor"]}],
 "readingWindows":[{"id":"title","start":2,"end":3.5,"minSeconds":1}],
 "exemptions":[]
}
```

阈值按对象/属性和实际 dt 配置（px/s、px/s²；zoom 可用 1/s）。报告保留异常测量值。可用 `pointerEvents:[{"time":1,"type":"press"},{"time":1.5,"type":"release"}]` 检查按下/释放状态。刻意瞬移豁免必须有 `key,start,end,approved:true,reason` 并与已确认创意相符；不删除报告记录。持续时间要求按文案长度与受众确定，12px 不是通用审美标准。
可选 `regions:[{"id":"content","start":4,"end":4.5,"box":[100,100,600,400],"minStd":2}]` 标出预期有内容的区域变得近乎纯色的候选；阈值需按设计设定，不能把刻意留白直接判错。

当前连续性检查可发现契约覆盖期间所有承接对象不可见（包含画布与 clip 的交集）；不能从 ID 推断轮廓真的连续。黑白拼接、复杂形态归属和构图品质必须看候选帧/回放，不能自动宣称通过。

## 三种静帧

- Concept Still：独立设计图，不能作为实现证据。
- Timeline Still：真实 await seek(t) 截图，有源/资源/时间/截图哈希。
- Rendered Frame：从正式 MP4 解码，记录视频哈希、帧号和 PTS。

概念可早期审批；Gate 3 必须增加真实时间轴短动画和回放。正式输出还要提取 Rendered Frame，核对运动模糊、编码、音画。不能用独立 drawStill 代替。

## 环境恢复

doctor 检查可执行路径/权限、ldd、字体清单、系统、实际最小截图。浏览器优先 Playwright Chromium，可设置 `UI_MORPH_BROWSER`；备用系统 Chromium。兼容重试仅 `--disable-dev-shm-usage --disable-gpu`，沙箱始终开启。
日志出现 DBus 不代表失败，以启动/截图结果判断。可执行缺失→安装 Chromium；库缺失→授权安装系统依赖；权限/user namespace→请求获准 runner；字体问题→加载实际字体并复测。不要默认 --no-sandbox，不绕过宿主限制。失败报告 BLOCKED，保留错误与建议。CLI 由独立进程监督，默认短命令 60 秒、scan/repair/beats 600 秒，driver 挂起也能保存超时报告；可用 `UI_MORPH_QA_TIMEOUT` 明确调整预算。仅生成 HTML 不算浏览器通过。

## 资源预检

assets.json：`{"assets":[{"file":"assets/font.woff2","type":"font","source":"具体来源","license":"具体授权及本地许可文件"}]}`。
类型 image/font/video/audio/script/style/document；图片可填 minDimensions。字体通过 Chromium FontFace 解码；音视频完整解码；缺失资源 BLOCKED，解码失败 FAIL，未知授权 NEEDS_REVIEW。
项目目录内相对路径离线可用，禁止远程依赖和越界。大字体建议先审查许可与 reserved names，再用可选 fontTools：
`pyftsubset input.ttf --text-file=all-copy.txt --output-file=assets/subset.woff2 --flavor=woff2`。
收集所有动态文案及符号，保留版权/许可，检查缺字；不要默认完整 CJK Base64。资源变化后重新预览。FontTools 未安装时不强制自动安装或改写字体。

## 局部修复

Render → Inspect → Diagnose → Patch → Re-render → Verify：
1. 从 report 的时间/对象/属性定位；打开异常前后至少 2 帧，检查轮廓、布局、clip、z、镜头和状态边界。
2. 记录假设、涉及代码与最小补丁（如共享边界锚点，而非重写全片）。
3. 保留 before 报告/原帧；修改后运行：
`motion_qa.py repair scene.html --config qa-config.json --before qa/full/report.json --start 1.3 --end 1.8 --out qa/repair-after`。
4. 同一源路径重新渲染，检查修改区与上下游边界；再完整 scan、预览/渲染刷新凭据。
5. repair 只生成对比证据，不自动修改代码、不按候选数量下降就通过。不能用降帧、删除动作、淡入淡出或隐藏异常替代修复。
