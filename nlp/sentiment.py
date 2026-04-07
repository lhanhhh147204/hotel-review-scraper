# nlp/sentiment.py
from __future__ import annotations

import os
import json
import logging
from functools import lru_cache
from typing import NamedTuple

from groq import Groq

log = logging.getLogger(__name__)

# ── Groq client ───────────────────────────────────────────────
_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
_MODEL  = "llama3-8b-8192"   # nhanh + miễn phí trên Groq


# ── Public data classes (giữ nguyên để tương thích) ──────────

class SentimentLexicon:
    """
    Giữ lại class này để không phá vỡ các import hiện có.
    """
    VI_POS: set[str] = set()
    VI_NEG: set[str] = set()
    EN_POS: set[str] = set()
    EN_NEG: set[str] = set()
    KO_POS: set[str] = set()
    KO_NEG: set[str] = set()
    ZH_POS: set[str] = set()
    ZH_NEG: set[str] = set()
    NEGATION: set[str] = set()
    STRONG_POS_PHRASES: set[str] = set()
    STRONG_NEG_PHRASES: set[str] = set()


class SentimentResult(NamedTuple):
    label:      str
    pos_score:  float
    neg_score:  float
    confidence: float


# ── LLM prompt ───────────────────────────────────────────────

_SYSTEM_PROMPT = """Bạn là chuyên gia phân tích cảm xúc (sentiment analysis) cho đánh giá khách sạn.
Trả về JSON đúng cấu trúc (không markdown, không giải thích):

{
  "label": "Tích cực" | "Tiêu cực" | "Trung lập",
  "pos_score": <float 0-10>,
  "neg_score": <float 0-10>,
  "confidence": <float 0-1>
}

Quy tắc:
- Tích cực = khen ngợi
- Tiêu cực = phàn nàn
- Trung lập = không rõ
- Hiểu phủ định: "không tốt" = tiêu cực
- Hỗ trợ đa ngôn ngữ
"""


# ── LLM call ─────────────────────────────────────────────────

def _call_llm(text: str, lang: str = "vi") -> SentimentResult:

    prompt = f"[lang={lang}]\n{text}"

    try:

        response = _client.chat.completions.create(
            model=_MODEL,
            temperature=0,
            max_tokens=200,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
        )

        raw = response.choices[0].message.content.strip()

        data = json.loads(raw)

        return SentimentResult(
            label=data.get("label", "Trung lập"),
            pos_score=float(data.get("pos_score", 0.0)),
            neg_score=float(data.get("neg_score", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
        )

    except Exception as exc:

        log.error("Groq sentiment error: %s", exc)

        return SentimentResult("Trung lập", 0.0, 0.0, 0.0)


# ── SentimentAnalyzer ────────────────────────────────────────

class SentimentAnalyzer:

    @lru_cache(maxsize=10_000)
    def analyse(self, text: str, lang: str = "vi") -> SentimentResult:

        if not text or not text.strip():
            return SentimentResult("Trung lập", 0.0, 0.0, 0.0)

        return _call_llm(text, lang)

    def batch_analyse(self, texts: list[tuple[str, str]]) -> list[SentimentResult]:

        return [self.analyse(text, lang) for text, lang in texts]


# ── Singleton ────────────────────────────────────────────────

_analyzer = SentimentAnalyzer()


def analyse_sentiment(text: str, lang: str = "vi") -> str:
    return _analyzer.analyse(text, lang).label


def analyse_sentiment_full(text: str, lang: str = "vi") -> SentimentResult:
    return _analyzer.analyse(text, lang)
