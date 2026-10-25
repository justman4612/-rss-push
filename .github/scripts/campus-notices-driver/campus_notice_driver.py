"""校园通知每日采集驱动：列表页发现 → 抓正文 → POST 学校服务桥接端点 → 知识库 xsyu_notices。

背景（2026-10-24 实测）：平台 URL"在线网页"导入确定性失败（解析器不解析 .htm）；
xsyu_notices 是编程沙箱的项目级资源，挂 integration 网关按名字寻址，公网 api.coze.cn
的开放 API 与个人 PAT 均无法触达（integration 路由未对外注册）。因此写入知识库的
最后一跳由学校已部署服务代做：服务端新增受调度令牌保护的 /internal/notices/import-kb
端点，内部走沙箱同款 KnowledgeClient.batch_import（按名字 xsyu_notices，服务端写死，
绝不接受客户端指定 dataset）。

模式：
  verify    只读契约检查：无令牌 POST → 期待 401；带令牌空文档 POST → 期待 200 且零导入。不发任何数据。
  discover  只读：抓两个列表页，输出本次发现的通知 URL（不导入、不改状态）
  run       导入：发现新通知 → 抓正文 → 批量 POST → 更新状态文件 → 输出报告

凭据只从环境变量读取：CAMPUS_SCHEDULER_TOKEN（与既有 process-due 同一令牌）；
CAMPUS_IMPORT_ENDPOINT 可覆盖默认端点。任何输出不回显令牌。
状态文件 known_notices.json 记录已导入 URL，防止重复入库；服务端不做幂等，重导由驱动负责。
设计边界：只采集公共通知；单次最多导入 --limit 条（默认 5）；失败逐条记录不中断整批。
"""
import argparse
import json
import re
import ssl
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error
from urllib.parse import urljoin

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("缺少 beautifulsoup4：pip install beautifulsoup4", file=sys.stderr)
    raise

HERE = Path(__file__).resolve().parent
STATE_PATH = HERE / "known_notices.json"

DEFAULT_IMPORT_ENDPOINT = "https://s5h8t653w3.coze.site/internal/notices/import-kb"

LIST_SOURCES = [
    # 教务处列表页用相对链接（info/1048/xxx.htm），官网用绝对路径（/info/1072/...），正则统一不带前导斜杠
    ("教务处", "https://jwch.xsyu.edu.cn/tzgg.htm", re.compile(r"info/1048/\d+\.htm")),
    ("学校官网", "https://www.xsyu.edu.cn/xwzx/tzgg.htm", re.compile(r"info/1072/\d+\.htm")),
]

META_LINE_RE = re.compile(r"发布时间[：:]\s*(\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?)")
TITLE_SUFFIX_RE = re.compile(r"[-－—|]西安石油大学.*$")

BODY_SELECTORS = ("#vsb_content", ".v_news_content", "div.content", "article")


def http_get(url, timeout=30):
    req = request.Request(url, headers={"User-Agent": "campus-notices-driver/1.0"})
    with request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        return resp.read()


def post_import(payload, token, endpoint, platform_token="", timeout=90):
    # 部署服务在平台网关之后：所有请求需双凭据（Authorization: Bearer 平台令牌 + 调度令牌），
    # 与 一次只读诊断/probe 脚本的既有做法一致。
    headers = {"Content-Type": "application/json", "X-Campus-Scheduler-Token": token}
    if platform_token:
        headers["Authorization"] = "Bearer " + platform_token
    req = request.Request(endpoint, data=json.dumps(payload).encode("utf-8"),
                          headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
            return resp.status, json.loads(resp.read())
    except error.HTTPError as exc:
        body = exc.read(1024).decode("utf-8", "replace")
        exc.close()
        return exc.code, {"raw": body[:500]}


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"known": {}}


def save_state(state):
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


def discover():
    """抓列表页，返回 [(url, source_name)]，按页面出现顺序，已去重。"""
    found, seen = [], set()
    for name, list_url, pattern in LIST_SOURCES:
        html = http_get(list_url).decode("utf-8", "replace")
        for match in pattern.finditer(html):
            url = urljoin(list_url, match.group(0))
            if url not in seen:
                seen.add(url)
                found.append((url, name))
    return found


def extract_page(html):
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.find("title")
    title = (title_el.get_text("", strip=True) if title_el else "") or ""
    title = TITLE_SUFFIX_RE.sub("", title).strip()

    body_el = None
    for selector in BODY_SELECTORS:
        candidates = soup.select(selector)
        if candidates:
            body_el = max(candidates, key=lambda el: len(el.get_text(strip=True)))
            break
    if body_el is None:
        body_el = soup.body or soup
    for tag in body_el.select("script, style"):
        tag.decompose()
    for br in body_el.select("br"):
        br.replace_with("\n")
    for block in body_el.select("p, div, tr, li, h1, h2, h3"):
        block.insert_before("\n")
        block.insert_after("\n")
    for cell in body_el.select("td, th"):
        cell.insert_after("\t")
    body = "\n".join(line.strip() for line in body_el.get_text().splitlines() if line.strip())

    meta = META_LINE_RE.search(soup.get_text())
    published_at = meta.group(1) if meta else ""
    return title, body, published_at


def build_document(url, source_name):
    html = http_get(url).decode("utf-8", "replace")
    title, body, published_at = extract_page(html)
    if len(body) < 80:
        return None, {"url": url, "ok": False, "reason": f"正文过短({len(body)}字)，疑似解析失败"}
    text = f"{title}｜{published_at}｜{url}\n\n{body}"
    doc = {"source_name": f"{title or url} [{source_name}]"[:200],
           "source_url": url, "published_at": published_at, "text": text}
    return doc, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("verify", "discover", "run"))
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    import os
    endpoint = os.environ.get("CAMPUS_IMPORT_ENDPOINT", DEFAULT_IMPORT_ENDPOINT)
    token = os.environ.get("CAMPUS_SCHEDULER_TOKEN", "")
    platform_token = os.environ.get("CAMPUS_PLATFORM_TOKEN", "")
    if not token and args.mode in ("verify", "run"):
        print(json.dumps({"ok": False, "reason": "缺少 CAMPUS_SCHEDULER_TOKEN"}, ensure_ascii=False))
        return 1

    if args.mode == "verify":
        # 契约检查，零写入：无调度令牌应 401；带令牌空文档应 200 且 imported=0
        try:
            code_anon, _ = post_import({"request_id": str(uuid.uuid4()), "documents": []},
                                       "wrong-token", endpoint, platform_token)
        except error.HTTPError:
            code_anon = 401
        except Exception as exc:
            code_anon = f"error:{type(exc).__name__}"
        code_auth, body = post_import({"request_id": str(uuid.uuid4()), "documents": []},
                                      token, endpoint, platform_token)
        ok = code_anon == 401 and code_auth == 200 and body.get("imported", None) in (0, [])
        print(json.dumps({"verify": bool(ok), "anon_status": code_anon,
                          "auth_status": code_auth, "auth_body": body}, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    if args.mode == "discover":
        urls = discover()
        print(json.dumps({"count": len(urls), "urls": [u for u, _ in urls]}, ensure_ascii=False, indent=2))
        return 0

    # run 模式
    state = load_state()
    state.setdefault("known", {})
    report = {"run_at_utc": datetime.now(timezone.utc).isoformat(), "discovered": 0,
              "imported": [], "skipped_known": 0, "failed": []}
    docs = []
    for url, source_name in discover():
        report["discovered"] += 1
        if url in state["known"]:
            report["skipped_known"] += 1
        elif len(docs) < args.limit:
            doc, err = build_document(url, source_name)
            if doc:
                docs.append(doc)
            else:
                report["failed"].append(err)
    if docs:
        code, body = post_import({"request_id": str(uuid.uuid4()), "documents": docs}, token, endpoint, platform_token)
        if code != 200:
            report["failed"].append({"endpoint_status": code, "body": body})
        else:
            for item in body.get("imported", []):
                report["imported"].append(item)
                state["known"][item["source_url"]] = {
                    "imported_at_utc": report["run_at_utc"],
                    "doc_ids": item.get("doc_ids", []),
                    "title": item.get("title", "")}
            for item in body.get("failed", []):
                report["failed"].append(item)
    # 每日摘要邮件：有新导入才发，空导入不发
    if report["imported"]:
        digest_payload = {
            "request_id": str(uuid.uuid4()),
            "date": report["run_at_utc"][:10],
            "notices": [
                {"title": it.get("title") or it.get("source_url", ""),
                 "source_url": it.get("source_url", ""),
                 "published_at": it.get("published_at", "")}
                for it in report["imported"]
            ],
        }
        try:
            dcode, dbody = post_import(digest_payload, token, endpoint.replace("import-kb", "digest-email"), platform_token)
            report["digest"] = {"status": dcode, "body": dbody}
        except Exception as exc:
            report["digest"] = {"status": "error", "reason": f"{type(exc).__name__}: {exc}"[:200]}
    save_state(state)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["failed"] or report["imported"] else 1


if __name__ == "__main__":
    sys.exit(main())
