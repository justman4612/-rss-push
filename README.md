# rss-push 📰

自动抓取英文媒体 RSS → 关键词过滤 → 去重 → 翻译 → 推送到企业微信。

每天早上 8 点（北京时间）自动运行，把值得看的国际新闻摘要和全文推到企业微信群里。部署在 GitHub Actions 上，**不需要自己的服务器**。

## 它做什么

- 抓取 BBC / CNN / 日本时报的 RSS 源
- 按关键词过滤出 AI、经济、新能源、互联网等领域的内容
- 敏感内容双语（中英）检测并跳过，避免企业微信审核问题
- 标题 + 摘要英译中
- 跨天去重，7 天内推过的不再重复推
- 先发一条「今日新闻速览」摘要，再逐篇发全文

## 工作流程

```
RSS 源 (BBC/CNN/JapanTimes)
   │
   ▼
feedparser 解析条目
   │
   ▼
关键词匹配（标题或摘要命中才保留）
   │
   ▼
敏感词检测（英文原文 + 中译后二次检测）
   │
   ▼
去重（同次标题去重 + 跨天 7 天窗口）
   │
   ▼
deep-translator 英译中
   │
   ▼
企业微信 Webhook
   ├── 摘要消息（自动截断，不超 4096 字节）
   └── 逐篇全文消息
```

## 仓库结构

```
├── main.py              主流程
├── config.py            RSS 源、关键词表、敏感词表
├── dedup.py             MD5 去重 + 推送记录持久化
├── translate.py         英译中封装
├── test_push.py         测试（未纳入 git）
├── requirements.txt     依赖
└── .github/workflows/
    └── daily.yml        定时任务
```

## 核心机制

**关键词过滤**：短关键词（≤3 字符）加词边界匹配，避免 `AI` 误命中 `again` / `rain` 这类词。

**去重**：以 `来源 + 标题` 的 MD5 作为唯一键，推送记录存入 `pushed.json`，保留 7 天。通过 GitHub Actions 的 cache 在每次运行间持久化。

**敏感词检测**：分英文原文检测和中译后中文检测两轮，只匹配标题和摘要，防止误杀正文。

**消息长度**：企业微信单条消息上限 4096 字节。摘要消息会逐篇尝试拼接，超长自动截断并标注「部分未列」；单篇全文超过 1200 字截断。

## 部署

Fork 本仓库后：

1. 在企业微信群里添加机器人，拿到 Webhook URL
2. 在仓库 Settings → Secrets 里添加 `WECHAT_WEBHOOK_URL`，值为该 URL
3. 默认每天 UTC 0:00（北京时间 8:00）自动运行，也可在 Actions 页面手动触发

## 本地运行

```bash
pip install -r requirements.txt

# 离线模拟，用 mock 数据验证关键词匹配和消息组装（不需要 webhook）
python main.py --dry-run

# 实际运行（需要设置环境变量）
export WECHAT_WEBHOOK_URL="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key"
python main.py
```

## 配置说明

编辑 `config.py`：

| 配置项 | 说明 |
|---|---|
| `SOURCES` | RSS 源地址，按媒体分组 |
| `MAX_PER_SOURCE` | 每个源最多取多少条 |
| `KEYWORDS` | 命中标题或摘要才推送 |
| `SKIP_KEYWORDS_EN` / `SKIP_KEYWORDS_CN` | 敏感词，命中标题则跳过 |
| `FULL_TEXT_MAX_CHARS` | 单篇全文截断长度 |

## 注意事项

- Webhook URL 是敏感信息，走环境变量 / Secrets，不要写进代码
- `pushed.json` 是去重状态文件，已加入 `.gitignore`，本地运行会自动生成
- 定时任务由 GitHub Actions 调度，高峰期可能有几分钟到十几分钟的延迟

## 依赖

- `feedparser` RSS 解析
- `requests` HTTP 请求
- `beautifulsoup4` 正文提取
- `deep-translator` 英译中
