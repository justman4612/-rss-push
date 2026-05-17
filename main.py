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

# Windows GBK 终端适配 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config
import dedup
import translate as translator


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
        kw_lower = kw.lower()
        # 短关键词加词边界，避免 "AI" 误匹配 "again"/"rain"
        pattern = rf"\b{kw_lower}\b" if len(kw_lower) <= 3 else kw_lower
        try:
            if re.search(pattern, text_lower):
                return True
        except re.error:
            if kw_lower in text_lower:
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


def _source_color(source):
    """来源对应企业微信颜色"""
    return {
        "BBC": "warning",
        "CNN": "warning",
        "NHK": "info",
        "JapanTimes": "comment",
    }.get(source, "info")


def build_summary(all_articles):
    """摘要消息：来源分块 + 标题粗体 + 摘要缩进，留白呼吸"""
    beijing_tz = timezone(timedelta(hours=8))
    today = datetime.now(beijing_tz).strftime("%Y-%m-%d %A")

    from collections import OrderedDict
    grouped = OrderedDict()
    for art in all_articles:
        grouped.setdefault(art["source"], []).append(art)

    lines = ["**📰 今日新闻速览**", f'<font color="comment">{today}</font>', ""]

    total = 0
    for source, articles in grouped.items():
        color = _source_color(source)
        lines.append(f'<font color="{color}">◆ {source} · {len(articles)} 篇</font>')
        lines.append("")
        for art in articles:
            total += 1
            title = re.sub(r'[\[\]\*_~#]', '', art["title"].replace("\n", " "))
            summary = re.sub(r'[\[\]\*_~#]', '', art["summary"][:100].replace("\n", " "))
            lines.append(f"**{total}.** {title}")
            if summary:
                lines.append(f"> {summary}")
        lines.append("")

    lines.append(f'<font color="comment">共 {total} 篇 · 下文附全文</font>')
    return "\n".join(lines)


def build_full_text(article, index):
    """单篇全文：来源标签 + 标题 + 正文，段落间空行不累眼"""
    source = article["source"]
    title = re.sub(r'[\[\]\*_~#]', '', article["title"])
    color = _source_color(source)
    safe_source = re.sub(r'[\[\]\*_~#]', '', source)

    # 抓取全文
    text = ""
    if article["link"]:
        print(f"  抓取全文 [{index}]: {title[:50]}...")
        text = fetch_article_text(article["link"])

    # 翻译（非 dry-run 模式）
    if text and "--no-translate" not in sys.argv:
        try:
            text = translator.batch_translate([text])[0]
        except Exception:
            pass

    if len(text) > config.FULL_TEXT_MAX_CHARS:
        text = text[:config.FULL_TEXT_MAX_CHARS] + "\n\n…"

    if not text:
        text = article.get("summary", "")

    # 段落分拆，每段用引用块包裹（视觉缩进 + 防止特殊字符破坏 markdown）
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    body_lines = []
    for p in paragraphs:
        p_escaped = re.sub(r'^([\*#\->])', r'\\\1', p)
        body_lines.append(f"> {p_escaped}")
    body = "\n>\n".join(body_lines) if body_lines else ""

    return (
        f'<font color="{color}">{safe_source}</font>  '
        f"**{title}**\n\n"
        f"{body}"
    )


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


# ---- Mock 数据（dry-run 用） ----
MOCK_ENTRIES = [
    # 命中类
    ("US-China trade tensions escalate after new tariff announcement", "The United States and China are locked in a new round of trade disputes as both sides impose fresh tariffs on billions of dollars worth of goods.", "https://www.bbc.com/news/world-us-china-tariffs"),
    ("China GDP growth beats expectations in Q2", "China's economy grew faster than expected in the second quarter, driven by strong exports and industrial output, but the real estate sector remains a drag.", "https://www.bbc.com/news/business-china-gdp"),
    ("DeepSeek releases new AI model challenging OpenAI", "Chinese AI startup DeepSeek unveiled its latest large language model, claiming performance on par with GPT-5 at a fraction of the training cost.", "https://www.cnn.com/tech/deepseek-ai-model"),
    ("Nvidia chip restrictions spark US-China semiconductor war", "New US export controls on advanced Nvidia GPUs have drawn sharp criticism from Beijing, escalating the ongoing semiconductor confrontation between the two powers.", "https://www.cnn.com/tech/nvidia-chip-ban-china"),
    ("Wang Yi meets ASEAN foreign ministers amid South China Sea tensions", "Chinese Foreign Minister Wang Yi held talks with ASEAN counterparts in Beijing, discussing maritime disputes and economic cooperation in the South China Sea.", "https://www.bbc.com/news/world-asia-wangyi"),
    ("In-depth analysis: How China's Belt and Road is reshaping global trade", "A comprehensive investigation into the Belt and Road Initiative reveals shifting patterns in global infrastructure investment and geopolitical influence.", "https://www.bbc.com/news/world-bri-analysis"),
    ("Chinese official Li Qiang pledges further economic reforms at Davos", "Premier Li Qiang told world leaders at the World Economic Forum that China remains committed to opening up its markets and deepening structural reforms.", "https://www.cnn.com/business/li-qiang-davos"),
    ("Taiwan Strait tensions rise after PLA military exercises", "China conducted large-scale military exercises around Taiwan, drawing condemnation from Washington and raising fears of miscalculation in the region.", "https://www.cnn.com/world/taiwan-strait-tensions"),
    ("PBOC cuts key interest rate to boost sluggish Chinese economy", "The People's Bank of China surprised markets by cutting its medium-term lending facility rate, signaling more aggressive stimulus to revive the slowing economy.", "https://www.zaobao.com/finance/pboc-rate-cut"),
    ("Investigation: The hidden environmental cost of China's AI boom", "An investigative report reveals the massive water and energy consumption behind China's rapid expansion of AI data centers across the country.", "https://www.zaobao.com/news/china-ai-environment"),
    # 不命中类
    ("Australia weather forecast: heavy rain expected this weekend", "Meteorologists predict severe thunderstorms and flooding across New South Wales and Queensland.", "https://www.bbc.com/news/world-australia-weather"),
    ("Football: Manchester United wins Premier League opener", "Manchester United secured a convincing victory in their first match of the new Premier League season.", "https://www.cnn.com/sports/man-utd-premier-league"),
    ("NASA announces new mission to explore Jupiter's moons", "The space agency unveiled plans for a bold new mission to study the subsurface oceans of Europa.", "https://www.bbc.com/news/nasa-jupiter-mission"),
    ("French cuisine festival draws record crowds in Paris", "The annual French gastronomy festival attracted over 100,000 visitors, celebrating the country's culinary heritage.", "https://www.cnn.com/travel/french-cuisine-festival"),
    ("Global coffee prices surge due to Brazil drought", "Coffee futures hit a 5-year high as severe drought conditions threaten Brazil's coffee-growing regions.", "https://www.bbc.com/news/business-coffee-prices"),
]

# 模拟全文（dry-run 不联网）
MOCK_FULL_TEXTS = {
    "tariff": "The United States announced sweeping new tariffs on Chinese imports, targeting electric vehicles, solar panels, and advanced semiconductors. Beijing vowed to retaliate with countermeasures. Analysts warn the escalating trade war could shave 0.5% off global GDP growth in 2026. The Biden administration defended the move as necessary to protect American industries from unfair competition, while Chinese officials accused Washington of economic coercion.",
    "gdp": "China's economy expanded by 5.2% in the April-June period, surpassing the 5.0% consensus forecast. Industrial production rose 6.1% year-on-year, while retail sales grew 4.8%. However, the property sector continued to contract, with new home prices falling for the 12th consecutive month. The PBOC has pledged to use additional monetary tools to support growth.",
    "deepseek": "DeepSeek, the Hangzhou-based AI startup founded in 2023, released its latest model DeepSeek-V3, which matches or exceeds GPT-5 on several benchmarks including reasoning, coding, and mathematical problem-solving. Most notably, the model was trained at less than 10% of the estimated cost of comparable Western models, raising questions about the effectiveness of US chip export controls.",
    "nvidia": "The US Commerce Department expanded restrictions on Nvidia's China-bound GPU shipments, closing loopholes that allowed Chinese companies to acquire advanced chips through third countries. Beijing called the move 'economic bullying' and hinted at rare earth export restrictions as potential retaliation. Nvidia shares fell 3% on the news.",
    "wangyi": "Foreign Minister Wang Yi hosted a two-day summit with ASEAN foreign ministers in Beijing, focusing on finalizing the Code of Conduct in the South China Sea. While China pledged to accelerate negotiations, several ASEAN members expressed concern over recent Chinese naval activities near disputed reefs.",
    "belt": "A six-month investigation by BBC correspondents across 12 countries reveals that China's Belt and Road Initiative has shifted from large-scale infrastructure projects to more targeted investments in digital infrastructure and green energy. The report documents both success stories and mounting debt concerns in recipient nations.",
    "liqiang": "Premier Li Qiang delivered a keynote address at the World Economic Forum in Davos, promising to 'substantially reduce' market access restrictions for foreign investors and to strengthen intellectual property protections. The speech was widely seen as China's most concrete reform pledge in years.",
    "taiwan": "The PLA conducted its largest-ever exercise around Taiwan, involving over 100 aircraft and 30 naval vessels simulating a blockade. The US deployed two carrier strike groups to the region in response, marking the most serious cross-strait escalation since 1996.",
    "pboc": "The PBOC cut its one-year MLF rate by 15 basis points to 2.35%, the largest single reduction in three years. Economists view the move as a prelude to broader stimulus measures aimed at stabilizing the property market and boosting consumer confidence.",
    "ai_env": "A team of environmental researchers found that China's AI data centers consumed an estimated 15 billion kWh of electricity in 2025, equivalent to the annual output of three nuclear reactors. Water consumption for cooling exceeded 1.2 billion tons, raising sustainability concerns in drought-prone regions.",
}


def run_dry():
    """离线模拟：用假数据测试关键词匹配和消息组装"""
    beijing_tz = timezone(timedelta(hours=8))
    print("=" * 50)
    print("DRY RUN — 离线模拟测试")
    print(f"时间: {datetime.now(beijing_tz).strftime('%Y-%m-%d %H:%M')} (北京时间)")
    print("=" * 50)

    # 构造假 feedparser entries（兼容 classify_articles 需要的 .get 方法）
    class MockEntry:
        def __init__(self, title, summary, link):
            self._data = {"title": title, "summary": summary, "link": link, "published": datetime.now(beijing_tz).isoformat()}
        def get(self, key, default=""):
            return self._data.get(key, default)

    mock_entries = [MockEntry(t, s, l) for t, s, l in MOCK_ENTRIES]

    # 用三条源模拟
    all_articles = []
    for source_name in ["BBC", "CNN", "联合早报"]:
        matched = classify_articles(mock_entries, source_name)
        print(f"[{source_name}] 命中 {len(matched)} 篇")
        for art in matched:
            print(f"  [OK] {art['title'][:60]}")
        all_articles.extend(matched)

    if not all_articles:
        print("\n无匹配文章！关键词或分类逻辑有问题。")
        return

    # 去重
    seen = set()
    unique = []
    for art in all_articles:
        if art["title"].lower() not in seen:
            seen.add(art["title"].lower())
            unique.append(art)
    all_articles = unique
    print(f"\n去重后共 {len(all_articles)} 篇")

    # 组装摘要
    print("\n" + "=" * 50)
    print("【摘要消息预览】")
    print("=" * 50)
    summary = build_summary(all_articles)
    print(summary[:2000])

    # 全文（用 mock 文本替代网络抓取）
    print("\n" + "=" * 50)
    print("【全文消息预览（前2篇）】")
    print("=" * 50)
    for i, art in enumerate(all_articles[:2], 1):
        # 从 mock 全文字典找匹配
        text = ""
        for key, full in MOCK_FULL_TEXTS.items():
            if key in art["title"].lower():
                text = full
                break
        if not text:
            text = art["summary"]
        if len(text) > config.FULL_TEXT_MAX_CHARS:
            text = text[:config.FULL_TEXT_MAX_CHARS] + "\n\n...(已截断)"

        msg = build_full_text(art, i)
        print(msg[:800])
        print(f"... (共 {len(msg)} 字符)")
        print("---")

    # 关键词覆盖统计
    print("\n" + "=" * 50)
    print("【关键词覆盖统计】")
    print("=" * 50)
    hits = {kw: 0 for kw in config.KEYWORDS}
    for art in all_articles:
        text_lower = (art["title"] + " " + art["summary"]).lower()
        for kw in config.KEYWORDS:
            kw_lower = kw.lower()
            pattern = rf"\b{kw_lower}\b" if len(kw_lower) <= 3 else kw_lower
            try:
                if re.search(pattern, text_lower):
                    hits[kw] += 1
            except re.error:
                if kw.lower() in text_lower:
                    hits[kw] += 1
    active_hits = {k: v for k, v in hits.items() if v > 0}
    for kw, count in sorted(active_hits.items(), key=lambda x: -x[1]):
        print(f"  [{count:>2}] {kw}")

    # 关键词有效性检查（命中0条的关键词可能有问题）
    zero_hits = [k for k, v in hits.items() if v == 0]
    if zero_hits:
        print(f"\n[WARN] 以下 {len(zero_hits)} 个关键词未命中任何文章（可能需要调整）：")
        for kw in zero_hits:
            print(f"  - {kw}")

    # 预期 vs 实际
    should_match = [e for e in MOCK_ENTRIES if match_keywords(e[0] + " " + e[1])]
    should_not = [e for e in MOCK_ENTRIES if not match_keywords(e[0] + " " + e[1])]
    print(f"\n命中文章: {len(should_match)} 篇 / 跳过文章: {len(should_not)} 篇")

    print("\n" + "=" * 50)
    print("Dry-run 完成。逻辑验证通过。")
    print("=" * 50)


def main():
    # dry-run 模式
    if "--dry-run" in sys.argv:
        run_dry()
        return

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
    print(f"\n同次去重后共 {len(all_articles)} 篇")

    # 去重（跨天：7天内标题不重复推送）
    all_articles, skipped = dedup.filter_new(all_articles)
    if skipped:
        print(f"跨天去重跳过 {skipped} 篇（7天内已推送）")
    print(f"最终推送 {len(all_articles)} 篇")

    if not all_articles:
        print("全部重复，跳过推送")
        return

    # 翻译（跳过中文源和 dry-run 模式）
    if "--no-translate" not in sys.argv:
        print("\n翻译中...")
        # 标题
        titles = [art["title"] for art in all_articles]
        translated_titles = translator.batch_translate(titles)
        # 摘要
        summaries = [art["summary"] for art in all_articles]
        translated_summaries = translator.batch_translate(summaries)
        # 应用
        for i, art in enumerate(all_articles):
            art["title"] = translated_titles[i]
        art["summary"] = translated_summaries[i]
        print("翻译完成")

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

    # 记录已推送（下次不重复推）
    dedup.save_pushed(all_articles)
    print("推送记录已保存")


if __name__ == "__main__":
    main()
