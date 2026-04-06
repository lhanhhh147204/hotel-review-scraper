# nlp/language_detect.py
from __future__ import annotations

import re
import logging
from functools import lru_cache

log = logging.getLogger(__name__)

# ── Thử import langdetect ─────────────────────────────────────
try:
    from langdetect import detect, DetectorFactory
    from langdetect.lang_detect_exception import LangDetectException
    DetectorFactory.seed = 42  # reproducible
    HAS_LANGDETECT = True
    log.info("✅  langdetect loaded")
except ImportError:
    HAS_LANGDETECT = False
    log.warning("⚠️  langdetect không có — dùng heuristic")


class LanguageDetector:
    """
    Phát hiện ngôn ngữ review để phân loại
    khách Việt vs khách quốc tế.
    """

    _LANG_MAP: dict[str, str] = {
        "vi":    "vi",
        "en":    "en",
        "zh-cn": "zh",
        "zh-tw": "zh",
        "zh":    "zh",
        "ko":    "ko",
        "ja":    "ja",
        "fr":    "fr",
        "de":    "de",
        "ru":    "ru",
        "th":    "th",
        "ms":    "ms",
        "id":    "id",
        "es":    "es",
        "it":    "it",
        "pt":    "pt",
        "ar":    "ar",
        "nl":    "nl",
        "pl":    "pl",
        "sv":    "sv",
    }

    _LANG_TO_GUEST: dict[str, str] = {
        "vi": "Khách Việt",
        "en": "Khách Anh/Mỹ",
        "zh": "Khách Trung Quốc",
        "ko": "Khách Hàn Quốc",
        "ja": "Khách Nhật Bản",
        "fr": "Khách Pháp",
        "de": "Khách Đức",
        "ru": "Khách Nga",
        "th": "Khách Thái Lan",
        "ms": "Khách Malaysia",
        "id": "Khách Indonesia",
        "es": "Khách Tây Ban Nha",
        "it": "Khách Ý",
        "pt": "Khách Bồ Đào Nha",
        "ar": "Khách Ả Rập",
        "nl": "Khách Hà Lan",
    }

    _CHAR_PATTERNS: dict[str, re.Pattern] = {
        "vi": re.compile(
            r"[àáâãèéêìíòóôõùúýăđơưạảấầẩẫậắằẳẵặẹẻẽế"
            r"ềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]",
            re.IGNORECASE,
        ),
        "zh": re.compile(r"[\u4e00-\u9fff]"),
        "ko": re.compile(r"[\uac00-\ud7af\u1100-\u11ff]"),
        "ja": re.compile(r"[\u3040-\u309f\u30a0-\u30ff]"),
        "ar": re.compile(r"[\u0600-\u06ff]"),
        "ru": re.compile(r"[\u0400-\u04ff]"),
        "th": re.compile(r"[\u0e00-\u0e7f]"),
    }

    @lru_cache(maxsize=50_000)
    def detect(self, text: str) -> str:
        """
        Phát hiện ngôn ngữ.
        Returns: mã ngôn ngữ chuẩn hóa (vi/en/zh/ko/ja/...)
        """
        if not text or len(text.strip()) < 5:
            return "vi"

        text_clean = text.strip()

        # ── Heuristic nhanh bằng ký tự đặc trưng ─────────────
        for lang, pattern in self._CHAR_PATTERNS.items():
            matches = pattern.findall(text_clean)
            ratio   = len(matches) / max(len(text_clean), 1)
            if ratio > 0.15:
                return lang

        # ── langdetect cho Latin script ───────────────────────
        if HAS_LANGDETECT:
            try:
                detected = detect(text_clean)
                return self._LANG_MAP.get(detected, detected)
            except LangDetectException:
                pass

        # ── Fallback: kiểm tra từ khóa tiếng Việt ────────────
        vi_keywords = {
            "phòng", "khách sạn", "dịch vụ", "nhân viên",
            "sạch", "đẹp", "tốt", "tệ", "hài lòng",
            "giá", "vị trí", "ăn sáng", "hồ bơi",
        }
        low      = text_clean.lower()
        vi_count = sum(1 for kw in vi_keywords if kw in low)
        if vi_count >= 2:
            return "vi"

        return "en"  # default Latin

    def detect_guest_type(self, text: str) -> str:
        """Phát hiện loại khách từ nội dung review."""
        lang = self.detect(text)
        return self._LANG_TO_GUEST.get(lang, "Khách Quốc Tế Khác")

    def batch_detect(self, texts: list[str]) -> list[str]:
        """Phát hiện ngôn ngữ hàng loạt."""
        return [self.detect(t) for t in texts]


# ── Singleton & wrapper functions ─────────────────────────────
_detector = LanguageDetector()


def detect_language(text: str) -> str:
    return _detector.detect(text)


def detect_guest_type(text: str) -> str:
    return _detector.detect_guest_type(text)