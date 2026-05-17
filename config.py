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
    "JapanTimes": [
        # 日本时报英文版
        "https://www.japantimes.co.jp/feed/",
    ],
}

# 每个源最多取多少条（从 RSS 中取前 N 条，再在其中做关键词过滤）
MAX_PER_SOURCE = 15

# 仅 JapanTimes 源生效的中国关键词——日本视角温和，不触雷
KEYWORDS_SAFE_CHINA = [
    "China", "Chinese", "Beijing", "Shanghai", "Guangdong",
    "中国", "北京", "上海", "广东", "深圳",
]

# 关键词（命中标题或摘要才推送，不区分大小写）
# NHK/JapanTimes 提供日本视角，BBC/CNN 提供西方视角
KEYWORDS = [
    # === AI & 科技 ===
    "artificial intelligence", "machine learning", "deep learning",
    "ChatGPT", "OpenAI", "DeepSeek", "large language model", "LLM",
    "Nvidia", "GPU", "semiconductor", "chip",
    "AI", "robot", "autonomous",
    "tech", "technology", "digital", "software", "cyber",
    "人工智能", "大模型", "芯片", "半导体", "英伟达", "机器人", "科技",

    # === 全球经济 ===
    "economy", "economic", "inflation", "bank", "market", "dollar",
    "Fed", "interest rate", "recession", "Wall Street", "Nasdaq",
    "oil", "energy", "supply chain", "trade",
    "economic growth", "budget",
    "经济", "通胀", "加息", "降息", "衰退", "股市", "油价", "贸易",
    "央行", "利率", "汇率", "供应链",
    # 中国经济（数据面，避负面叙事）
    "China GDP", "China.*trade", "PBOC", "Chinese consumer",
    "China.*economy", "China.*tech", "China.*business",
    "China.*market", "China.*energy",
    "人民币", "进出口", "消费",

    # === 新能源 & 气候 ===
    "climate", "renewable", "solar", "wind", "electric vehicle",
    "Tesla", "battery", "carbon", "green", "environment",
    "新能源", "电动车", "电池", "碳中和", "太阳能", "环保",

    # === 互联网 & 商业 ===
    "Apple", "Google", "Microsoft", "Amazon", "Meta",
    "startup", "venture capital", "IPO",
    "business", "industry", "company", "billion",
    "华为", "小米", "腾讯", "字节", "阿里", "创业", "融资",

    # === 深度 ===
    "analysis", "in-depth", "investigation",
    "深度", "分析", "调查",
]

# 敏感词跳过清单（标题命中则不推送，避免企业微信审核）
# 只匹配标题，不匹配正文，防止误杀
# 敏感词跳过清单（同时检查英文原文和中译后中文）
SKIP_KEYWORDS_EN = [
    "Tibet", "Xinjiang", "Uyghur", "Tiananmen",
    "Falun Gong", "Hong Kong independence",
    "Taiwan independence", "Taiwan.*sovereignty",
    "Xi.*critic", "dictator",
    "war.*China", "invasion.*Taiwan", "PLA.*attack",
    # 中国经济负面叙事
    "China.*crash", "China.*collapse", "China.*crisis.*econom",
    "China.*debt bomb", "China.*ghost city",
    "unemployment.*surge.*China",
]
SKIP_KEYWORDS_CN = [
    "台湾独立", "台湾主权", "藏独", "疆独", "香港独立",
    "天安门", "法轮功", "习近平", "独裁",
    "武力攻台", "入侵台湾", "台独",
]

# 全文字数上限（超过则截断，避免单条消息超企业微信 4096 字节限制）
FULL_TEXT_MAX_CHARS = 1200

# Webhook URL 从环境变量读取，不写死在代码里
# export WECHAT_WEBHOOK_URL="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
