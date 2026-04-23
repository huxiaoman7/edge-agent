"""面向昇腾 310 场景的本地检索器。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

# 同义词/别名，提高命中率
EXPANSIONS: dict[str, list[str]] = {
    "310": ["310", "300i", "300I", "Duo", "duo", "双芯", "推理卡"],
    "310p": ["310p", "310P", "P系列"],
    "mindie": ["mindie", "MindIE", "ATB", "atb", "atbgraph", "昇腾", "ascend", "华为"],
    "vllm": ["vllm", "VLLM", "decode", "W8A8SC", "TP", "并行"],
    "qwen": ["Qwen", "qwen", "通义", "千问"],
    "量化": ["量化", "W8A8", "W4A8", "W8A16", "浮点", "fp16"],
}


@dataclass
class Evidence:
    title: str
    body: str
    score: int


def _tokenize(text: str) -> set[str]:
    parts = re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]+", text)
    s: set[str] = set()
    for p in parts:
        s.add(p)
        s.add(p.lower())
    return s


def _expand_query(q: str) -> set[str]:
    tokens = _tokenize(q)
    for key, alts in EXPANSIONS.items():
        for t in list(tokens):
            if key.lower() in t.lower() or t.lower() in key.lower():
                tokens.update(alts)
        if re.search(r"310(?!0)", q) or "双芯" in q:
            tokens.update(EXPANSIONS["310"])
    return tokens


def _load_kb(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _score_chunk(query_tokens: set[str], text: str) -> int:
    t = set(_tokenize(text))
    if not t:
        return 0
    return sum(1 for x in query_tokens if x in t or any(x in y for y in t if len(x) >= 2))


def build_chunks(kb: dict) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    out.append(("图例与说明", json.dumps(kb.get("legend", {}), ensure_ascii=False, indent=2)))

    mindie = kb.get("mindie", {})
    for i, row in enumerate(mindie.get("text_models_300i_duo", [])):
        text = (
            f"{row.get('series', '')} {row.get('model', '')}；"
            f"上下文 {row.get('context_length', '见官方表')}；"
            f"量化 {','.join(row.get('quantization', [])) or '见官方表'}；"
            f"硬件 {row.get('hardware', '见官方表')}；"
            f"支持级别 {row.get('support_level', 'mixed')}"
        )
        out.append((f"文本模型（300I Duo）{i + 1}", text))

    for i, row in enumerate(mindie.get("multimodal_models_300i_duo", [])):
        text = (
            f"{row.get('series', '')} {row.get('model', '')}；"
            f"量化 {','.join(row.get('quantization', [])) or '见官方表'}；"
            f"硬件 {row.get('hardware', '见官方表')}；"
            f"支持级别 {row.get('support_level', 'mixed')}"
        )
        out.append((f"多模态（300I Duo）{i + 1}", text))

    uns = mindie.get("unsupported_examples_300i_duo", [])
    if uns:
        out.append(("300I Duo 不支持示例", "；".join(uns)))

    v = kb.get("vllm_310p_poc", {})
    if v:
        models = []
        for m in v.get("models", []):
            models.append(
                f"{m.get('model', '')}({m.get('type', '')}, {','.join(m.get('precision', []))})"
            )
        out.append(
            (
                "vLLM 310P POC",
                v.get("description", "")
                + "；模型："
                + "；".join(models)
                + "；能力："
                + "、".join(v.get("capabilities", [])),
            )
        )
    for faq in kb.get("faq", []):
        out.append((f"常见问题：{faq.get('q', '')}", faq.get("a", "")))
    return out


def retrieve_evidence(query: str, kb_path: Path, top_n: int = 8) -> tuple[dict, list[Evidence]]:
    kb = _load_kb(kb_path)
    chunks = build_chunks(kb)
    qtok = _expand_query(query)
    scored: List[Evidence] = []
    for title, body in chunks:
        s = _score_chunk(qtok, title + " " + body) * 2 + _score_chunk(qtok, body)
        if s > 0:
            scored.append(Evidence(title=title, body=body, score=s))
    scored.sort(key=lambda x: -x.score)
    return kb, scored[:top_n]


def retrieve_answer(query: str, kb_path: Path, top_n: int = 8) -> str:
    if not query or not query.strip():
        return "请输入与昇腾 310、MindIE、vLLM 或具体模型名相关的问题。"

    kb, scored = retrieve_evidence(query, kb_path, top_n=top_n)
    if not scored:
        mindie = kb.get("mindie", {})
        text_rows = mindie.get("text_models_300i_duo", [])
        vllm = kb.get("vllm_310p_poc", {})
        # 无命中时给摘要
        lines = [
            "## 未在知识库中精确定位，可参考以下固定摘要：\n",
            "### MindIE / Atlas 300I Duo（310）",
        ]
        for row in text_rows[:3]:
            lines.append(f"- {row.get('series', '')} {row.get('model', '')}")
        lines.append("\n### vLLM 310P POC\n")
        for row in vllm.get("models", [])[:3]:
            lines.append(f"- {row.get('model', '')} ({'/'.join(row.get('precision', []))})")
        lines.append(
            f"\n完整清单以官方文档为准：\n{kb.get('meta', {}).get('mindie_list_url', '')}"
        )
        return "\n".join(lines)

    parts: List[str] = ["## 与问题相关的条目（按相关度）\n"]
    seen = set()
    for ev in scored[:top_n]:
        key = (ev.title, ev.body[:80])
        if key in seen:
            continue
        seen.add(key)
        parts.append(f"### {ev.title}\n\n{ev.body}\n")
    parts.append(
        f"\n---\n**信息来源**：{kb.get('meta', {}).get('mindie_list_url', '详见 knowledge.json 中 meta.mindie_list_url')}"
    )
    return "\n".join(parts)
