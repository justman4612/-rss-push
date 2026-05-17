"""Google Translate 批量翻译（不用 API key，零成本）"""
from deep_translator import GoogleTranslator

# 单次调用上限（字符数），留余量避免超限
CHUNK_SIZE = 4000
# 分隔符，在批量翻译时用来拼接和拆分
SEP = " ||| "


def batch_translate(texts, source="auto", target="zh-CN"):
    """批量翻译，拼接后一次调多段，大幅减少 API 调用次数"""
    if not texts:
        return []

    # 滤掉空串
    non_empty = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
    if not non_empty:
        return texts[:]

    # 按 CHUNK_SIZE 分组
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

    # 翻译每个分组
    translator = GoogleTranslator(source=source, target=target)
    results = list(texts)  # 保留原始顺序和空值
    for chunk in chunks:
        combined = SEP.join(t for _, t in chunk)
        try:
            translated = translator.translate(combined)
            parts = [s.strip() for s in translated.split(SEP)]
            for (idx, _), part in zip(chunk, parts):
                results[idx] = part
        except Exception as e:
            print(f"    [翻译失败] {e}")
            # 该组保留原文

    return results
