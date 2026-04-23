"""MoFix风格多阶段 Agent：规划 -> 检索 -> 生成 -> 审校。"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from .retrieval import Evidence, retrieve_evidence


@dataclass
class AgentConfig:
    top_k: int = 6
    temperature: float = 0.2
    mode: str = "balanced"
    enable_remote: bool = True


@dataclass
class AgentResult:
    answer: str
    intent: str
    plan: list[str]
    evidences: list[dict]
    review_notes: list[str]
    used_remote: bool
    source_url: str


class AscendAgent:
    def __init__(self, kb_path: Path) -> None:
        self.kb_path = kb_path

    def _intent(self, query: str) -> str:
        q = query.lower()
        if any(x in q for x in ["支持", "模型", "qwen", "deepseek", "glm", "llama"]):
            return "model"
        if any(x in q for x in ["区别", "差异", "比较", "对比", "mindie", "vllm"]):
            return "compare"
        if any(x in q for x in ["部署", "上线", "docker", "spaces", "启动"]):
            return "deploy"
        if any(x in q for x in ["量化", "w8a8", "w4a8", "w8a16", "精度"]):
            return "quant"
        return "general"

    def _contextual_query(self, message: str, history: list[dict]) -> str:
        recent_user = [
            str(x.get("content", ""))
            for x in history[-6:]
            if isinstance(x, dict) and x.get("role") == "user"
        ]
        recent = " ".join(recent_user[-2:])
        return f"{recent} {message}".strip()

    def _format_context(self, evidences: list[Evidence]) -> str:
        lines = []
        for idx, ev in enumerate(evidences[:2], start=1):
            brief = ev.body.replace("\n", " ").strip()
            brief = brief[:150]
            lines.append(f"[{idx}] {ev.title}\n{brief}")
        return "\n\n".join(lines)

    def _plan(self, _query: str, intent: str) -> list[str]:
        base = [
            "解析用户目标并识别约束（芯片型号、栈、部署目标）",
            "在本地知识库检索最相关证据（优先官方清单）",
            "输出结论与可执行建议，并标注信息边界",
        ]
        if intent == "compare":
            base.insert(1, "对比 MindIE 与 vLLM 310P 路线，避免混淆")
        elif intent == "deploy":
            base.insert(1, "给出从开发到上线的步骤与风险检查点")
        elif intent == "quant":
            base.insert(1, "优先提取量化能力（W8A8/W8A8SC）与限制")
        return base

    def _remote_llm(
        self,
        user_message: str,
        history: list[dict],
        context: str,
        intent: str,
        cfg: AgentConfig,
    ) -> str | None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        model = os.getenv("OPENAI_MODEL", "").strip()
        if not (cfg.enable_remote and api_key and base_url and model):
            return None

        url = base_url.rstrip("/") + "/chat/completions"
        system_prompt = (
            "你是喵酱，昇腾310芯片智能小助手。"
            "仅根据给定上下文回答，不编造。"
            "输出中文，要求自然、精准、直接。"
            "禁止使用Markdown符号（如 #、*、`、- 列表）。"
            "语气要像真实同事沟通，轻松一点，但不要油腻。"
            "先给一句简短结论，再给关键信息。"
            "上下文不足时直说“当前知识库未覆盖”。"
        )
        history_window = 2 if cfg.mode == "fast" else 5
        recent = [
            {"role": x.get("role"), "content": str(x.get("content", ""))}
            for x in history[-history_window:]
            if isinstance(x, dict) and x.get("role") in {"user", "assistant"}
        ]
        context = context[:900] if cfg.mode == "fast" else context[:1200]
        payload = {
            "model": model,
            "temperature": max(0.0, min(1.0, cfg.temperature)),
            "messages": [
                {"role": "system", "content": system_prompt},
                *recent,
                {
                    "role": "user",
                    "content": (
                        f"用户问题：{user_message}\n"
                        f"意图：{intent}\n"
                        "上下文（可信证据）：\n"
                        f"{context}"
                    ),
                },
            ],
        }
        payload["max_tokens"] = 320 if cfg.mode == "fast" else 420
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            timeout_s = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "4.5" if cfg.mode == "fast" else "7"))
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8")
            obj = json.loads(raw)
            return (
                obj.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            ) or None
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
            return None

    def _fallback(
        self,
        kb: dict,
        evidences: list[Evidence],
        intent: str,
        mode: str,
        query: str,
    ) -> str:
        if not evidences:
            return (
                "我没有在当前知识库精确命中这个问题。\n\n"
                "你可以换个问法，例如：\n"
                "- `Qwen3-32B 在 300I Duo 是否支持？`\n"
                "- `MindIE 和 vLLM 310P 的区别？`\n"
                "- `有哪些模型支持 W8A8？`"
            )

        filtered = [ev for ev in evidences if ev.title != "图例与说明"] or evidences
        pick = 6 if mode == "deep" else 5
        top = filtered[:pick]
        points = [ev.body.replace("\n", " ").strip() for ev in top]

        def first_match(keys: tuple[str, ...]) -> str:
            for p in points:
                if any(k in p for k in keys):
                    return p
            return points[0] if points else ""

        def by_title(keys: tuple[str, ...]) -> str:
            for ev in top:
                if any(k in ev.title for k in keys):
                    return ev.body.replace("\n", " ").strip()
            return ""

        if intent == "compare":
            mindie = by_title(("文本模型（300I Duo）", "多模态（300I Duo）")) or first_match(
                ("Atlas 300I Duo", "ATB")
            )
            vllm = by_title(("vLLM 310P POC",)) or first_match(("vLLM", "310P", "W8A8SC", "decode only"))
            return (
                "先说重点：MindIE 和 vLLM 310P 是两条路线，别混着选就不容易踩坑。\n"
                f"MindIE 侧：{mindie}\n"
                f"vLLM 310P 侧：{vllm}\n"
                "我的建议：如果你重点是官方清单和稳定服务化，优先 MindIE。"
                "如果你重点是 decode-only 图、W8A8SC、TP 并行能力，优先 vLLM 310P。"
                "两条路线不要混成一套口径评估。"
            )

        if intent == "deploy":
            model_line = first_match(("Qwen3", "DeepSeek", "GLM", "Llama"))
            return (
                "可以做，而且完全能上线。建议按先可用、再稳定、后扩容推进。\n"
                f"模型线索：{model_line}\n"
                "我建议你先做单机可用（固定模型、固定参数、健康检查），再补监控（超时、失败率、响应时间），"
                "最后做灰度发布。你给我硬件与并发目标后，我可以直接给参数模板。"
            )

        if intent == "quant":
            quant_line = first_match(("W8A8", "W8A8SC", "W4A8", "量化"))
            return (
                "量化这条路是对的，但要分栈验证，别直接互相套结论。\n"
                f"关键能力：{quant_line}\n"
                "建议：先用浮点跑通基线，再对比量化后的精度和吞吐。"
                "MindIE 与 vLLM 310P 的量化结果请分开验收。"
            )

        if intent == "model":
            mindie = kb.get("mindie", {})
            text_models = mindie.get("text_models_300i_duo", [])
            mm_models = mindie.get("multimodal_models_300i_duo", [])
            vllm_models = kb.get("vllm_310p_poc", {}).get("models", [])
            # 精确型号问法（如 Qwen3-VL-8B 支持吗）优先返回定点答案
            candidates = [
                t
                for t in re.findall(r"[A-Za-z0-9.\-]+", query)
                if any(ch.isdigit() for ch in t) and len(t) >= 4 and t.lower() not in {"310", "310p"}
            ]
            candidate = max(candidates, key=len) if candidates else ""
            c = candidate.lower()
            mt = [x for x in text_models if c and c in x.get("model", "").lower()]
            mm = [x for x in mm_models if c and c in x.get("model", "").lower()]
            mv = [x for x in vllm_models if c and c in x.get("model", "").lower()]
            if candidate and (mt or mm or mv):
                rows = []
                for x in mt[:2]:
                    rows.append(
                        f"| MindIE | 文本 | {x.get('model')} | {x.get('context_length','见官方表')} | {','.join(x.get('quantization',[])) or '见官方表'} | {x.get('hardware','见官方表')} |"
                    )
                for x in mm[:2]:
                    rows.append(
                        f"| MindIE | 多模态 | {x.get('model')} | - | {','.join(x.get('quantization',[])) or '见官方表'} | {x.get('hardware','见官方表')} |"
                    )
                for x in mv[:2]:
                    rows.append(
                        f"| vLLM 310P POC | {x.get('type','')} | {x.get('model')} | - | {','.join(x.get('precision',[]))} | 310P POC 能力范围 |"
                    )
                return (
                    f"有的，{candidate} 在当前知识库里能查到支持信息。\n"
                    "我先把你最关心的点放进这张表：\n"
                    "| 路线 | 类型 | 模型 | 上下文 | 量化/精度 | 硬件/说明 |\n"
                    "| --- | --- | --- | --- | --- | --- |\n"
                    + "\n".join(rows)
                    + "\n如果你愿意，我下一步可以直接给你这款模型在 300I Duo 和 310P 上的部署参数建议。"
                )

            q_l = query.lower()
            ask_300i = ("300i" in q_l) or ("mindie" in q_l)
            only_vllm = any(k in q_l for k in ["只看vllm", "仅vllm", "only vllm", "只看 310p", "仅看310p"])
            if only_vllm:
                capabilities = "、".join(kb.get("vllm_310p_poc", {}).get("capabilities", []))
                v_rows = []
                for x in vllm_models[:6]:
                    v_rows.append(
                        f"| {x.get('model','')} | {x.get('type','')} | {','.join(x.get('precision',[])) or '-'} | {capabilities or '见说明'} |"
                    )
                return (
                    "好的，你要只看 vLLM 310P，那我就给你单路线版本。\n"
                    "先看这张表：\n"
                    "| 模型 | 类型 | 精度 | 关键能力 |\n"
                    "| --- | --- | --- | --- |\n"
                    + ("\n".join(v_rows) if v_rows else "| 当前知识库未覆盖 | - | - | - |")
                    + "\n如果你想切回全量（MindIE + vLLM）视图，直接说“给我全量”就行。"
                )

            rows = []
            # MindIE 文本
            for x in text_models[:6]:
                rows.append(
                    f"| MindIE | 文本 | {x.get('model','')} | {x.get('context_length','-')} | {','.join(x.get('quantization',[])) or '-'} | {x.get('hardware','-')} |"
                )
            # MindIE 多模态
            for x in mm_models[:5]:
                rows.append(
                    f"| MindIE | 多模态 | {x.get('model','')} | - | {','.join(x.get('quantization',[])) or '-'} | {x.get('hardware','-')} |"
                )
            # vLLM 310P
            for x in vllm_models[:4]:
                rows.append(
                    f"| vLLM 310P POC | {x.get('type','')} | {x.get('model','')} | - | {','.join(x.get('precision',[])) or '-'} | 310P POC |"
                )

            conclusion = (
                "你这个问题更偏 MindIE/300I Duo 场景，我先按这条线给你梳理。"
                if ask_300i
                else "按你的问题，我先给你全量视图（MindIE + vLLM 310P POC）。"
            )
            return (
                f"{conclusion}\n"
                "你先看表格，后面如果要我可以再按你的目标做精简版：\n"
                "| 路线 | 大类 | 模型 | 上下文 | 量化/精度 | 硬件/说明 |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                + ("\n".join(rows) if rows else "| - | - | 当前知识库未覆盖 | - | - | - |")
                + "\n"
                "你告诉我你的目标硬件（300I Duo 或 310P）和目标模型，我就能直接给你最短部署路径。"
            )

        pick_points = points[:3]
        bullets = "\n".join(f"- {x}" for x in pick_points)
        return (
            "我先给你最有用的结论：\n\n"
            f"{bullets}\n\n"
            "你可以继续说你的目标，我会直接给你可执行方案。"
        )

    def _review(self, answer: str, evidences: list[Evidence]) -> list[str]:
        notes: list[str] = []
        if "可能" in answer or "大概" in answer:
            notes.append("回答包含不确定表达，建议补充明确证据。")
        if not evidences:
            notes.append("未检索到证据，建议用户换关键词。")
            return notes
        evidence_text = " ".join(x.body for x in evidences[:6])
        for probe in ["W8A8SC", "full decode only", "TP 并行", "Atlas 300I Duo"]:
            if probe in answer and probe not in evidence_text:
                notes.append(f"检测到术语 `{probe}` 可能缺少直接证据。")
        if not notes:
            notes.append("审校通过：回答与检索证据一致。")
        return notes

    def _clean_answer(self, text: str) -> str:
        """清理不希望展示给用户的尾注字段。"""
        if not text:
            return ""
        banned_keywords = ("信息来源", "处理模式")
        cleaned: list[str] = []
        pending_sep = False
        for line in text.splitlines():
            striped = line.strip()
            if striped == "---":
                pending_sep = True
                continue
            if any(k in striped for k in banned_keywords):
                continue
            # 若分隔线后是空行，也一并去掉，避免尾部残留格式痕迹
            if pending_sep and not striped:
                continue
            pending_sep = False
            plain = line
            plain = re.sub(r"^\s*#{1,6}\s*", "", plain)
            plain = re.sub(r"\*\*(.*?)\*\*", r"\1", plain)
            plain = re.sub(r"`([^`]*)`", r"\1", plain)
            plain = re.sub(r"^\s*[-*]\s+", "", plain)
            plain = re.sub(r"^\s*(\d+)\.\s+", r"\1）", plain)
            cleaned.append(plain)
        return "\n".join(cleaned).strip()

    def chat(self, message: str, history: list[dict], cfg: AgentConfig | None = None) -> AgentResult:
        cfg = cfg or AgentConfig()
        quick = message.strip()
        quick_l = quick.lower()
        identity_tokens = ("你是谁", "你是誰", "你叫什么", "你叫啥", "你叫什麼", "介绍下你", "介紹下你")
        greet_tokens = {"你好", "hi", "hello", "在吗", "在嗎", "嗨", "哈喽", "哈囉"}
        if quick in greet_tokens or any(t in quick for t in identity_tokens) or quick_l in greet_tokens:
            return AgentResult(
                answer="我是喵酱，昇腾310芯片智能小助手",
                intent="general",
                plan=["快速问候响应"],
                evidences=[],
                review_notes=["问候类请求已走极速路径。"],
                used_remote=False,
                source_url="",
            )
        query = self._contextual_query(message, history)
        kb, evidences = retrieve_evidence(query, self.kb_path, top_n=max(3, cfg.top_k))
        intent = self._intent(query)
        plan = self._plan(query, intent)
        context = self._format_context(evidences)
        # 模型支持类问题一律走本地结构化模板，避免远端风格漂移
        force_structured_model_answer = intent == "model"
        remote = self._remote_llm(message, history, context, intent, cfg)
        if force_structured_model_answer:
            remote = None
        used_remote = bool(remote)
        answer = remote or self._fallback(kb, evidences, intent, cfg.mode, query)
        answer = self._clean_answer(answer)
        review_notes = self._review(answer, evidences)
        source_url = kb.get("meta", {}).get("mindie_list_url", "")
        formatted = answer
        evidence_payload = [asdict(x) for x in evidences]
        return AgentResult(
            answer=formatted,
            intent=intent,
            plan=plan,
            evidences=evidence_payload,
            review_notes=review_notes,
            used_remote=used_remote,
            source_url=source_url,
        )

