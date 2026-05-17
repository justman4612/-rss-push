"""文章去重：基于 source+title 哈希，保留 7 天推送记录，配合 GitHub Actions cache 持久化"""
import json
import hashlib
import os
from datetime import datetime, timedelta

CACHE_FILE = os.environ.get("PUSHED_CACHE_FILE", "pushed.json")
KEEP_DAYS = 7


def _key(article):
    """生成文章唯一键：source + title 的 MD5"""
    raw = f"{article['source']}:{article['title']}".lower()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def load_pushed():
    """加载已推送记录，清除超过 KEEP_DAYS 天的旧记录"""
    if not os.path.exists(CACHE_FILE):
        return set()
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return set()

    cutoff = (datetime.utcnow() - timedelta(days=KEEP_DAYS)).isoformat()[:10]
    fresh = {k for k, v in data.items() if v.get("date", "") >= cutoff}
    return fresh


def save_pushed(articles):
    """把本次推送的文章追加到记录中"""
    existing = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    today = datetime.utcnow().isoformat()[:10]
    for art in articles:
        k = _key(art)
        existing[k] = {"title": art["title"][:80], "source": art["source"], "date": today}

    # 清理过期
    cutoff = (datetime.utcnow() - timedelta(days=KEEP_DAYS)).isoformat()[:10]
    existing = {k: v for k, v in existing.items() if v.get("date", "") >= cutoff}

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def filter_new(articles):
    """过滤掉已推送过的文章，返回新文章列表和跳过数"""
    pushed = load_pushed()
    new_articles = []
    skipped = 0
    for art in articles:
        if _key(art) in pushed:
            skipped += 1
        else:
            new_articles.append(art)
    return new_articles, skipped
