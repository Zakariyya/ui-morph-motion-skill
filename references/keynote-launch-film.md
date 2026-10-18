# 54 拍品牌发布片：升级参考案例

来源：用户提供的案例提示词。用途：为 UI Morph Motion 后续升级和同类创作提供参考；不是已经实现或验收的成片。

## 使用边界与升级切入点

- 保留下面的英文原文作为创作规格。只有用户要求制作此类影片时才执行其中的 `<start>`；补充、整理或维护 skill 时不索要品牌和素材。
- 该案例为 120 BPM、54 拍，即 27 秒，60 fps 对应 1620 个输出帧。不要套用可选的 28 拍示例节拍表。具体 drop、breakdown 和 beat return 的位置须用选定歌曲试听、测量后编排，不能仅凭 BPM 推断；不合适的音轨需换选或明确调整分镜。
- 制作前收齐缺失输入，展示节拍表与 open、glass、stage、wall 四张静帧，再确认分镜。独立设计图标 Concept Still；Visual Proof 另需从真实 seek 时间轴生成 Timeline Still 和短动画。素材额外依赖包括配准的白天/金色时刻照片对；在素材核对阶段识别，不等做到 slider 才发现缺失。
- 参考价值：为相邻场景记录同一形状如何变成下一形状；单独安排内容遮罩、光标操作、镜头与音乐锚点。采用本案例时，禁止 crossfade、blur-in 和 3D 翻转，覆盖通用制作建议中的短暂模糊或可能产生 3D 效果的拖动倾斜。玻璃滤镜与 goo 内部模糊不是模糊入场转场。
- 技术升级候选：背景克隆折射、字形距离场、六叶 iris、字标压缩、视频异步 seek、逐帧突变检查。下面的实现方案与 Chromium/http.server 注意事项均来自案例，尚未在本仓验证；实际采用时先做最小技术样片，不把它们当成现有脚本已支持的能力或所有环境的确定结论。
- 使用实际素材时逐项核验曲目、音效、照片、视频和字体许可；原文中的平台名称和 “free for commercial use” 不是具体素材的授权证明。该案例要求下载音效，不能套用通用流程中的原创合成音效替代。
- `seek(t)` 可以异步等待视频解码，但同一时间必须得到同一画面。所有采样须等待完成并串行操作同一视频元素，检查乱序 seek 的结果。单 HTML 的交付需明确是否内嵌媒体，不能把依赖外部文件的 HTML 称作自包含。
- “Last frame = first frame” 表示循环端点的设计目标；仍按 `[0,T)` 导出，不添加重复终帧，并检查接缝运动与音频。逐帧差分超过相邻值 3 倍仅作为人工复核候选，不能单独判定所有闪帧或证明没有闪帧。

## 原始提示词

```text
<inputs>
Ask me for: a one-word brand name for the wordmark (a verb works best), 9 to 12 high-res photos, a royalty-free song around 120 BPM with a drop and a quiet breakdown (Mixkit, free for commercial use), and a free stock clip of a plain wall with moving plant shadows (Pexels).
</inputs>

<direction>
An Apple-keynote launch film, 2D only, one continuous take. Every scene is made out of the previous one: nothing fades, blurs or cuts. Objects change shape instead: text rises out of a mask line, icons pop from zero on a spring, bars draw across, pages push, and a black shape floods the whole frame and contracts into the next scene. Warm off-white canvas, black UI, iOS 26 liquid glass over the photos. Archivo (wdth 125, weight 800) for the wordmark, Geist for UI. A cursor drives every change with real clicks, drags and long-presses. The camera zooms screen-studio style so each moment fills the square, and the cursor scales with it.
Banned: crossfades, blur-ins, brightness "developing", 3D flips, particles, glows, holds longer than 1s, anything that looks like a template.
</direction>

<structure>
120 BPM, 54 beats, something happens on every beat.
Open: the wordmark squeezes into its own period like an accordion, the dot grows into a black pill, a label rises inside it. Click: six iris blades close over the label and snap open onto a photo. The circle becomes a square, shrinks, the grid unfolds from behind it like a paper map (center, plus, corners), reflows into a bento, and a click zooms into one tile, landing exactly on the drop.
Glass: a glass word pops in letter by letter, melts into a droplet that stretches into a glass toolbar. The adjust icon turns it into a slider. Dragging relights the photo from day to golden hour (two aligned shots), and the knob turns into a glass lens while held. It lifts into a glass orb, the next photo opens inside it as a circle, and the orb expands into a lock screen: glass clock digits, date, and a home bar that stretches into a glass music player.
Stage: the lock screen pulls back into a phone (the bezel grows out of the screen edge). The Dynamic Island stretches like liquid, pinches off, flies over and grows into a Mac window that rolls up like a blind. Long-press the wallpaper, drag it onto a Safari tab, the page pushes in, drop it and it becomes the hero of a landing page. Scroll: the hero morphs into a framed print on a product card, with the mat and molding growing out of the photo's edge. Pick a frame color (it paints across) and a size, then the nav button flies down into "Order print".
Order: one black shape keeps morphing: Ordered ✓ → Printing % → On its way (a van on a route) → Delivered ✓.
Wall: the delivered circle floods the frame edge to edge, holds black for a beat, and contracts into the framed print hanging on the real wall footage. The same iris opens onto the print, closes again, the frame floods the screen and contracts into the pill → the dot → the letters spring back out, landing on the beat return. Last frame = first frame.
</structure>

<build>
1. One HTML file, square 1440x1440. Every style is computed from time inside an async seek(t): no CSS transitions, no timers, no state between frames.
2. Springs are closed-form step responses. A value with many targets is the sum of one spring per change, so it stays a pure function of time.
3. Liquid glass: each glass element holds its own clone of the scene behind it, filtered with an SVG feImage displacement map (a rounded-rect distance field) through three feDisplacementMaps at slightly different scales for chromatic edges, plus a rim light. Glass letters: a canvas distance field per glyph gives the map, mask and highlights.
4. Goo: blur + alpha threshold, then composite the source atop it so the glass stays sharp inside.
5. Iris: 6 blades around a hexagonal aperture. Each blade is its two vertices, both edge extensions and the SHORT arc between them.
6. Wordmark squeeze: every letter moves toward the dot by the same factor and its drawn width follows (narrow the wdth axis, scale the rest), so the letters stay touching.
7. Footage: re-encode all-intra (ffmpeg -g 1), load it as a blob URL, await 'seeked' before drawing each frame.
8. Sound: a downloaded SFX for every event (Mixkit), never synthesized, each placed by its measured peak. The song starts on a downbeat: the zoom lands on the drop, the wall sits in the breakdown, the wordmark returns with the beat. Loudnorm to -14 LUFS.
9. Render with Playwright: 4 subframes per frame blended with ffmpeg tmix, 60fps. Check one frame per beat, then scan for single-frame pops (frame-difference spikes 3x their neighbours).
</build>

<gotchas>
backdrop-filter: url() misreads displacement maps in Chromium, so clone the scene instead. A flood must overscale past the corners and take about 0.3s, or half the screen changes in one frame. A child with visibility: visible shows through a hidden parent, so use inherit. Text that swaps inside a morphing shape needs its own mask. python http.server can't range-seek video, so use the blob URL.
</gotchas>

<start>
Ask me for the inputs, then show me the beat map and 4 stills (open, glass, stage, wall) before you write the full film.
</start>
```
