# nlp/sentiment.py
from __future__ import annotations

import re
import logging
from functools import lru_cache
from typing import NamedTuple

log = logging.getLogger(__name__)

# ── Thử import underthesea ────────────────────────────────────
try:
    from underthesea import sentiment as uts_sentiment
    from underthesea import word_tokenize
    HAS_UNDERTHESEA = True
    log.info("✅  underthesea loaded — NLP tiếng Việt nâng cao")
except ImportError:
    HAS_UNDERTHESEA = False
    log.warning("⚠️  underthesea không có — dùng keyword matching")


class SentimentLexicon:
    """Từ điển cảm xúc đa ngôn ngữ."""

    VI_POS = {
        "tuyệt vời", "xuất sắc", "hoàn hảo", "tuyệt",
        "tốt", "rất tốt", "khá tốt", "ổn", "được",
        "hài lòng", "rất hài lòng", "hài lòng lắm",
        "thích", "rất thích", "yêu thích",
        "thân thiện", "nhiệt tình", "chu đáo", "chuyên nghiệp",
        "tận tâm", "lịch sự", "niềm nở", "vui vẻ",
        "sạch", "sạch sẽ", "sạch bóng", "tinh tươm",
        "đẹp", "rất đẹp", "xinh", "sang trọng", "hiện đại",
        "rộng", "rộng rãi", "thoáng", "thoáng mát",
        "yên tĩnh", "yên bình", "tĩnh lặng",
        "tiện lợi", "thuận tiện", "gần", "trung tâm",
        "xứng đáng", "hợp lý", "giá tốt", "rẻ", "tiết kiệm",
        "ngon", "rất ngon", "ngon miệng", "tuyệt ngon",
        "sẽ quay lại", "sẽ giới thiệu", "recommend",
    }

    VI_NEG = {
        "tệ", "rất tệ", "tệ lắm", "kém", "dở",
        "thất vọng", "rất thất vọng", "thất vọng lắm",
        "không hài lòng", "không ổn", "không được",
        "thô lỗ", "lạnh lùng", "chậm", "chậm chạp",
        "thiếu chuyên nghiệp", "vô lễ", "cáu kỉnh",
        "bẩn", "dơ", "hôi", "mốc", "ẩm mốc",
        "xấu", "cũ", "xuống cấp", "hỏng", "hư",
        "chật", "chật chội", "tối", "tối tăm",
        "ồn", "ồn ào", "náo nhiệt",
        "đắt", "đắt đỏ", "chặt chém", "không xứng",
        "dở", "không ngon", "nhạt", "mặn", "cứng",
        "gián", "chuột", "muỗi", "côn trùng",
        "mất điện", "mất nước", "wifi yếu", "không có wifi",
    }

    EN_POS = {
        "excellent", "amazing", "wonderful", "fantastic",
        "great", "good", "nice", "lovely", "beautiful",
        "perfect", "outstanding", "superb", "brilliant",
        "clean", "spotless", "immaculate",
        "friendly", "helpful", "professional", "attentive",
        "comfortable", "cozy", "spacious", "quiet",
        "convenient", "central", "accessible",
        "value", "affordable", "reasonable", "worth",
        "delicious", "tasty", "yummy",
        "recommend", "recommended", "will return",
        "love", "loved", "enjoy", "enjoyed",
    }

    EN_NEG = {
        "terrible", "awful", "horrible", "dreadful",
        "bad", "poor", "disappointing", "disappointed",
        "dirty", "filthy", "smelly", "moldy",
        "rude", "unfriendly", "unhelpful", "slow",
        "noisy", "loud", "cramped", "small", "dark",
        "expensive", "overpriced", "ripoff",
        "broken", "damaged", "old", "outdated",
        "cockroach", "bug", "insect", "rat", "mouse",
        "no wifi", "weak wifi", "no hot water",
        "worst", "never again", "avoid",
    }

    KO_POS = {
        "좋아요", "훌륭해요", "깨끗해요", "친절해요",
        "편안해요", "만족해요", "추천해요", "최고예요",
    }
    KO_NEG = {
        "나빠요", "실망이에요", "더러워요", "시끄러워요",
        "불친절해요", "비싸요", "최악이에요",
    }

    ZH_POS = {
        "很好", "非常好", "干净", "友好", "舒适",
        "满意", "推荐", "完美", "优秀", "棒",
    }
    ZH_NEG = {
        "很差", "失望", "脏", "吵", "贵",
        "不好", "差劲", "最差", "避免",
    }

    NEGATION = {
        "không", "chẳng", "chưa", "chả", "đừng",
        "chớ", "không hề", "không chút", "chẳng hề",
        "không có", "không được", "không thể",
        "not", "never", "no", "without", "lack",
        "doesn't", "don't", "didn't", "isn't",
        "wasn't", "weren't", "can't", "couldn't",
        "won't", "wouldn't", "shouldn't",
        "안", "못", "없어요", "아니에요",
        "不", "没有", "无", "别",
    }

    STRONG_POS_PHRASES = {
        "tuyệt vời lắm", "cực kỳ tốt", "rất rất tốt",
        "highly recommend", "absolutely perfect",
        "exceeded expectations", "will definitely return",
        "best hotel", "best experience",
        "5 sao", "5 star", "10/10",
    }

    STRONG_NEG_PHRASES = {
        "rất tệ", "cực kỳ tệ", "tệ nhất", "tệ hại",
        "never again", "worst experience", "waste of money",
        "do not recommend", "stay away", "avoid at all costs",
        "0 sao", "0 star", "0/10",
    }


class SentimentResult(NamedTuple):
    label:      str    # Tích cực / Tiêu cực / Trung lập
    pos_score:  float
    neg_score:  float
    confidence: float  # 0.0 → 1.0


class SentimentAnalyzer:
    """
    Phân tích cảm xúc đa ngôn ngữ.
    Ưu tiên: underthesea (VI) → keyword matching.
    """

    WINDOW = 4  # số token sau từ phủ định cần kiểm tra

    def __init__(self):
        self.lexicon  = SentimentLexicon()
        self._all_pos = (
            self.lexicon.VI_POS
            | self.lexicon.EN_POS
            | self.lexicon.KO_POS
            | self.lexicon.ZH_POS
        )
        self._all_neg = (
            self.lexicon.VI_NEG
            | self.lexicon.EN_NEG
            | self.lexicon.KO_NEG
            | self.lexicon.ZH_NEG
        )

    @lru_cache(maxsize=10_000)
    def analyse(
            self,
            text: str,
            lang: str = "vi",
    ) -> SentimentResult:
        if not text or not text.strip():
            return SentimentResult("Trung lập", 0.0, 0.0, 0.0)

        # ── Thử underthesea cho tiếng Việt ───────────────────
        if HAS_UNDERTHESEA and lang in ("vi", "vi-VN"):
            try:
                result    = uts_sentiment(text)
                label_map = {
                    "positive": "Tích cực",
                    "negative": "Tiêu cực",
                    "neutral":  "Trung lập",
                }
                label = label_map.get(result, "Trung lập")
                return SentimentResult(label, 0.0, 0.0, 0.85)
            except Exception:
                pass  # fallback xuống keyword matching

        # ── Keyword matching với xử lý phủ định ──────────────
        return self._keyword_analyse(text)

    def _tokenize(self, text: str) -> list[str]:
        """Tách token đơn giản."""
        if HAS_UNDERTHESEA:
            try:
                return (
                    word_tokenize(text.lower(), format="text")
                    .split()
                )
            except Exception:
                pass
        return re.sub(r"[^\w\s]", " ", text.lower()).split()

    def _keyword_analyse(self, text: str) -> SentimentResult:
        low    = text.lower()
        tokens = self._tokenize(text)
        pos    = 0.0
        neg    = 0.0

        # ── Kiểm tra cụm từ mạnh trước ───────────────────────
        for phrase in self.lexicon.STRONG_POS_PHRASES:
            if phrase in low:
                pos += 2.0
        for phrase in self.lexicon.STRONG_NEG_PHRASES:
            if phrase in low:
                neg += 2.0

        # ── Kiểm tra từng token với cửa sổ phủ định ─────────
        for i, token in enumerate(tokens):
            window_start = max(0, i - self.WINDOW)
            preceding    = tokens[window_start:i]
            is_negated   = any(
                neg_word in " ".join(preceding)
                for neg_word in self.lexicon.NEGATION
            )

            if token in self._all_pos:
                if is_negated:
                    neg += 1.0   # "không tốt" → tiêu cực
                else:
                    pos += 1.0

            elif token in self._all_neg:
                if is_negated:
                    pos += 0.5   # "không tệ" → hơi tích cực
                else:
                    neg += 1.0

        # ── Tính confidence ───────────────────────────────────
        total = pos + neg
        if total == 0:
            return SentimentResult("Trung lập", 0.0, 0.0, 0.0)

        confidence = abs(pos - neg) / total

        if pos > neg:
            return SentimentResult("Tích cực", pos, neg, confidence)
        if neg > pos:
            return SentimentResult("Tiêu cực", pos, neg, confidence)
        return SentimentResult("Trung lập", pos, neg, confidence)

    def batch_analyse(
            self,
            texts: list[tuple[str, str]],  # [(text, lang), ...]
    ) -> list[SentimentResult]:
        """Phân tích hàng loạt — tối ưu cho bulk insert."""
        return [self.analyse(text, lang) for text, lang in texts]


# ── Singleton & wrapper functions ─────────────────────────────
_analyzer = SentimentAnalyzer()


def analyse_sentiment(text: str, lang: str = "vi") -> str:
    """Hàm wrapper tương thích ngược với code cũ."""
    return _analyzer.analyse(text, lang).label


def analyse_sentiment_full(
        text: str,
        lang: str = "vi",
) -> SentimentResult:
    """Trả về kết quả đầy đủ gồm cả confidence."""
    return _analyzer.analyse(text, lang)