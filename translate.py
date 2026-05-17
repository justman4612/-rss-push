"""Google Translate 批量翻译（不用 API key，零成本）"""
import re
import time
from deep_translator import GoogleTranslator

CHUNK_SIZE = 4000
SEP = "\n<<<SEP>>>\n"
MAX_RETRIES = 2


def _translate_one(text, source="auto", target="zh-CN"):
    """翻译单条，带重试"""
    for attempt in range(MAX_RETRIES + 1):
        try:
            return GoogleTranslator(source=source, target=target).translate(text)
        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(2)
    raise RuntimeError("translation failed after retries")


def batch_translate(texts, source="auto", target="zh-CN"):
    """批量翻译，拼接后一次调多段。失败则逐条降级"""
    if not texts:
        return []

    non_empty = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
    if not non_empty:
        return texts[:]

    # 分组
    chunks = []
    current_chunk = []
    current_len = 0
    for idx, text in non_empty:
        if current_len + len(text) > CHUNK_SIZE:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = [(idx, text)]
            current_len = len(text)
        else:
            current_chunk.append((idx, text))
            current_len += len(text) + len(SEP)
    if current_chunk:
        chunks.append(current_chunk)

    results = list(texts)
    fail_count = 0

    for ci, chunk in enumerate(chunks):
        combined = SEP.join(t for _, t in chunk)
        translated = None

        # 先尝试批量
        try:
            translated = GoogleTranslator(source=source, target=target).translate(combined)
            parts = re.split(r'\s*<<<SEP>>>\s*', translated)
            if len(parts) == len(chunk):
                for (idx, _), part in zip(chunk, parts):
                    results[idx] = part.strip()
                time.sleep(0.5)  # 避免触发限流
                continue
        except Exception:
            pass  # 降级到逐条

        # 逐条降级
        for idx, text in chunk:
            try:
                results[idx] = _translate_one(text)
                time.sleep(0.3)
            except Exception:
                fail_count += 1

    if fail_count:
        print(f"    [翻译] {fail_count} 条翻译失败，保留原文")
    return results
