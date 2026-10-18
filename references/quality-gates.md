# Evidence-based quality gates

每个 Gate 四态：PASS=证据满足条件；FAIL=明确不满足；BLOCKED=环境/依赖/素材不能执行；NEEDS_REVIEW=程序不能判断，等待实际复核。脚本自动检查通过只代表检查项，不代表审美或许可通过。

| Gate | 必要证据 | 继续条件 |
|---|---|---|
| 1 Preflight | 项目事实、资源清单/许可、资源解码报告、browser doctor 截图 | 缺失补齐；实际资源与环境成功，许可/事实复核 |
| 2 Motion Blueprint | 已批准分镜/声音方案、对象契约、轨迹/镜头/阅读窗口、技术试验方案 | 创意审批记录绑定当前材料 |
| 3 Visual Proof | 核心连续形变短动画、Timeline Stills、QA 报告、真实浏览器回放记录 | 关键失败清零，候选逐项检查；不能拿概念图放行 |
| 4 Full Production | 全时间轴、素材/音频、镜头实现、完整产物清单 | 与分镜一致，输出可复现 |
| 5 Verification | 完整 scan、编码/解码报告、Rendered Frames、播放器/音画复核、需要时两轮循环 | 证据绑定当前版本，无未解决关键项 |

工具不会凭“写了代码”“HTML 能打开”自动放行。人类复核可以处理 NEEDS_REVIEW，不得覆盖 FAIL/BLOCKED；修复后重跑产生新证据。新素材/源代码/声音/编码变化使相关旧凭据失效。

`motion_qa.py gate gates.json --out qa/gates` 校验文件哈希、源哈希、按顺序评估。空证据不会 PASS；前级未通过则后级 BLOCKED。gate 文件示意：

```json
{"gates":[{"number":1,"name":"Preflight","evidence":[
 {"file":"environment/report.json","sha256":"实际SHA256","type":"report","role":"environment"},
 {"file":"assets/report.json","sha256":"实际SHA256","type":"report","role":"assets"},
 {"file":"facts.md","sha256":"实际SHA256","type":"document","role":"facts"}
],"review":{"file":"preflight-review.json","sha256":"实际SHA256"}}]}
```

review 文件：`{"reviewer":"实际复核者","decision":"PASS","evidence":{"environment/report.json":"实际SHA256",...},"notes":"具体看过什么，创意批准/许可与未解决项"}`。
工具只能验证记录与绑定，不能认证姓名真实性；Agent 不得编造用户审批/人工试听记录。只有真实复核后填写。Gate 2 review 记录用户对创意/声音方案的批准。

必需 evidence role：Gate 1 environment/assets/facts；Gate 2 blueprint/continuity；Gate 3 timeline/qa/playback；Gate 4 production；Gate 5 qa/encoded/playback。role 是材料责任声明，仍须读内容；单一截图的 capture PASS 不能当成 Visual Proof。

定向修复期间 Gate 3/5 回到待验证。保留 before/after、异常时间与对象、根因、最小补丁、重渲染区间和受影响边界。最后再跑完整检查，而不是只证明一张修复截图漂亮。
