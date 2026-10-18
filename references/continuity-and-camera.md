# Object Continuity Contract 与确定性镜头

先为重要对象建表：`id / interval / from / to / bounds / anchor / path / clip / z / children / visible / ownership`。
`from/to` 包括位置、尺寸、轮廓控制点、颜色与内容状态；锚点使用对象局部坐标并声明世界/屏幕空间。
每个转场明确：哪一段轮廓延续，哪个子元素重排，旧内容何时退出，新内容何时接入，最小可见面积/最长空窗是多少。

默认同一身份的边界、位置、形态及轨迹连续。尺寸相近的新元素替换旧元素、遮罩遮掉断点或短暂空白，不构成连续形变。
允许多根对象：合并记录来源 IDs→目标 ID、公共接触边界；分裂记录父 ID→子 IDs、分裂点和轮廓归属；复杂交接声明出让/接收对象及重叠区间。不能暗中换成淡入淡出。
路径变换需匹配轮廓点序、方向和闭合规则；圆角、宽高、遮罩有效范围在最大过冲时仍成立。
缩小外壳时同步重排、缩放或裁切内容，不能保留大布局挤入小壳体。底色应在完整边界上统一插值；区域填色只有创意明确要求“扫色”时才使用。

## 单一真实时间轴

`await seek(t)` 从任意时间独立计算状态，再绘制；缓存已解码图片、字体、固定离屏图，禁止跨帧积分、累加 transform、依赖调用顺序。
`window.ready` 完成资源准备；视频 seek 等待解码完成。相同时间+源文件+资源应产生相同像素；QA 会乱序复测。
闭式弹簧使用 motion.js 原有 `release / step / track`；同一属性多目标响应叠加，变化时间按升序排列。
`Motion.path(t, keys)` 为 cubic Hermite：每个 key 为 `{t,x,y,vx?,vy?}`，速度单位 px/s，默认端点速度为零。共享 key 保证段内 C1 连续；首尾夹持，外部衔接时端点速度应为零或继续同一轨迹。
不要把“禁止状态历史”误解为每帧加载字体/图片。

## Camera Rig（可选）

```js
const camera = Motion.camera(t, {
  x: t => Motion.track(t, 0, [{t:1.1,value:80}],20,.85),
  y: 0, zoom: t => 1 + .15*Motion.smooth((t-1.2)/.4),
  anchor: {x:width/2,y:height/2},
  follow: t => subjectCenter(t), lag:.08
});
ctx.setTransform(...Motion.cameraMatrix(camera)); // 世界→屏幕
// 在场景变换之下应用对象局部变换，然后画对象。
const cursor = Motion.toScreen(worldHitPoint, camera);
ctx.setTransform(1,0,0,1,0,0); // 屏幕空间光标，尺寸恒定
// 如设计要求光标跟随镜头变大，显式乘 camera.zoom。
```

四层分离：对象局部变形 → 场景排布变换 → 摄像机变换 → 屏幕光标/字幕。镜头映射：`screen = anchor + (world-cameraPosition)*zoom`；`toWorld` 为逆映射。
跟随是纯函数的时间错位采样，不是依赖前帧的平滑积分；主体函数要定义负时间（通常夹持首帧）。平移/缩放曲线可分别传函数，主体事件与镜头事件可错时。
DOM 可使用 `matrix(...Motion.cameraMatrix(camera))`，transform-origin=0 0，主体另用子节点；不能直接缩放整个页面冒充镜头设计。

`motionQA()` 中返回实际应用的 camera/matrix 和同源对象几何；数值声明无法独自证明镜头落地，必须核对画面与变换代码。光标命中使用变换后的锚点；拖拽目标与光标来自同一函数。
