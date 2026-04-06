# nlp/sentiment.py
"""
Phân tích cảm xúc (sentiment analysis) đa ngôn ngữ cho reviews khách sạn.
Ưu tiên: underthesea (VI) → keyword matching fallback.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

log = logging.getLogger(__name__)

# ── Import thư viện NLP ────────────────────────────────────────────
try:
    from underthesea import sentiment as uts_sentiment
    from underthesea import word_tokenize
    HAS_UNDERTHESEA = True
    log.info("✅ underthesea loaded — NLP tiếng Việt nâng cao")
except ImportError:
    HAS_UNDERTHESEA = False
    log.warning("⚠️ underthesea không có — dùng keyword matching fallback")

try:
    from langdetect import detect, DetectorFactory
    DetectorFactory.seed = 42
    HAS_LANGDETECT = True
except ImportError:
    HAS_LANGDETECT = False


# ── Sentiment Lexicon ──────────────────────────────────────────────
class SentimentLexicon:
    """
    Từ điển cảm xúc đa ngôn ngữ chuẩn hóa.
    Hỗ trợ: Tiếng Việt, Anh, Hàn, Trung Quốc.
    """

    VI_POS = {
        # Tổng thể
        "tuyệt vời", "xuất sắc", "hoàn hảo", "tuyệt",
        "tốt", "rất tốt", "khá tốt", "ổn", "được",
        
        # Cảm giác / Hài lòng
        "hài lòng", "rất hài lòng", "hài lòng lắm",
        "thích", "rất thích", "yêu thích", "tuyệt vời",
        
        # Dịch vụ
        "thân thiện", "nhiệt tình", "chu đáo", "chuyên nghiệp",
        "tận tâm", "lịch sự", "niềm nở", "vui vẻ",
        "phục vụ tốt", "tận tình",
        
        # Phòng / Cơ sở
        "sạch", "sạch sẽ", "sạch bóng", "tinh tươm",
        "đẹp", "rất đẹp", "xinh", "sang trọng", "hiện đại",
        "rộng", "rộng rãi", "thoáng", "thoáng mát",
        
        # Chất lượng
        "yên tĩnh", "yên bình", "tĩnh lặng",
        "tiện lợi", "thuận tiện", "gần", "trung tâm",
        
        # Giá cả
        "xứng đáng", "hợp lý", "giá tốt", "rẻ", "tiết kiệm",
        
        # Ăn uống
        "ngon", "rất ngon", "ngon miệng", "tuyệt ngon", "ngon lắm",
        
        # Sẵn sàng quay lại
        "sẽ quay lại", "sẽ giới thiệu", "recommend", "cực kỳ tốt",
    }

    VI_NEG = {
        # Tổng thể
        "tệ", "rất tệ", "tệ lắm", "kém", "dở", "lộn xộn",
        
        # Không hài lòng
        "thất vọng", "rất thất vọng", "thất vọng lắm",
        "không hài lòng", "không ổn", "không được",
        
        # Dịch vụ
        "thô lỗ", "lạnh lùng", "chậm", "chậm chạp",
        "thiếu chuyên nghiệp", "vô lễ", "cáu kỉnh", "xỉ vả",
        
        # Vệ sinh
        "bẩn", "dơ", "hôi", "mốc", "ẩm mốc", "không sạch",
        
        # Phòng / Cơ sở
        "xấu", "cũ", "xuống cấp", "hỏng", "hư", "nát",
        "chật", "chật chội", "tối", "tối tăm", "tư tối",
        
        # Âm thanh
        "ồn", "ồn ào", "náo nhiệt", "ồn ào lắm",
        
        # Giá cả
        "đắt", "đắt đỏ", "chặt chém", "không xứng", "cắt cổ",
        
        # Ăn uống
        "dở", "không ngon", "nhạt", "mặn", "cứng", "tệ",
        
        # Côn trùng & vấn đề
        "gián", "chuột", "muỗi", "côn trùng", "bọ",
        "mất điện", "mất nước", "wifi yếu", "không có wifi",
        "bồn cầu bị", "tắc", "nước bẩn",
    }

    EN_POS = {
        "excellent", "amazing", "wonderful", "fantastic", "fabulous",
        "great", "good", "nice", "lovely", "beautiful", "gorgeous",
        "perfect", "outstanding", "superb", "brilliant", "awesome",
        "clean", "spotless", "immaculate", "pristine",
        "friendly", "helpful", "professional", "attentive", "courteous",
        "comfortable", "cozy", "spacious", "quiet", "peaceful",
        "convenient", "central", "accessible", "well-located",
        "value", "affordable", "reasonable", "worth", "bargain",
        "delicious", "tasty", "yummy", "scrumptious",
        "recommend", "recommended", "will return", "coming back",
        "love", "loved", "enjoy", "enjoyed", "impressed",
    }

    EN_NEG = {
        "terrible", "awful", "horrible", "dreadful", "disgusting",
        "bad", "poor", "disappointing", "disappointed", "let down",
        "dirty", "filthy", "smelly", "moldy", "gross",
        "rude", "unfriendly", "unhelpful", "slow", "inattentive",
        "noisy", "loud", "cramped", "small", "dark", "dingy",
        "expensive", "overpriced", "ripoff", "overcharge",
        "broken", "damaged", "old", "outdated", "worn",
        "cockroach", "bug", "insect", "rat", "mouse", "pest",
        "no wifi", "weak wifi", "no hot water", "no power",
        "worst", "never again", "avoid", "waste of money",
    }

    KO_POS = {
        "좋아요", "훌륭해요", "깨끗해요", "친절해요",
        "편안해요", "만족해요", "추천해요", "최고예요",
        "훌륭합니다", "좋습니다", "최고입니다",
    }

    KO_NEG = {
        "나빠요", "실망이에요", "더러워요", "시끄러워요",
        "불친절해요", "비싸요", "최악이에요", "끔찍해요",
    }

    ZH_POS = {
        "很好", "非常好", "干净", "友好", "舒适",
        "满意", "推荐", "完美", "优秀", "棒",
        "很舒服", "非常满意", "值得", "太好了",
    }

    ZH_NEG = {
        "很差", "失望", "脏", "吵", "贵",
        "不好", "差劲", "最差", "避免", "糟糕",
    }

    # Từ phủ định làm đảo chiều cảm xúc
    NEGATION = {
        # Tiếng Việt
        "không", "chẳng", "chưa", "chả", "đừng",
        "chớ", "không hề", "không chút", "chẳng hề",
        "không có", "không được", "không thể", "chẳng có",
        # Tiếng Anh
        "not", "never", "no", "without", "lack",
        "doesn't", "don't", "didn't", "isn't",
        "wasn't", "weren't", "can't", "couldn't",
        "won't", "wouldn't", "shouldn't", "no way",
        # Tiếng Hàn
        "안", "못", "없어요", "아니에요", "없습니다",
        # Tiếng Trung
        "不", "没有", "无", "别", "并非",
    }

    # Cụm từ cảm xúc mạnh (tăng trọng)
    STRONG_POS_PHRASES = {
        "tuyệt vời lắm", "cực kỳ tốt", "rất rất tốt",
        "rất hài lòng", "rất thích", "xuất sắc lắm",
        "highly recommend", "absolutely perfect",
        "exceeded expectations", "will definitely return",
        "best hotel", "best experience", "best stay",
        "5 sao", "5 star", "10/10", "5⭐",
    }

    STRONG_NEG_PHRASES = {
        "rất tệ", "cực kỳ tệ", "tệ nhất", "tệ hại",
        "thất vọng lắm", "thất vọng rất lắm",
        "never again", "worst experience", "waste of money",
        "do not recommend", "stay away", "avoid at all costs",
        "0 sao", "0 star", "0/10", "0⭐",
        "sẽ không quay lại",
    }

    # Rating keywords (nếu text chứa)
    RATING_PATTERN = re.compile(
        r"\b(\d+)/(\d+)|(\d+)\s*sao|⭐+",
        re.IGNORECASE
    )


@dataclass
class SentimentResult:
    """Kết quả phân tích cảm xúc."""
    label: str          # "Tích cực" / "Tiêu cực" / "Trung lập"
    pos_score: float    # Điểm tích cực
    neg_score: float    # Điểm tiêu cực
    confidence: float   # Độ tin cậy [0.0, 1.0]
    raw_sentiment: Optional[str] = None  # Kết quả từ underthesea

    def to_dict(self) -> dict:
        """Chuyển đổi thành dict."""
        return {
            "label": self.label,
            "pos_score": round(self.pos_score, 2),
            "neg_score": round(self.neg_score, 2),
            "confidence": round(self.confidence, 2),
        }


# ── Sentiment Analyzer ─────────────────────────────────────────────
class SentimentAnalyzer:
    """
    Phân tích cảm xúc đa ngôn ngữ với fallback tự động.
    
    Ưu tiên:
    1. underthesea (tiếng Việt)
    2. Keyword matching + negation handling
    """

    WINDOW = 4  # Cửa sổ từ trước từ phủ định

    def __init__(self):
        self.lexicon = SentimentLexicon()
        
        # Tập hợp tất cả từ tích cực/tiêu cực
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

    @lru_cache(maxsize=50_000)
    def analyse(
        self,
        text: str,
        lang: str = "vi",
    ) -> SentimentResult:
        """
        Phân tích cảm xúc text.
        
        Args:
            text: Nội dung review
            lang: Mã ngôn ngữ (vi/en/zh/ko/ja)
            
        Returns:
            SentimentResult với label, scores, confidence
        """
        if not text or not text.strip():
            return SentimentResult(
                label="Trung lập",
                pos_score=0.0,
                neg_score=0.0,
                confidence=0.0
            )

        text_clean = text.strip()

        # ── Ưu tiên 1: underthesea cho tiếng Việt ──────────────
        if HAS_UNDERTHESEA and lang in ("vi", "vi-VN", "vn"):
            result = self._analyse_underthesea(text_clean)
            if result:
                return result

        # ── Ưu tiên 2: Keyword matching ────────────────────────
        return self._analyse_keywords(text_clean)

    def _analyse_underthesea(self, text: str) -> Optional[SentimentResult]:
        """Sử dụng underthesea nếu có."""
        try:
            result = uts_sentiment(text)
            label_map = {
                "positive": "Tích cực",
                "negative": "Tiêu cực",
                "neutral": "Trung lập",
            }
            label = label_map.get(result, "Trung lập")
            
            # Gán điểm dựa trên label
            if label == "Tích cực":
                pos_score, neg_score = 1.0, 0.0
            elif label == "Tiêu cực":
                pos_score, neg_score = 0.0, 1.0
            else:
                pos_score, neg_score = 0.5, 0.5

            return SentimentResult(
                label=label,
                pos_score=pos_score,
                neg_score=neg_score,
                confidence=0.85,
                raw_sentiment=result
            )
        except Exception as e:
            log.debug(f"underthesea error: {e}")
            return None

    def _tokenize(self, text: str) -> list[str]:
        """Tách từ thông minh."""
        if HAS_UNDERTHESEA:
            try:
                return (
                    word_tokenize(text.lower(), format="text")
                    .split()
                )
            except Exception:
                pass

        # Fallback: regex tokenization
        return re.sub(r"[^\w\s]", " ", text.lower()).split()

    def _analyse_keywords(self, text: str) -> SentimentResult:
        """Phân tích bằng keyword matching + negation."""
        text_lower = text.lower()
        tokens = self._tokenize(text)
        
        pos_score = 0.0
        neg_score = 0.0

        # ── 1. Kiểm tra cụm từ mạnh trước ──────────────────────
        for phrase in self.lexicon.STRONG_POS_PHRASES:
            if phrase.lower() in text_lower:
                pos_score += 2.0

        for phrase in self.lexicon.STRONG_NEG_PHRASES:
            if phrase.lower() in text_lower:
                neg_score += 2.0

        # ── 2. Kiểm tra rating (e.g., "5/10", "⭐⭐⭐") ────────
        rating = self._extract_rating(text)
        if rating is not None:
            if rating >= 7:
                pos_score += 1.5
            elif rating <= 3:
                neg_score += 1.5
            # else: 4-6 trung lập

        # ── 3. Kiểm tra từng token với window phủ định ────────
        for i, token in enumerate(tokens):
            # Lấy cửa sổ từ trước (để kiểm tra phủ định)
            window_start = max(0, i - self.WINDOW)
            preceding = tokens[window_start:i]
            
            is_negated = any(
                neg_word in " ".join(preceding)
                for neg_word in self.lexicon.NEGATION
            )

            # Tính điểm
            if token in self._all_pos:
                if is_negated:
                    # "không tốt" → tiêu cực
                    neg_score += 0.8
                else:
                    pos_score += 1.0

            elif token in self._all_neg:
                if is_negated:
                    # "không tệ" → hơi tích cực
                    pos_score += 0.5
                else:
                    neg_score += 1.0

        # ── 4. Tính label & confidence ─────────────────────────
        total = pos_score + neg_score

        if total == 0:
            return SentimentResult(
                label="Trung lập",
                pos_score=0.0,
                neg_score=0.0,
                confidence=0.0
            )

        # Normalize scores
        pos_normalized = pos_score / total if total > 0 else 0
        neg_normalized = neg_score / total if total > 0 else 0

        # Confidence = khoảng cách giữa 2 score
        confidence = abs(pos_normalized - neg_normalized)

        # Xác định label
        if pos_score > neg_score:
            label = "Tích cực"
        elif neg_score > pos_score:
            label = "Tiêu cực"
        else:
            label = "Trung lập"

        return SentimentResult(
            label=label,
            pos_score=pos_normalized,
            neg_score=neg_normalized,
            confidence=confidence
        )

    def _extract_rating(self, text: str) -> Optional[float]:
        """Trích xuất rating số từ text."""
        match = self.lexicon.RATING_PATTERN.search(text)
        if not match:
            return None

        # Trường hợp "X/Y"
        if match.group(1):
            try:
                numerator = float(match.group(1))
                denominator = float(match.group(2))
                if denominator > 0:
                    return (numerator / denominator) * 10
            except (ValueError, ZeroDivisionError):
                pass

        # Trường hợp "X sao"
        if match.group(3):
            try:
                return float(match.group(3))
            except ValueError:
                pass

        # Trường hợp "⭐⭐⭐"
        stars = text.count('⭐')
        if stars > 0:
            return stars

        return None

    def batch_analyse(
        self,
        texts: list[tuple[str, str]],
    ) -> list[SentimentResult]:
        """Phân tích hàng loạt."""
        return [
            self.analyse(text, lang)
            for text, lang in texts
        ]


# ── Singleton Instance ─────────────────────────────────────────────
_analyzer = SentimentAnalyzer()


# ── Public API ─────────────────────────────────────────────────────
def analyse_sentiment(text: str, lang: str = "vi") -> str:
    """
    Wrapper tương thích ngược — trả về chỉ label.
    
    Returns: "Tích cực" | "Tiêu cực" | "Trung lập"
    """
    return _analyzer.analyse(text, lang).label


def analyse_sentiment_full(
    text: str,
    lang: str = "vi",
) -> SentimentResult:
    """
    Trả về kết quả đầy đủ với confidence score.
    
    Returns: SentimentResult(label, pos_score, neg_score, confidence)
    """
    return _analyzer.analyse(text, lang)


def batch_analyse_sentiment(
    texts: list[tuple[str, str]],
) -> list[SentimentResult]:
    """
    Phân tích hàng loạt reviews.
    
    Args:
        texts: List[Tuple[text, language_code]]
        
    Returns: List[SentimentResult]
    """
    return _analyzer.batch_analyse(texts)


def clear_cache() -> None:
    """Xóa bộ nhớ cache."""
    _analyzer.analyse.cache_clear()


# ── Testing & Debug ───────────────────────────────────────────────
if __name__ == "__main__":
    # Test cases
    test_cases = [
        ("Khách sạn tuyệt vời, phòng sạch, nhân viên thân thiện!", "vi"),
        ("Terrible room, dirty and noisy. Never coming back.", "en"),
        ("Phòng xấu, dơ bẩn, nhân viên vô lễ. Không hài lòng!", "vi"),
        ("Amazing hotel! 5/5 stars, highly recommend!", "en"),
        ("좋아요. 친절해요. 다시 올게요!", "ko"),
        ("很好，非常满意，推荐", "zh"),
        ("không tốt lắm", "vi"),  # negation case
    ]

    print("=" * 70)
    print("SENTIMENT ANALYSIS TEST")
    print("=" * 70)

    for text, lang in test_cases:
        result = analyse_sentiment_full(text, lang)
        print(f"\n📝 Text: {text[:50]}...")
        print(f"   Lang: {lang}")
        print(f"   Label: {result.label}")
        print(f"   Scores: (+{result.pos_score:.2f} | -{result.neg_score:.2f})")
        print(f"   Confidence: {result.confidence:.2%}")
