# IM Bot 控制空调

## 关联
- idea 版本：实验性想法 v0.1
- 目标：通过 IM Bot 控制家里的空调

## 核心流程

```
用户发送 IM 消息
    ↓
IM Platform → Webhook
    ↓
pataphaw-jr 服务（解析意图）
    ↓
HomeAssistant API（控制空调）
    ↓
空调响应指令
```

## 关键决策

### IM 平台选择

| 平台 | 优点 | 缺点 |
|------|------|------|
| Telegram | API 开放、Bot 完善 | 需科学上网 |
| 飞书 | API 丰富、国内可用 | 需注册企业 |
| 企业微信 | 国内常用 | API 限制多 |
| 钉钉 | 国内常用 | Bot 能力有限 |

### 架构设计

- pataphaw-jr 作为中转服务
- IM Platform → Webhook → pataphaw-jr → HomeAssistant
- 大模型用于意图解析（可选，先做规则匹配）

### 空调控制能力

已验证可在 HomeAssistant 中控制的主卧空调：
- `climate.lumi_mcn02_d56f_air_conditioner`
- 支持：开关、模式切换、温度调节、风速调节

## 实施步骤

### Phase 1：确认 IM 平台
选择并配置一个 IM Bot，获取 Webhook URL。

### Phase 2：搭建中转服务
pataphaw-jr 接收 IM Webhook，解析指令并调用 HomeAssistant。

### Phase 3：端到端验证
通过 IM 发送消息控制空调开关。

## 待确认项

- [ ] 使用哪个 IM 平台？
- [ ] 是否需要大模型解析自然语言指令？

---

## 已验证能力

HomeAssistant 空调控制（已验证）：
- entity_id: `climate.lumi_mcn02_d56f_air_conditioner`
- 服务调用成功，可开关空调、调节模式/温度

**下一步**：先实现 pataphaw-jr 的 HomeAssistant 空调控制能力，IM 接入后续补充。
