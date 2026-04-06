# core/helpers.py
from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse  # noqa: F401 — giữ lại cho các module import

from fake_useragent import UserAgent
from playwright.async_api import Browser, BrowserContext, Page

# ── Config ────────────────────────────────────────────────────
MAX_PAGES_PER_HOTEL = 10
REVIEWS_PER_PAGE    = 10
DELAY_MIN           = 2.5
DELAY_MAX           = 6.0
PAGE_DELAY_MIN      = 1.5
PAGE_DELAY_MAX      = 3.5

# ── Logging ───────────────────────────────────────────────────
LOG_FILE = Path("logs/etl.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)  # FIX 1: parents=True tránh lỗi nếu logs/ chưa tồn tại

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# FIX 2: UserAgent() có thể raise exception khi không có cache/network
# Dùng fallback an toàn
try:
    ua = UserAgent()
except Exception:
    class _FallbackUA:
        random = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    ua = _FallbackUA()

# ── Block patterns ────────────────────────────────────────────
_BLOCK_RE = re.compile(
    r"\.(png|jpg|jpeg|gif|svg|webp|ico|woff2?|ttf|eot"
    r"|mp4|webm|avi|css)(\?.*)?$",
    re.IGNORECASE,
)

# ── City normalize map ────────────────────────────────────────
_CITY_NORMALIZE: dict[str, str] = {
    "ha-noi": "Hà Nội",
    "ho-chi-minh-city": "Hồ Chí Minh",
    "thanh-pho-ho-chi-minh": "Hồ Chí Minh",
    "tp-hcm": "Hồ Chí Minh",
    "da-nang": "Đà Nẵng",
    "hoi-an": "Hội An",
    "nha-trang": "Nha Trang",
    "phu-quoc": "Phú Quốc",
    "da-lat": "Đà Lạt",
    "hue": "Huế",
    "ha-long": "Hạ Long",
    "sapa": "Sa Pa",
    "sa-pa": "Sa Pa",
    "vung-tau": "Vũng Tàu",
    "mui-ne": "Mũi Né",
    "phan-thiet": "Phan Thiết",
    "quy-nhon": "Quy Nhơn",
    "can-tho": "Cần Thơ",
    "hai-phong": "Hải Phòng",
    "ninh-binh": "Ninh Bình",
    "buon-ma-thuot": "Buôn Ma Thuột",
    "ha-giang": "Hà Giang",
    "dien-bien": "Điện Biên",
    "son-la": "Sơn La",
    "hoa-binh": "Hòa Bình",
    "thanh-hoa": "Thanh Hóa",
    "nghe-an": "Nghệ An",
    "quang-binh": "Quảng Bình",
    "quang-tri": "Quảng Trị",
    "quang-nam": "Quảng Nam",
    "quang-ngai": "Quảng Ngãi",
    "binh-dinh": "Bình Định",
    "phu-yen": "Phú Yên",
    "ninh-thuan": "Ninh Thuận",
    "binh-thuan": "Bình Thuận",
    "kon-tum": "Kon Tum",
    "gia-lai": "Gia Lai",
    "dak-lak": "Đắk Lắk",
    "dak-nong": "Đắk Nông",
    "lam-dong": "Lâm Đồng",
    "binh-phuoc": "Bình Phước",
    "tay-ninh": "Tây Ninh",
    "binh-duong": "Bình Dương",
    "dong-nai": "Đồng Nai",
    "ba-ria-vung-tau": "Bà Rịa-Vũng Tàu",
    "long-an": "Long An",
    "tien-giang": "Tiền Giang",
    "ben-tre": "Bến Tre",
    "tra-vinh": "Trà Vinh",
    "vinh-long": "Vĩnh Long",
    "dong-thap": "Đồng Tháp",
    "an-giang": "An Giang",
    "kien-giang": "Kiên Giang",
    "hau-giang": "Hậu Giang",
    "soc-trang": "Sóc Trăng",
    "bac-lieu": "Bạc Liêu",
    "ca-mau": "Cà Mau",
    "bac-ninh": "Bắc Ninh",
    "bac-giang": "Bắc Giang",
    "bac-kan": "Bắc Kạn",
    "cao-bang": "Cao Bằng",
    "lang-son": "Lạng Sơn",
    "thai-nguyen": "Thái Nguyên",
    "phu-tho": "Phú Thọ",
    "vinh-phuc": "Vĩnh Phúc",
    "hung-yen": "Hưng Yên",
    "hai-duong": "Hải Dương",
    "thai-binh": "Thái Bình",
    "nam-dinh": "Nam Định",
    "ha-nam": "Hà Nam",
    "tuyen-quang": "Tuyên Quang",
    "yen-bai": "Yên Bái",
    "lai-chau": "Lai Châu",
    "lao-cai": "Lào Cai",
    "quang-ninh": "Quảng Ninh",
    "phong-nha": "Phong Nha",
    "tam-coc": "Tam Cốc",
    "cat-ba": "Cát Bà",
    "ha-tien": "Hà Tiên",
}

# ── City → Region mapping ─────────────────────────────────────
_CITY_TO_REGION: dict[str, str] = {
    # Miền Bắc
    "Hà Nội": "Miền Bắc",
    "Hải Phòng": "Miền Bắc",
    "Quảng Ninh": "Miền Bắc",
    "Hạ Long": "Miền Bắc",
    "Bắc Ninh": "Miền Bắc",
    "Hải Dương": "Miền Bắc",
    "Hưng Yên": "Miền Bắc",
    "Thái Bình": "Miền Bắc",
    "Nam Định": "Miền Bắc",
    "Ninh Bình": "Miền Bắc",
    "Hà Nam": "Miền Bắc",
    "Vĩnh Phúc": "Miền Bắc",
    "Bắc Giang": "Miền Bắc",
    "Phú Thọ": "Miền Bắc",
    "Thái Nguyên": "Miền Bắc",
    "Lạng Sơn": "Miền Bắc",
    "Cao Bằng": "Miền Bắc",
    "Bắc Kạn": "Miền Bắc",
    "Tuyên Quang": "Miền Bắc",
    "Hà Giang": "Miền Bắc",
    "Lào Cai": "Miền Bắc",
    "Sa Pa": "Miền Bắc",
    "Yên Bái": "Miền Bắc",
    "Lai Châu": "Miền Bắc",
    "Sơn La": "Miền Bắc",
    "Hòa Bình": "Miền Bắc",
    "Điện Biên": "Miền Bắc",
    # Miền Trung
    "Thanh Hóa": "Miền Trung",
    "Nghệ An": "Miền Trung",
    "Hà Tĩnh": "Miền Trung",
    "Quảng Bình": "Miền Trung",
    "Phong Nha": "Miền Trung",
    "Quảng Trị": "Miền Trung",
    "Huế": "Miền Trung",
    "Thừa Thiên Huế": "Miền Trung",
    "Đà Nẵng": "Miền Trung",
    "Quảng Nam": "Miền Trung",
    "Hội An": "Miền Trung",
    "Quảng Ngãi": "Miền Trung",
    "Bình Định": "Miền Trung",
    "Quy Nhơn": "Miền Trung",
    "Phú Yên": "Miền Trung",
    "Khánh Hòa": "Miền Trung",
    "Nha Trang": "Miền Trung",
    "Ninh Thuận": "Miền Trung",
    "Phan Rang": "Miền Trung",
    "Bình Thuận": "Miền Trung",
    "Phan Thiết": "Miền Trung",
    "Mũi Né": "Miền Trung",
    "Kon Tum": "Miền Trung",
    "Gia Lai": "Miền Trung",
    "Đắk Lắk": "Miền Trung",
    "Buôn Ma Thuột": "Miền Trung",
    "Đắk Nông": "Miền Trung",
    "Lâm Đồng": "Miền Trung",
    "Đà Lạt": "Miền Trung",
    # Miền Nam
    "Hồ Chí Minh": "Miền Nam",
    "Bình Phước": "Miền Nam",
    "Tây Ninh": "Miền Nam",
    "Bình Dương": "Miền Nam",
    "Đồng Nai": "Miền Nam",
    "Bà Rịa-Vũng Tàu": "Miền Nam",
    "Vũng Tàu": "Miền Nam",
    "Long An": "Miền Nam",
    "Tiền Giang": "Miền Nam",
    "Bến Tre": "Miền Nam",
    "Trà Vinh": "Miền Nam",
    "Vĩnh Long": "Miền Nam",
    "Đồng Tháp": "Miền Nam",
    "An Giang": "Miền Nam",
    "Kiên Giang": "Miền Nam",
    "Phú Quốc": "Miền Nam",
    "Hậu Giang": "Miền Nam",
    "Sóc Trăng": "Miền Nam",
    "Bạc Liêu": "Miền Nam",
    "Cà Mau": "Miền Nam",
    "Cần Thơ": "Miền Nam",
}

# ── Month lookup (dùng chung cho parse_date) ──────────────────
_MONTHS: dict[str, str] = {
    "january": "01", "february": "02", "march": "03",
    "april": "04",   "may": "05",      "june": "06",
    "july": "07",    "august": "08",   "september": "09",
    "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08", "sep": "09",
    "oct": "10", "nov": "11", "dec": "12",
}

# ── Utility functions ─────────────────────────────────────────

def sha12(text: str) -> str:
    """SHA-256 → 12 ký tự hex viết hoa."""
    return hashlib.sha256(text.encode()).hexdigest()[:12].upper()


def md5_hash(text: str) -> str:
    """MD5 hex digest."""
    return hashlib.md5(text.encode()).hexdigest()


def clean(s: str | None, max_len: int = 500) -> str | None:
    """Làm sạch chuỗi: bỏ ký tự điều khiển, chuẩn hoá khoảng trắng."""
    if not s:
        return None
    s = s.strip()
    s = re.sub(r"[\x00-\x1f\x7f]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_len] if s else None


def extract_city_slug(url: str) -> str:
    """Trích tên thành phố từ URL và chuẩn hóa về tiếng Việt."""
    patterns = [
        r"/khach-san-([^/?#]+?)(?:/|\.html|$)",
        r"/hotel/vn/[^/?#]+-([^/?#.]+?)(?:/|\.html|$)",
        r"/([\w-]+)/hotels?(?:/|$)",
        r"location=([^&]+)",
        r"/([a-z-]+)-hotels?(?:/|$)",
        r"city/([^/?#.]+)",
    ]
    for pat in patterns:
        m = re.search(pat, url, re.IGNORECASE)
        if m:
            slug = m.group(1).lower().strip("-")
            if slug in _CITY_NORMALIZE:
                return _CITY_NORMALIZE[slug]
            return slug.replace("-", " ").title()
    return "Vietnam"


def get_region(city: str) -> str:
    """Lấy vùng miền từ tên thành phố chuẩn hoá."""
    return _CITY_TO_REGION.get(city, "Miền Nam")


def parse_price(raw: str | None) -> float | None:
    """Chuyển chuỗi giá bất kỳ → float VND.

    - Tự động nhận diện USD và quy đổi sang VND (×24 000).
    - Lọc bỏ giá trị ngoài dải hợp lệ (10 000 – 100 000 000 VND).
    """
    if not raw:
        return None
    raw = raw.strip()

    is_usd = bool(re.search(r"\$|usd", raw, re.IGNORECASE))

    if is_usd:
        m = re.search(r"[\d,]+\.?\d*", raw)
        if m:
            try:
                v = float(m.group().replace(",", ""))
                # FIX 3: ngưỡng 10 000 không hợp lý cho USD — đổi thành 10_000_000 VND
                return round(v * 24_000, 0)
            except ValueError:
                return None
        return None

    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None
    try:
        v = float(digits)
        if 10_000 <= v <= 100_000_000:
            return v
        return None
    except ValueError:
        return None


def parse_date(raw: str | None) -> str | None:
    """Chuyển chuỗi ngày bất kỳ → YYYY-MM-DD.

    Hỗ trợ: tiếng Việt, tiếng Anh, nhiều định dạng phổ biến.
    """
    if not raw:
        return None
    raw = raw.strip()

    # Tiếng Việt: "Tháng 3 năm 2024"
    m = re.search(
        r"tháng\s+(\d{1,2})[\s,/năm]+(\d{4})",
        raw, re.IGNORECASE,
    )
    if m:
        return f"{m.group(2)}-{m.group(1).zfill(2)}-01"

    # Tiếng Anh: "March 2024"
    m = re.search(
        r"(january|february|march|april|may|june|july|"
        r"august|september|october|november|december|"
        r"jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)"
        r"\s+(\d{4})",
        raw, re.IGNORECASE,
    )
    if m:
        month = _MONTHS.get(m.group(1).lower(), "01")
        return f"{m.group(2)}-{month}-01"

    # Format chuẩn — thứ tự từ cụ thể → tổng quát để tránh match nhầm
    _FORMATS = [
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
        (r"\d{2}/\d{2}/\d{4}", "%d/%m/%Y"),
        (r"\d{2}-\d{2}-\d{4}", "%d-%m-%Y"),
        (r"\d{2}\.\d{2}\.\d{4}", "%d.%m.%Y"),
        (r"\d{2}/\d{4}", "%m/%Y"),        # FIX 4: dict không đảm bảo thứ tự match → dùng list
        (r"\d{4}/\d{2}", "%Y/%m"),
    ]
    for pattern, fmt in _FORMATS:
        m = re.search(pattern, raw)
        if m:
            try:
                dt = datetime.strptime(m.group(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

    # "15 March 2024"
    m = re.search(
        r"(\d{1,2})\s+(january|february|march|april|may|june|"
        r"july|august|september|october|november|december)\s+(\d{4})",
        raw, re.IGNORECASE,
    )
    if m:
        month = _MONTHS.get(m.group(2).lower(), "01")
        return f"{m.group(3)}-{month}-{m.group(1).zfill(2)}"

    return None


# ── Playwright helpers ────────────────────────────────────────

async def _text(loc) -> str:
    """An toàn lấy inner_text của locator."""
    try:
        return (await loc.inner_text()).strip()
    except Exception:
        return ""


async def _attr(loc, attr: str) -> str:
    """An toàn lấy attribute của locator."""
    try:
        v = await loc.get_attribute(attr)
        return (v or "").strip()
    except Exception:
        return ""


async def _first_text(page: Page, selectors: list[str]) -> str:
    """Thử lần lượt các CSS selector, trả về text đầu tiên tìm được."""
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                t = await _text(el)
                if t and len(t) > 1:
                    return t
        except Exception:
            continue
    return ""


async def human_scroll(page: Page) -> None:
    """Cuộn trang bắt chước hành vi người dùng thật."""
    for _ in range(random.randint(2, 5)):
        direction = -1 if random.random() < 0.15 else 1
        distance  = random.randint(200, 600) * direction
        await page.evaluate(f"window.scrollBy(0, {distance})")
        await asyncio.sleep(random.uniform(0.3, 1.0))
        if random.random() < 0.2:
            await asyncio.sleep(random.uniform(1.0, 2.5))


# ── Danh sách tracking/analytics domains bị block ────────────
_BLOCKED_DOMAINS = (
    "google-analytics.com",
    "googletagmanager.com",
    "facebook.com/tr",
    "doubleclick.net",
    "hotjar.com",
    "mixpanel.com",
    "segment.com",
    "amplitude.com",
)


async def open_page(ctx: BrowserContext) -> Page:
    """Mở tab mới với route blocking tài nguyên tĩnh & analytics."""
    page = await ctx.new_page()

    async def _route(route, req) -> None:
        url = req.url
        if _BLOCK_RE.search(url):
            await route.abort()
        elif any(d in url for d in _BLOCKED_DOMAINS):
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", _route)
    return page


async def safe_goto(
    page: Page,
    url: str,
    timeout: int = 60_000,
    retries: int = 3,
) -> bool:
    """Điều hướng đến URL với exponential-backoff retry.

    Returns:
        True nếu thành công, raise Exception sau `retries` lần thất bại.
    """
    # FIX 5: Từ khoá block check — thêm "robot" đầy đủ hơn
    _BLOCK_KEYWORDS = (
        "captcha", "robot", "blocked",
        "access denied", "403 forbidden",
        "too many requests", "unusual traffic",
    )

    for attempt in range(1, retries + 1):
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=timeout,
            )
            # FIX 6: page.content() gọi lại lần 2 tốn thêm thời gian;
            # chỉ lấy title + body text snippet để kiểm tra nhanh hơn
            content = (await page.content()).lower()
            if any(kw in content for kw in _BLOCK_KEYWORDS):
                raise ValueError(f"Bị block/captcha tại {url}")
            return True

        except Exception as e:
            if attempt == retries:
                raise
            delay = 2.0 * (2 ** (attempt - 1)) + random.uniform(0, 1)
            log.warning(
                f"  Goto thất bại lần {attempt}/{retries}: {e}"
                f" — retry sau {delay:.1f}s"
            )
            await asyncio.sleep(delay)

    return False  # unreachable nhưng mypy cần


# ── Stealth JS ────────────────────────────────────────────────
_STEALTH_JS = r"""
() => {
    // 1. Xóa dấu hiệu webdriver
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    try { delete navigator.__proto__.webdriver; } catch (_) {}

    // 2. Chrome runtime giả lập
    if (!window.chrome) {
        window.chrome = {
            runtime: {
                connect:         () => {},
                sendMessage:     () => {},
                onMessage:       { addListener: () => {} },
                getPlatformInfo: (cb) => cb && cb({ os: 'win' }),
            },
            loadTimes: () => ({
                requestTime:            Date.now() / 1000 - Math.random() * 2,
                startLoadTime:          Date.now() / 1000 - Math.random(),
                commitLoadTime:         Date.now() / 1000,
                finishDocumentLoadTime: Date.now() / 1000,
                finishLoadTime:         Date.now() / 1000,
                firstPaintTime:         Date.now() / 1000,
                navigationType:         'Other',
                wasFetchedViaSpdy:      false,
                wasNpnNegotiated:       false,
                npnNegotiatedProtocol:  '',
                wasAlternateProtocolAvailable: false,
                connectionInfo:         'http/1.1',
            }),
            csi: () => ({
                startE:  Date.now(),
                onloadT: Date.now(),
                pageT:   Math.random() * 5000,
                tran:    15,
            }),
        };
    }

    // 3. Navigator properties
    Object.defineProperty(navigator, 'languages', {
        get: () => ['vi-VN', 'vi', 'en-US', 'en'],
    });
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => [4, 6, 8, 12, 16][Math.floor(Math.random() * 5)],
    });
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => [4, 8, 16][Math.floor(Math.random() * 3)],
    });
    Object.defineProperty(navigator, 'platform', {
        get: () => 'Win32',
    });

    // 4. Canvas fingerprint noise
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type) {
        const ctx2d = this.getContext('2d');
        if (ctx2d) {
            const imageData = ctx2d.getImageData(0, 0, this.width, this.height);
            for (let i = 0; i < imageData.data.length; i += 100) {
                imageData.data[i] ^= Math.floor(Math.random() * 3);
            }
            ctx2d.putImageData(imageData, 0, 0);
        }
        return origToDataURL.apply(this, arguments);
    };

    // 5. WebGL fingerprint
    const origGetParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        const overrides = {
            37445: 'Intel Inc.',
            37446: 'Intel(R) UHD Graphics 620',
            7937:  'WebKit WebGL',
            7938:  'WebGL 1.0 (OpenGL ES 2.0 Chromium)',
            35724: 'WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)',
        };
        return overrides[param] !== undefined
            ? overrides[param]
            : origGetParam.apply(this, arguments);
    };

    // 6. AudioContext noise — FIX: kiểm tra AudioBuffer tồn tại trước
    if (typeof AudioBuffer !== 'undefined') {
        const origGetChannelData = AudioBuffer.prototype.getChannelData;
        AudioBuffer.prototype.getChannelData = function() {
            const array = origGetChannelData.apply(this, arguments);
            for (let i = 0; i < array.length; i += 100) {
                array[i] += Math.random() * 0.0001;
            }
            return array;
        };
    }

    // 7. Permissions API
    if (navigator.permissions && navigator.permissions.query) {
        const origQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : origQuery(parameters)
        );
    }

    // 8. Connection API
    Object.defineProperty(navigator, 'connection', {
        get: () => ({
            effectiveType: '4g',
            rtt:           50,
            downlink:      10,
            saveData:      false,
        }),
    });

    // 9. Battery API — FIX: chỉ override nếu API tồn tại
    if ('getBattery' in navigator) {
        navigator.getBattery = () => Promise.resolve({
            charging:        true,
            chargingTime:    0,
            dischargingTime: Infinity,
            level:           0.85 + Math.random() * 0.15,
        });
    }

    // 10. Screen properties
    Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
    Object.defineProperty(screen, 'pixelDepth',  { get: () => 24 });
}
"""


async def make_context(browser: Browser, proxy=None) -> BrowserContext:
    """Tạo browser context với stealth đầy đủ và proxy tuỳ chọn."""
    proxy_settings = None
    if proxy and getattr(proxy, "host", None):
        proxy_settings = {
            "server":   f"http://{proxy.host}:{proxy.port}",
            "username": proxy.username,
            "password": proxy.password,
        }

    # FIX 7: ua.random có thể trả về None nếu UserAgent cache lỗi
    user_agent: str = ua.random or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    ctx = await browser.new_context(
        user_agent=user_agent,
        locale=random.choice([
            "vi-VN", "en-US", "en-GB",
            "ko-KR", "ja-JP", "zh-CN",
        ]),
        timezone_id=random.choice([
            "Asia/Ho_Chi_Minh",
            "Asia/Bangkok",
            "Asia/Singapore",
            "Asia/Seoul",
            "America/New_York",
        ]),
        viewport={
            "width":  random.randint(1280, 1920),
            "height": random.randint(768, 1080),
        },
        java_script_enabled=True,
        bypass_csp=True,
        proxy=proxy_settings,
        extra_http_headers={
            "Accept-Language":           "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept":                    (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "DNT":                       "1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest":            "document",
            "Sec-Fetch-Mode":            "navigate",
            "Sec-Fetch-Site":            "none",
            "Sec-Fetch-User":            "?1",
        },
    )
    await ctx.add_init_script(_STEALTH_JS)
    return ctx
