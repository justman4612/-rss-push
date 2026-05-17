"""Google Translate 批量翻译（不用 API key，零成本）"""
import re
from deep_translator import GoogleTranslator

CHUNK_SIZE = 4000
# 用 Google Translate 不会改动的分隔符
SEP = "\n<<<SEP>>>\n"


def batch_translate(texts, source="auto", target="zh-CN"):
    """批量翻译，拼接后一次调多段，减少 API 调用"""
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

    translator = GoogleTranslator(source=source, target=target)
    results = list(texts)

    for ci, chunk in enumerate(chunks):
        combined = SEP.join(t for _, t in chunk)
        try:
            translated = translator.translate(combined)
            # 用正则分割，容错空白变化
            parts = re.split(r'\s*<<<SEP>>>\s*', translated)

            if len(parts) == len(chunk):
                for (idx, _), part in zip(chunk, parts):
                    results[idx] = part.strip()
            else:
                # 分割数不匹配，逐个翻译降级
                print(f"    [翻译分割异常] 期望{len(chunk)}段 实际{len(parts)}段，降级逐条翻译")
                for idx, text in chunk:
                    try:
                        results[idx] = translator.translate(text)
                    except Exception:
                        pass  # 保留原文
        except Exception as e:
            print(f"    [翻译失败 chunk{ci}]: {e}")
            # 该组保留原文

    return results
