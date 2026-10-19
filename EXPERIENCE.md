# Polymarket Arb 项目实战经验

完整实验时间：2026-05-28 to 2026-05-30

## 起点

- 钱包 $97.61 → 峰值 $174 → 现 ~$67 (因 arb 实盘半腿亏损)
- 跟单 ce25 + eebde 两个 BTC 5m/15m whale
- 4 个并行 sim：v8 mirror、HTTP scanner、WS observer、paper executor

## 关键验证结论

### ✅ 已确认可行
1. **Polymarket fee = 0%** in 2026（实测，不是 7%）
2. **PH 区域可下单**（Polymarket 不禁菲律宾，但禁美国）
3. **polymarket-client SDK** > py_clob_client（避免 order_version_mismatch）
4. **WS 检测 26 tradable/hr**，paper 模拟 96.8% WR / +$0.35/pair

### ❌ 已确认不可行
1. **单边跟 ce25/eebde** → -7~-16% ROI（whale 是 MM-arb 对冲者，不是 directional）
2. **HTTP 轮询** → 99% 时间 sum > 1.00（HFT 吃光）
3. **多 leader 投票** → Crisp-Elderberry 等 WR 50% → 40% 衰退
4. **chop 阈值过滤** → backtest 反驳，越紧反而越亏
5. **PH 直接做 arb** → 100% 半腿，real 亏损

### ⚠️ 未验证但可能
1. **加拿大 AWS ca-central-1** → 可能 30-50% 半腿率（仍未理想）
2. **US colo** → <5% 半腿，但成本 $1000+/月
3. **swisstony 类 longshot** → 4933 笔历史已有

## 数据驱动的关键发现

### eebde (Bonereaper) 真实性能
```
2806 MM-arb pairs / 8 天
1613 wins (57.5%)
1193 losses (42.5%)
Net +$50,828 / ROI 0.87%
最大单笔亏: -$5,116 (sum_avg 1.583，单边追势失败)

最赚的是 sum_avg > 1.05 (违反 arb 数学) — 因为它实际是
"有方向 alpha 的趋势赌徒"，不是纯 arb
```

### 我们的 WS 数据
```
138 tradable / 5.2h = 26.5/hr
78% 可执行 (ttl >= 60s)
持续时间 median 77s
按资产: SOL/ETH/XRP 各 ~30, BTC 仅 11 (HFT 抢光)
```

### PH 半腿问题完整诊断

**实测**: 100% 半腿率 = 5 笔尝试，5 笔 Up 单边裸露

**原因**：
```
T0:        我们 batch post_orders 同时发
T0+250ms:  到 PM 撮合
T0+253ms:  Up matched (taker 速度)
T0+253ms:  market 广播 Up matched
T0+256ms:  其他 MM 调整 Dn ask 向上
T0+260ms:  我们 Dn limit @ ask+2c 已 stale
T0+5s:     check_fills 发现 Dn 没填
T0+5s:     cancel Dn + emergency hedge @ ask+10c
T0+5s+250ms: 但 Dn ask 已 jump 比 +10c 还高
T0+8s:     hedge 也 cancel → SINGLE Up 留下
```

**架构无解**：在 PH 250ms 延迟下，paper 的双腿假设不可能复刻

### 余额追踪
```
$76.51 → $67.12 (今天净 -$9.39)
分解:
  eth-15m 双腿 (cost $5.17): 双腿都成交 → Down 赢 → 应 +$0.03 但 redeem 延迟
  xrp-5m 半腿 × 3 (cost $6.15): 全 Up 单边
  之后 Up 输 → -$6 直接损失
```

## 验证过的策略 vs Paper 数据

| 策略 | 起 | 终 | ROI | 时长 |
|---|---|---|---|---|
| v8 mirror (eebde) | $76 | $76 | 0% | 10.4h |
| HTTP arb scanner | obs only | 3 tradable / 9.9h | - | - |
| **WS paper executor** | $76 | **$92.38** | **+8.58%** | 1h |
| **WS real executor** | $76.51 | $67 | **-9.39%** | 1h |

**核心矛盾**：Paper 8.58% / 1h vs Real -12% / 1h

## 设备投资 ROI 估算

| 配置 | 月成本 | 估半腿率 | 估日 PnL | 月净 |
|---|---|---|---|---|
| PH 直跑 | $0 | 100% | -$10 | -$300 |
| **AWS ca-central-1** | **$8** | **30-50%** | **$0-15** | **-$8 to +$450** |
| AWS us-east-1 | $8 | 不能下单 | N/A | N/A |
| US colo + 直连 | $1000+ | <5% | $100+ | +$2000+ |
| 资金量 $1000+ | - | 同上 | x5 倍 | x5 倍 |

## 重要 SDK 细节

### polymarket-client (推荐用此)
```python
from polymarket import SecureClient
client = SecureClient.create(private_key=PK, wallet=PROXY)

# Balance (raw 6-decimal!)
bal = client.get_balance_allowance(asset_type="COLLATERAL")
usdc = float(bal.balance) / 1e6  # 必须除！

# Limit order (返回 AcceptedOrder 或 RejectedOrder)
res = client.place_limit_order(token_id="...", price=0.50, size=5, side="BUY")
order_id = getattr(res, "order_id", None)  # None = rejected

# Batch (一次发多个)
signed = client.create_limit_order(...)  # 只签名
results = client.post_orders([signed1, signed2])  # 批量发

# Cancel
client.cancel_order(order_id="...")

# Get order status
o = client.get_order(order_id="...")
# o.status: 'live' (未成交), 'matched' (已成交), ...
```

### py_clob_client (老 SDK)
- 出现 `order_version_mismatch` 错误，避免使用

### Balance 单位陷阱
```
get_balance_allowance().balance = 71343209 (raw)
真实 USDC = 71343209 / 1e6 = $71.34
```

## 已知技术问题

### 1. WS 频繁断线
```
Polymarket WS 每 1-3 min 无 close frame 即断
需要 reconnect 逻辑 + 重新 subscribe
我们的 ping_interval=10 帮助但不解决
```

### 2. 异步并发限制
```
asyncio.create_task() 每次 book_update 触发 → 任务堆积
正确做法: 同步 detect + 异步只用于 check_fills
```

### 3. log() 不完全可靠
```
print + 文件 write 双路径
print() 与 redirected stdout 在高频时丢消息
建议: 只用一种 IO 路径
```

### 4. neg_risk 标志
```
gamma /events 的 negRisk 不准确
应查 https://clob.polymarket.com/neg-risk?token_id=...
但新 SDK (polymarket-client) 不需要传 neg_risk
```

## 数据库 / 历史 dump 中的关键文件

```
ce25_history_7d.jsonl   - 143k events / 7天
eebde_history_7d.jsonl  - 303k events / 7天
ws_arb_detections.jsonl - WS 检测的 138+ tradable arb
arb_opportunities.jsonl - HTTP scanner 对照数据
ws_paper_state.json     - paper executor 完整状态
v8_mirror_state.json    - v8 sim 状态
```

## 重要的 backtest 脚本

```
backtest_mirror_vs_single.py  # 验证 mirror 不如单边
backtest_chop_threshold.py    # 验证 chop 阈值无效
_dbg_eebde_arb_losses.py      # 揭示 eebde 42.5% 亏损率
_dbg_voting_v2.py             # 多 leader 投票回测
```

## 下一步建议（按优先级）

### 立即可做
1. **关 PH real exec** 止血 (现已停)
2. **paper 继续跑通宵** 收完整 24h tradable 分布
3. **租 AWS ca-central-1 t3.micro** $8/月

### 部署 CA 后第一周
1. 跑 ws_real_executor.py 一周
2. 监控:
   - 半腿率 < 50%
   - 日 PnL > $0
3. 7 天 net 正 → 加资金到 $200
4. 7 天 net 负 → arb 路线放弃，转 swisstony 模式

### 如果 CA 也不行
1. 接受 arb 不可行
2. 转：
   - **swisstony longshot 模仿** (10c 入，等大波动)
   - **directional whale 跟单** (找 60%+ WR 真鲸鱼)
   - **手动操盘** (大事件期间)

## 失败的经验 (避免重蹈)

1. ❌ **不要相信 paper 数据 = real 数据**
   - paper 假设 0 延迟、0 半腿、100% fill
   - real 全部反过来

2. ❌ **不要在低延迟环境下做高频 arb**
   - PH 250ms RTT → 100% 半腿 → 必亏

3. ❌ **不要单边跟 MM-arb 鲸鱼**
   - 它们对冲，单边复制 = 50% 翻硬币

4. ❌ **不要忽视 SDK 版本细节**
   - py_clob_client 0.34.6 仍有 order_version 错
   - polymarket-client 是新版

5. ❌ **不要过拟合到历史样本**
   - 加 filter "解释" 已发生的亏损 → 过拟合
   - 真实测试才知道 filter 在 OOS 有没有效

## 部署人员注意

如果接手项目部署到 CA：

1. **不要再写 paper 验证！** 已经验证过 lab 数据
2. **直接修复 real exec 配置** 跑 24-48h 观察实际半腿率
3. **如果 CA 半腿率 > 50%** → 立刻停，节省资金
4. **如果 CA 半腿率 < 30%** → 加资金到 $500+

## 用户偏好（来自 CLAUDE.md + 实战）

- 用户接受 paper 验证不等于 real 验证
- 预算 ~$76-100 真钱
- 已购 AWS US 服务器（但 PM 禁 US 下单）
- 偏好快速迭代 + 数据驱动决策
- 已多次反复修正过分乐观的策略推荐
