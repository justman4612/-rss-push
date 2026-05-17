# RSS 源配置
SOURCES = {
    "BBC": [
        # BBC 各频道 RSS（GitHub Actions 美国 IP 可直连）
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "https://feeds.bbci.co.uk/news/rss.xml",
    ],
    "CNN": [
        # CNN 各频道 RSS
        "http://rss.cnn.com/rss/cnn_topstories.rss",
        "http://rss.cnn.com/rss/cnn_world.rss",
        "http://rss.cnn.com/rss/cnn_tech.rss",
        "http://rss.cnn.com/rss/money_latest.rss",
        "http://rss.cnn.com/rss/cnn_allpolitics.rss",
    ],
    "NHK": [
        # NHK World 英文版，日本视角
        "https://www3.nhk.or.jp/nhkworld/en/news/feed.xml",
    ],
    "JapanTimes": [
        # 日本时报英文版
        "https://www.japantimes.co.jp/feed/",
    ],
}

# 每个源最多取多少条（从 RSS 中取前 N 条，再在其中做关键词过滤）
MAX_PER_SOURCE = 15

# 关键词（命中标题或摘要才推送，不区分大小写）
# NHK/JapanTimes 提供日本视角，BBC/CNN 提供西方视角
KEYWORDS = [
    # === AI & 科技 ===
    "artificial intelligence", "machine learning", "deep learning",
    "ChatGPT", "OpenAI", "DeepSeek", "large language model", "LLM",
    "Nvidia", "GPU", "semiconductor", "chip",
    "AI", "robot", "autonomous",
    "人工智能", "大模型", "芯片", "半导体", "英伟达", "机器人",

    # === 全球经济 ===
    "Fed", "Federal Reserve", "ECB", "inflation", "interest rate",
    "recession", "stock market", "Wall Street", "Nasdaq", "S&P 500",
    "oil price", "OPEC", "supply chain", "trade deficit",
    "央行", "通胀", "加息", "降息", "衰退", "股市", "油价", "供应链",

    # === 新能源 & 气候 ===
    "climate", "renewable", "solar", "wind power", "electric vehicle",
    "Tesla", "BYD", "battery", "carbon",
    "新能源", "电动车", "电池", "碳中和", "太阳能",

    # === 互联网 & 商业 ===
    "Apple", "Google", "Microsoft", "Amazon", "Meta",
    "startup", "venture capital", "IPO",
    "华为", "小米", "腾讯", "字节", "阿里", "创业", "融资",

    # === 深度报道 ===
    "analysis", "in-depth", "investigation", "explainer",
    "深度", "分析", "调查", "解读",
]

# 敏感词跳过清单（标题命中则不推送，避免企业微信审核）
# 只匹配标题，不匹配正文，防止误杀
SKIP_KEYWORDS = [
    # 涉政敏感
    "Tibet", "Xinjiang", "Uyghur", "Tiananmen",
    "Falun Gong", "Hong Kong independence",
    "Taiwan independence", "Taiwan.*sovereignty",
    # 领导人负面
    "Xi Jinping.*critic", "dictator",
    # 军事冲突
    "war.*China", "invasion.*Taiwan", "PLA.*attack",
]

# 全文字数上限（超过则截断，避免单条消息超企业微信 4096 字节限制）
FULL_TEXT_MAX_CHARS = 1200

# Webhook URL 从环境变量读取，不写死在代码里
# export WECHAT_WEBHOOK_URL="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
