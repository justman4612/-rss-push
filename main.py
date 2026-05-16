"""
RSS 新闻抓取 → 关键词过滤 → 全文提取 → 企业微信推送
在 GitHub Actions 上定时运行（UTC 0:00 = 北京时间 8:00）
"""
import os
import re
import sys
import json
import html as html_lib
from datetime import datetime, timezone, timedelta

import requests
import feedparser
from bs4 import BeautifulSoup

import config


def fetch_rss(url):
    """抓取并解析 RSS，返回条目列表"""
    try:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"
        })
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        if feed.bozo:
            print(f"  [警告] RSS 解析异常: {feed.bozo_exception}")
        return feed.entries
    except Exception as e:
        print(f"  [错误] 抓取失败 {url}: {e}")
        return []


def match_keywords(text):
    """检查文本是否命中 config 中任意关键词（不区分大小写）"""
    if not text:
        return False
    text_lower = text.lower()
    for kw in config.KEYWORDS:
        # 短关键词加词边界，避免 "AI" 误匹配 "again"/"rain"
        pattern = rf"\b{kw}\b" if len(kw) <= 3 else kw
        try:
            if re.search(pattern, text_lower):
                return True
        except re.error:
            if kw.lower() in text_lower:
                return True
    return False


def fetch_article_text(url):
    """抓取文章页面，提取正文文本"""
    try:
        resp = requests.get(url, timeout=20, headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 按来源尝试不同的提取策略
        text = ""
        if "bbc.com" in url or "bbc.co.uk" in url:
            text = _extract_bbc(soup)
        elif "cnn.com" in url:
            text = _extract_cnn(soup)
        elif "zaobao.com" in url:
            text = _extract_zaobao(soup)
        else:
            text = _extract_generic(soup)

        # 清理文本
        text = _clean_text(text)
        return text

    except Exception as e:
        print(f"    [警告] 无法抓取全文 {url[:80]}: {e}")
        return ""


def _extract_bbc(soup):
    """BBC 正文提取"""
    parts = []
    for tag in soup.select("article p, [data-component='text-block'] p, .story-body__inner p"):
        t = tag.get_text(strip=True)
        if t:
            parts.append(t)
    return "\n".join(parts)


def _extract_cnn(soup):
    """CNN 正文提取"""
    parts = []
    for tag in soup.select(".article__content p, .zn-body__paragraph, article p"):
        t = tag.get_text(strip=True)
        if t:
            parts.append(t)
    return "\n".join(parts)


def _extract_zaobao(soup):
    """联合早报正文提取"""
    parts = []
    for tag in soup.select(".article-content-rawhtml p, .article-body p, article p"):
        t = tag.get_text(strip=True)
        if t:
            parts.append(t)
    return "\n".join(parts)


def _extract_generic(soup):
    """通用正文提取：取 <article> 或 <body> 中的 <p> 标签"""
    parts = []
    container = soup.find("article") or soup.find("body")
    if container:
        for tag in container.find_all("p"):
            t = tag.get_text(strip=True)
            if t and len(t) > 20:  # 过滤太短的片段
                parts.append(t)
    return "\n".join(parts)


def _clean_text(text):
    """清理文本：去 HTML 实体、去多余空白"""
    text = html_lib.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def classify_articles(entries, source_name):
    """从 RSS 条目中筛选命中关键词的文章，返回结构化列表"""
    results = []
    seen_titles = set()

    for entry in entries[:config.MAX_PER_SOURCE]:
        title = entry.get("title", "").strip()
        summary = entry.get("summary", "") or entry.get("description", "")
        summary = _clean_text(BeautifulSoup(summary, "html.parser").get_text())

        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        # 关键词匹配标题或摘要
        if match_keywords(title) or match_keywords(summary):
            link = entry.get("link", "")
            published = entry.get("published", "") or entry.get("updated", "")

            results.append({
                "source": source_name,
                "title": title,
                "summary": summary[:300],  # 摘要截断，详情见全文
                "link": link,
                "published": published,
            })

    return results


def build_summary(all_articles):
    """构建摘要消息（Markdown）"""
    beijing_tz = timezone(timedelta(hours=8))
    today = datetime.now(beijing_tz).strftime("%Y-%m-%d %A")

    lines = [f"📰 **今日新闻速览 | {today}**\n"]

    # 按来源分组
    from collections import OrderedDict
    grouped = OrderedDict()
    for art in all_articles:
        grouped.setdefault(art["source"], []).append(art)

    total = 0
    for source, articles in grouped.items():
        lines.append(f"---")
        lines.append(f"**【{source}】** ({len(articles)}篇)")
        for i, art in enumerate(articles, 1):
            total += 1
            title = art["title"].replace("\n", " ").replace("\r", "")
            # 企业微信 markdown 不支持某些特殊字符，做转义
            title = re.sub(r'[\[\]\*_~]', '', title)
            summary = art["summary"][:120].replace("\n", " ")
            summary = re.sub(r'[\[\]\*_~]', '', summary)
            lines.append(f"> **{total}.** {title}")
            if summary:
                lines.append(f"> _{summary}_")
            lines.append("")

    lines.append(f"共 **{total}** 篇 · 下文附全文")
    return "\n".join(lines)


def build_full_text(article, index):
    """构建单篇文章全文消息（Markdown）"""
    source = article["source"]
    title = re.sub(r'[\[\]\*_~]', '', article["title"])

    # 抓取全文
    text = ""
    if article["link"]:
        print(f"  抓取全文 [{index}]: {title[:50]}...")
        text = fetch_article_text(article["link"])

    # 截断
    if len(text) > config.FULL_TEXT_MAX_CHARS:
        text = text[:config.FULL_TEXT_MAX_CHARS] + "\n\n...(已截断)"

    if not text:
        text = article.get("summary", "(无法获取全文)")

    lines = [
        f"📄 **{index}. [{source}] {title}**",
        "",
        text,
    ]

    if article["link"]:
        lines.append("")
        lines.append(f"原文链接: {article['link']}")

    return "\n".join(lines)


def send_wechat(content, webhook_url):
    """发送 Markdown 消息到企业微信"""
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": content},
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        data = resp.json()
        if data.get("errcode") == 0:
            return True
        else:
            print(f"  [推送失败] {data}")
            return False
    except Exception as e:
        print(f"  [推送异常] {e}")
        return False


def main():
    webhook_url = os.environ.get("WECHAT_WEBHOOK_URL", "")
    if not webhook_url:
        print("错误: 请设置环境变量 WECHAT_WEBHOOK_URL")
        sys.exit(1)

    print("=" * 50)
    print("RSS 新闻抓取开始")
    print(f"时间: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')} (北京时间)")
    print("=" * 50)

    # 1. 抓取所有 RSS 源
    all_articles = []
    for source_name, urls in config.SOURCES.items():
        print(f"\n[{source_name}]")
        for url in urls:
            print(f"  抓取: {url}")
            entries = fetch_rss(url)
            matched = classify_articles(entries, source_name)
            print(f"  命中 {len(matched)} 篇")
            all_articles.extend(matched)

    if not all_articles:
        print("\n无匹配文章，跳过推送")
        return

    # 去重（按标题）
    seen = set()
    unique = []
    for art in all_articles:
        if art["title"].lower() not in seen:
            seen.add(art["title"].lower())
            unique.append(art)
    all_articles = unique
    print(f"\n去重后共 {len(all_articles)} 篇")

    # 2. 发送摘要
    print("\n发送摘要...")
    summary = build_summary(all_articles)
    if not send_wechat(summary, webhook_url):
        print("摘要发送失败，终止")
        sys.exit(1)
    print("摘要已发送")

    # 3. 逐篇发送全文
    success = 0
    for i, art in enumerate(all_articles, 1):
        full = build_full_text(art, i)
        if send_wechat(full, webhook_url):
            success += 1
            print(f"  [{i}/{len(all_articles)}] 已发送: {art['title'][:40]}")
        else:
            print(f"  [{i}/{len(all_articles)}] 发送失败: {art['title'][:40]}")

    print(f"\n完成: 摘要 + {success}/{len(all_articles)} 篇全文已推送")


if __name__ == "__main__":
    main()
