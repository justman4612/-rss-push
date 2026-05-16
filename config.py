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
    "联合早报": [
        # 联合早报官方 RSS 已关，用 RSSHub 抓取
        "https://rsshub.app/zaobao/znews/china",
        "https://rsshub.app/zaobao/znews/world",
        "https://rsshub.app/zaobao/realtime/china",
        "https://rsshub.app/zaobao/realtime/world",
    ],
}

# 每个源最多取多少条（从 RSS 中取前 N 条，再在其中做关键词过滤）
MAX_PER_SOURCE = 15

# 关键词（中英文双语，命中标题或摘要才推送）
# 不区分大小写
KEYWORDS = [
    # === 中美关系 ===
    "US-China", "China-US", "Sino-US", "trade war", "tariff", "sanctions",
    "decoupling", "Biden.*China", "Trump.*China", "Congress.*China",
    "Blinken", "Yellen", "Taiwan", "Taiwan Strait", "South China Sea",
    "南海", "台海", "台湾海峡",
    "中美", "贸易战", "关税", "制裁", "脱钩",

    # === 中国深度报道 ===
    "China", "Beijing", "Chinese", "Xi Jinping",
    "Belt and Road", "Made in China", "CCP",
    "中国", "北京", "习近平", "一带一路",

    # === AI 相关 ===
    "artificial intelligence", "machine learning", "deep learning",
    "ChatGPT", "OpenAI", "DeepSeek", "large language model", "LLM",
    "Nvidia", "GPU", "semiconductor", "chip",
    "AI", "artificial",
    "人工智能", "大模型", "深度求索", "芯片", "半导体", "英伟达",

    # === 中国经济 ===
    "China.*economy", "China.*GDP", "Chinese economy", "Yuan", "RMB",
    "A-share", "Hang Seng", "real estate.*China", "Evergrande",
    "PBOC", "People's Bank", "China.*export", "China.*import",
    "中国经济", "人民币", "A股", "港股", "房地产", "央行", "出口", "进口",

    # === 中国官员 ===
    "Chinese official", "foreign ministry", "Politburo",
    "Chinese foreign minister", "Chinese premier", "Chinese president",
    "Wang Yi", "Qin Gang", "Li Qiang", "Ding Xuexiang",
    "外交部", "政治局", "国务院", "王毅", "李强",

    # === 深度报道/分析 ===
    "analysis", "in-depth", "explainer", "feature", "investigation",
    "opinion", "commentary", "editorial", "long read",
    "深度", "分析", "评论", "调查", "特写", "解读",
]

# 全文字数上限（超过则截断，避免单条消息超企业微信 4096 字节限制）
FULL_TEXT_MAX_CHARS = 1000

# Webhook URL 从环境变量读取，不写死在代码里
# export WECHAT_WEBHOOK_URL="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
