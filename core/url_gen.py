 url=https://github.com/lhanhhh147204/hotel-review-scraper/blob/main/core/url_gen.py
# core/url_gen.py
"""
URL Generation & Listing Page Scraping
========================================
Sinh listing URLs từ các platform (Booking, Agoda, TripAdvisor, etc.)
Trích xuất hotel URLs từ listing pages.
"""

from __future__ import annotations

import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Callable
from urllib.parse import quote, urljoin
from collections import defaultdict

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from core.helpers import _attr, _text

log = logging.getLogger(__name__)


# ── Data Models ────────────────────────────────────────────────────
@dataclass
class URLGeneratorConfig:
    """Cấu hình cho URL Generator."""
    
    # Ngày check-in/check-out mặc định
    default_checkin: str = "2025-06-01"
    default_checkout: str = "2025-06-02"
    
    # Max pages
    max_pages_booking: int = 10
    max_pages_agoda: int = 10
    max_pages_tripadvisor: int = 5
    max_pages_ivivu: int = 5
    max_pages_mytour: int = 5
    max_pages_traveloka: int = 5
    
    # Google Maps queries per city
    google_maps_queries: int = 5
    
    # Timeouts (ms)
    page_timeout: int = 30_000
    wait_timeout: int = 5_000


@dataclass
class ListingScrapResult:
    """Kết quả scraping 1 trang listing."""
    platform: str
    url: str
    urls_found: int
    urls_extracted: list[str] = field(default_factory=list)
    error: Optional[str] = None
    duration: float = 0.0
    
    @property
    def success(self) -> bool:
        return self.error is None


# ── URL Generator ────────────────────────────────��─────────────────
class URLGenerator:
    """
    Sinh listing URLs cho các platform booking.
    Hỗ trợ: Booking, Agoda, TripAdvisor, iVIVU, MyTour, Traveloka, Google Maps.
    """

    # Mapping thành phố → slug (chuẩn hóa)
    _CITY_SLUGS: dict[str, dict[str, str]] = {
        # Tỉnh: { platform: slug }
        "Hà Nội": {
            "booking": "hanoi",
            "agoda": "hanoi",
            "ivivu": "ha-noi",
            "mytour": "ha-noi",
            "traveloka": "hanoi",
        },
        "Hồ Chí Minh": {
            "booking": "ho-chi-minh-city",
            "agoda": "ho-chi-minh-city",
            "ivivu": "thanh-pho-ho-chi-minh",
            "mytour": "thanh-pho-ho-chi-minh",
            "traveloka": "ho-chi-minh",
        },
        "Đà Nẵng": {
            "booking": "da-nang",
            "agoda": "da-nang",
            "ivivu": "da-nang",
            "mytour": "da-nang",
            "traveloka": "da-nang",
        },
        "Nha Trang": {
            "booking": "nha-trang",
            "agoda": "nha-trang",
            "ivivu": "nha-trang",
            "mytour": "nha-trang",
            "traveloka": "nha-trang",
        },
        "Phú Quốc": {
            "booking": "phu-quoc",
            "agoda": "phu-quoc",
            "ivivu": "phu-quoc",
            "mytour": "phu-quoc",
            "traveloka": "phu-quoc",
        },
        "Đà Lạt": {
            "booking": "da-lat",
            "agoda": "da-lat",
            "ivivu": "da-lat",
            "mytour": "da-lat",
            "traveloka": "da-lat",
        },
        "Hội An": {
            "booking": "hoi-an",
            "agoda": "hoi-an",
            "ivivu": "hoi-an",
            "mytour": "hoi-an",
            "traveloka": "hoi-an",
        },
        "Huế": {
            "booking": "hue",
            "agoda": "hue",
            "ivivu": "thua-thien-hue",
            "mytour": "hue",
            "traveloka": "hue",
        },
        "Hạ Long": {
            "booking": "ha-long",
            "agoda": "halong-city",
            "ivivu": "ha-long",
            "mytour": "ha-long",
            "traveloka": "ha-long",
        },
        "Sa Pa": {
            "booking": "sapa",
            "agoda": "sapa",
            "ivivu": "sapa",
            "mytour": "sapa",
            "traveloka": "sapa",
        },
        # ... (thêm các thành phố khác)
        "Vũng Tàu": {
            "booking": "vung-tau",
            "agoda": "vung-tau",
            "ivivu": "vung-tau",
            "mytour": "vung-tau",
            "traveloka": "vung-tau",
        },
        "Mũi Né": {
            "booking": "mui-ne",
            "agoda": "mui-ne",
            "ivivu": "mui-ne",
            "mytour": "mui-ne",
            "traveloka": "mui-ne",
        },
        "Cần Thơ": {
            "booking": "can-tho",
            "agoda": "can-tho",
            "ivivu": "can-tho",
            "mytour": "can-tho",
            "traveloka": "can-tho",
        },
    }

    # TripAdvisor geo IDs
    _TA_GEO: dict[str, str] = {
        "Hà Nội": "g293924",
        "Hồ Chí Minh": "g293925",
        "Đà Nẵng": "g298085",
        "Hội An": "g298082",
        "Huế": "g293926",
        "Nha Trang": "g298092",
        "Phú Quốc": "g469404",
        "Đà Lạt": "g293922",
        "Hạ Long": "g469418",
        "Sa Pa": "g311304",
        "Vũng Tàu": "g303942",
        "Mũi Né": "g303944",
        "Quy Nhơn": "g1078753",
        "Cần Thơ": "g303940",
        "Hải Phòng": "g303939",
    }

    def __init__(self, cfg: Optional[URLGeneratorConfig] = None):
        self.cfg = cfg or URLGeneratorConfig()

    # ── Booking.com ────────────────────────────────────────────
    def booking_listing(
        self,
        city: str,
        checkin: Optional[str] = None,
        checkout: Optional[str] = None,
        max_pages: Optional[int] = None,
    ) -> list[str]:
        """Generate Booking.com listing URLs."""
        slug = self._get_slug(city, "booking")
        checkin = checkin or self.cfg.default_checkin
        checkout = checkout or self.cfg.default_checkout
        max_pages = max_pages or self.cfg.max_pages_booking
        
        urls = []
        for p in range(max_pages):
            url = (
                f"https://www.booking.com/searchresults.vi.html"
                f"?ss={slug}"
                f"&checkin={checkin}"
                f"&checkout={checkout}"
                f"&offset={p * 25}"
                f"&order=review_score_and_count"
                f"&nflt=ht_id%3D204"  # Only hotels
            )
            urls.append(url)
        
        return urls

    # ── Agoda.com ──────────────────────────────────────────────
    def agoda_listing(
        self,
        city: str,
        checkin: Optional[str] = None,
        checkout: Optional[str] = None,
        max_pages: Optional[int] = None,
    ) -> list[str]:
        """Generate Agoda.com listing URLs."""
        slug = self._get_slug(city, "agoda")
        checkin = checkin or self.cfg.default_checkin
        checkout = checkout or self.cfg.default_checkout
        max_pages = max_pages or self.cfg.max_pages_agoda
        
        urls = []
        for p in range(1, max_pages + 1):
            url = (
                f"https://www.agoda.com/vi-vn/city/{slug}.html"
                f"?checkIn={checkin}"
                f"&checkOut={checkout}"
                f"&page={p}"
                f"&sortBy=popularity"
            )
            urls.append(url)
        
        return urls

    # ── TripAdvisor.com ────────────────────────────────────────
    def tripadvisor_listing(
        self,
        city: str,
        max_pages: Optional[int] = None,
    ) -> list[str]:
        """Generate TripAdvisor listing URLs."""
        geo = self._TA_GEO.get(city, "g293924")
        max_pages = max_pages or self.cfg.max_pages_tripadvisor
        
        urls = []
        for p in range(max_pages):
            offset = p * 30
            suffix = f"-oa{offset}" if offset > 0 else ""
            url = (
                f"https://www.tripadvisor.com/Hotels-{geo}"
                f"{suffix}-Hotels.html"
            )
            urls.append(url)
        
        return urls

    # ── Google Maps ────────────────────────────────────────────
    def google_maps_search(self, city: str) -> list[str]:
        """Generate Google Maps search URLs."""
        queries = [
            f"khách sạn {city}",
            f"resort {city}",
            f"homestay {city}",
            f"khu du lịch {city}",
            f"nhà nghỉ {city}",
        ]
        return [
            f"https://www.google.com/maps/search/{quote(q)}"
            for q in queries
        ]

    # ── iVIVU ─────────────────────────────────────────────────
    def ivivu_listing(
        self,
        city: str,
        max_pages: Optional[int] = None,
    ) -> list[str]:
        """Generate iVIVU listing URLs."""
        slug = self._get_slug(city, "ivivu")
        max_pages = max_pages or self.cfg.max_pages_ivivu
        
        urls = []
        for p in range(1, max_pages + 1):
            url = (
                f"https://www.ivivu.com/khach-san/{slug}"
                f"?page={p}&sort=review"
            )
            urls.append(url)
        
        return urls

    # ── MyTour ────────────────────────────────────────────────
    def mytour_listing(
        self,
        city: str,
        max_pages: Optional[int] = None,
    ) -> list[str]:
        """Generate MyTour listing URLs."""
        slug = self._get_slug(city, "mytour")
        max_pages = max_pages or self.cfg.max_pages_mytour
        
        urls = []
        for p in range(1, max_pages + 1):
            url = (
                f"https://www.mytour.vn/khach-san/{slug}.html"
                f"?trang={p}&sapxep=diem-danh-gia"
            )
            urls.append(url)
        
        return urls

    # ── Traveloka ──────────────────────────────────────────────
    def traveloka_listing(
        self,
        city: str,
        max_pages: Optional[int] = None,
    ) -> list[str]:
        """Generate Traveloka listing URLs."""
        slug = self._get_slug(city, "traveloka")
        max_pages = max_pages or self.cfg.max_pages_traveloka
        
        urls = []
        for p in range(1, max_pages + 1):
            url = (
                f"https://www.traveloka.com/vi-vn/hotel/vietnam/{slug}"
                f"?page={p}&sort=RATING"
            )
            urls.append(url)
        
        return urls

    # ── Utility ────────────────────────────────────────────────
    def _get_slug(
        self,
        city: str,
        platform: str,
    ) -> str:
        """Lấy slug cho thành phố và platform."""
        if city in self._CITY_SLUGS:
            slug = self._CITY_SLUGS[city].get(
                platform,
                city.lower().replace(" ", "-")
            )
        else:
            slug = city.lower().replace(" ", "-")
        
        return slug

    def generate_all(
        self,
        provinces: Optional[list[str]] = None,
        sources: Optional[list[str]] = None,
        max_pages: int = 5,
    ) -> dict[str, list[str]]:
        """
        Generate tất cả listing URLs cho provinces & sources.
        
        Args:
            provinces: Danh sách tỉnh thành
            sources: Danh sách platform (booking, agoda, etc.)
            max_pages: Max pages per listing
            
        Returns:
            Dict[province_name, list[urls]]
        """
        if provinces is None:
            provinces = list(self._CITY_SLUGS.keys())
        
        if sources is None:
            sources = [
                "booking", "agoda", "tripadvisor",
                "google_maps", "ivivu", "mytour",
                "traveloka",
            ]

        result: dict[str, list[str]] = {}
        
        for province in provinces:
            urls: list[str] = []
            
            if "booking" in sources:
                urls.extend(self.booking_listing(
                    province, max_pages=max_pages
                ))
            
            if "agoda" in sources:
                urls.extend(self.agoda_listing(
                    province, max_pages=max_pages
                ))
            
            if "tripadvisor" in sources:
                urls.extend(self.tripadvisor_listing(
                    province, max_pages=max_pages
                ))
            
            if "google_maps" in sources:
                urls.extend(self.google_maps_search(province))
            
            if "ivivu" in sources:
                urls.extend(self.ivivu_listing(
                    province, max_pages=max_pages
                ))
            
            if "mytour" in sources:
                urls.extend(self.mytour_listing(
                    province, max_pages=max_pages
                ))
            
            if "traveloka" in sources:
                urls.extend(self.traveloka_listing(
                    province, max_pages=max_pages
                ))
            
            result[province] = urls

        return result


# ── Listing Scraper ───────────────────────────────────────────────
class ListingScraper:
    """
    Trích xuất hotel URLs từ listing pages.
    Hỗ trợ các platform khác nhau với fallback selectors.
    """

    def __init__(self, cfg: Optional[URLGeneratorConfig] = None):
        self.cfg = cfg or URLGeneratorConfig()
        self._stats = defaultdict(int)

    # ── Booking.com ────────────────────────────────────────────
    async def extract_hotel_urls_booking(
        self,
        page: Page,
    ) -> list[str]:
        """Extract hotel URLs từ Booking.com listing."""
        urls = []
        selectors = [
            "[data-testid='property-card']",
            "div.sr_property_block",
            "li[data-testid='property-card-container']",
            "[data-component-type='s-hotel-card']",
        ]
        
        cards = None
        for selector in selectors:
            try:
                cards = page.locator(selector)
                if await cards.count() > 0:
                    break
            except Exception:
                continue

        if not cards or await cards.count() == 0:
            log.warning("❌ No hotel cards found on Booking page")
            return []

        for i in range(await cards.count()):
            try:
                card = cards.nth(i)
                
                # Cố gắng nhiều selectors cho link
                link_selectors = [
                    "a[data-testid='title-link']",
                    "a.hotel_name_link",
                    "h3 a",
                    "a[data-component-type='s-hotel-card-title-link']",
                ]
                
                href = None
                for link_sel in link_selectors:
                    try:
                        link = card.locator(link_sel).first
                        href = await _attr(link, "href")
                        if href and "booking.com/hotel" in href:
                            break
                    except Exception:
                        continue

                if href and "booking.com/hotel" in href:
                    # Chuẩn hóa URL
                    clean_url = href.split("?")[0] + ".vi.html"
                    urls.append(clean_url)
            
            except Exception as e:
                log.debug(f"Error extracting Booking card {i}: {e}")
                continue

        return list(set(urls))  # Dedup

    # ── Agoda.com ──────────────────────────────────────────────
    async def extract_hotel_urls_agoda(
        self,
        page: Page,
    ) -> list[str]:
        """Extract hotel URLs từ Agoda listing."""
        urls = []
        selectors = [
            "[data-selenium='hotel-item']",
            "li.hotel-list-item",
            "div.PropertyCard",
            "[data-testid='property-card']",
        ]
        
        cards = None
        for selector in selectors:
            try:
                cards = page.locator(selector)
                if await cards.count() > 0:
                    break
            except Exception:
                continue

        if not cards or await cards.count() == 0:
            log.warning("❌ No hotel cards found on Agoda page")
            return []

        for i in range(await cards.count()):
            try:
                card = cards.nth(i)
                link = card.locator("a[href*='/hotel/']").first
                href = await _attr(link, "href")
                
                if href:
                    if not href.startswith("http"):
                        href = f"https://www.agoda.com{href}"
                    
                    # Clean query params
                    clean_url = href.split("?")[0]
                    urls.append(clean_url)
            
            except Exception as e:
                log.debug(f"Error extracting Agoda card {i}: {e}")
                continue

        return list(set(urls))

    # ── TripAdvisor.com ────────────────────────────────────────
    async def extract_hotel_urls_tripadvisor(
        self,
        page: Page,
    ) -> list[str]:
        """Extract hotel URLs từ TripAdvisor listing."""
        urls = []
        selectors = [
            "div[data-automation='hotel-card-title'] a",
            "a.property-title",
            "div.listing_title a",
            "[data-test-target='hotel-card-link']",
        ]
        
        cards = None
        for selector in selectors:
            try:
                cards = page.locator(selector)
                if await cards.count() > 0:
                    break
            except Exception:
                continue

        if not cards or await cards.count() == 0:
            log.warning("❌ No hotel cards found on TripAdvisor page")
            return []

        for i in range(await cards.count()):
            try:
                href = await _attr(cards.nth(i), "href")
                
                if href and ("Hotel_Review" in href or "/Hotel_" in href):
                    if not href.startswith("http"):
                        href = f"https://www.tripadvisor.com{href}"
                    
                    clean_url = href.split("?")[0]
                    urls.append(clean_url)
            
            except Exception as e:
                log.debug(f"Error extracting TripAdvisor card {i}: {e}")
                continue

        return list(set(urls))

    # ── iVIVU ─────────────────────────────────────────────────
    async def extract_hotel_urls_ivivu(
        self,
        page: Page,
    ) -> list[str]:
        """Extract hotel URLs từ iVIVU listing."""
        urls = []
        selectors = [
            "div.hotel-item",
            "li.property-item",
            "div.hotel-card",
            "[data-testid='hotel-item']",
        ]
        
        cards = None
        for selector in selectors:
            try:
                cards = page.locator(selector)
                if await cards.count() > 0:
                    break
            except Exception:
                continue

        if not cards or await cards.count() == 0:
            log.warning("❌ No hotel cards found on iVIVU page")
            return []

        for i in range(await cards.count()):
            try:
                card = cards.nth(i)
                link = card.locator("a[href*='/khach-san/']").first
                href = await _attr(link, "href")
                
                if href:
                    if not href.startswith("http"):
                        href = f"https://www.ivivu.com{href}"
                    
                    clean_url = href.split("?")[0]
                    urls.append(clean_url)
            
            except Exception as e:
                log.debug(f"Error extracting iVIVU card {i}: {e}")
                continue

        return list(set(urls))

    # ── MyTour ────────────────────────────────────────────────
    async def extract_hotel_urls_mytour(
        self,
        page: Page,
    ) -> list[str]:
        """Extract hotel URLs từ MyTour listing."""
        urls = []
        selectors = [
            "div.hotel-item",
            "li.hotel-list-item",
            "article.hotel-card",
            "div.khachsan-item",
        ]
        
        cards = None
        for selector in selectors:
            try:
                cards = page.locator(selector)
                if await cards.count() > 0:
                    break
            except Exception:
                continue

        if not cards or await cards.count() == 0:
            log.warning("❌ No hotel cards found on MyTour page")
            return []

        for i in range(await cards.count()):
            try:
                card = cards.nth(i)
                link = card.locator("a[href*='/khach-san/']").first
                href = await _attr(link, "href")
                
                if href:
                    if not href.startswith("http"):
                        href = f"https://www.mytour.vn{href}"
                    
                    clean_url = href.split("?")[0]
                    urls.append(clean_url)
            
            except Exception as e:
                log.debug(f"Error extracting MyTour card {i}: {e}")
                continue

        return list(set(urls))

    # ── Traveloka ──────────────────────────────────────────────
    async def extract_hotel_urls_traveloka(
        self,
        page: Page,
    ) -> list[str]:
        """Extract hotel URLs từ Traveloka listing."""
        urls = []
        selectors = [
            "[data-testid='hotel-card']",
            "div.hotel-list-item",
            "li.property-card",
            "div.HotelCard",
        ]
        
        cards = None
        for selector in selectors:
            try:
                cards = page.locator(selector)
                if await cards.count() > 0:
                    break
            except Exception:
                continue

        if not cards or await cards.count() == 0:
            log.warning("❌ No hotel cards found on Traveloka page")
            return []

        for i in range(await cards.count()):
            try:
                card = cards.nth(i)
                link = card.locator("a[href*='/hotel/']").first
                href = await _attr(link, "href")
                
                if href:
                    if not href.startswith("http"):
                        href = f"https://www.traveloka.com{href}"
                    
                    clean_url = href.split("?")[0]
                    urls.append(clean_url)
            
            except Exception as e:
                log.debug(f"Error extracting Traveloka card {i}: {e}")
                continue

        return list(set(urls))

    # ── Dispatcher ─────────────────────────────────────────────
    async def scrape_listing_page(
        self,
        page: Page,
        url: str,
        platform: str,
    ) -> ListingScrapResult:
        """
        Scrape listing page và extract hotel URLs.
        
        Args:
            page: Playwright Page object
            url: Listing page URL
            platform: Platform name (booking.com, agoda.com, etc.)
            
        Returns:
            ListingScrapResult với thống kê
        """
        import time
        start_time = time.time()
        
        # Dispatcher: platform → extractor method
        extractors: dict[str, Callable] = {
            "booking.com": self.extract_hotel_urls_booking,
            "agoda.com": self.extract_hotel_urls_agoda,
            "tripadvisor.com": self.extract_hotel_urls_tripadvisor,
            "ivivu.com": self.extract_hotel_urls_ivivu,
            "mytour.vn": self.extract_hotel_urls_mytour,
            "traveloka.com": self.extract_hotel_urls_traveloka,
        }
        
        # Tìm extractor phù hợp
        extractor = None
        matched_platform = None
        
        for key, func in extractors.items():
            if key in platform or key.split(".")[0] in platform:
                extractor = func
                matched_platform = key
                break
        
        if not extractor:
            log.warning(f"⚠️ No extractor found for platform: {platform}")
            return ListingScrapResult(
                platform=platform,
                url=url,
                urls_found=0,
                error=f"Unknown platform: {platform}",
                duration=time.time() - start_time,
            )
        
        try:
            log.info(
                f"📍 Scraping {matched_platform} | URL: {url[:60]}..."
            )
            
            # Wait for page to be ready
            try:
                await page.wait_for_load_state("networkidle")
            except PlaywrightTimeoutError:
                log.debug("⏱️ Page timeout on networkidle, continuing...")
            
            # Extract URLs
            urls = await extractor(page)
            
            duration = time.time() - start_time
            
            result = ListingScrapResult(
                platform=matched_platform,
                url=url,
                urls_found=len(urls),
                urls_extracted=urls,
                duration=duration,
            )
            
            if urls:
                log.info(
                    f"✅ {matched_platform} | Found {len(urls)} hotel URLs "
                    f"in {duration:.1f}s"
                )
            else:
                log.warning(
                    f"⚠️ {matched_platform} | No URLs found in {duration:.1f}s"
                )
            
            return result
        
        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"{type(e).__name__}: {str(e)[:100]}"
            
            log.error(
                f"❌ Error scraping {matched_platform}: {error_msg}"
            )
            
            return ListingScrapResult(
                platform=matched_platform or platform,
                url=url,
                urls_found=0,
                error=error_msg,
                duration=duration,
            )

    async def batch_scrape(
        self,
        page: Page,
        listings: list[tuple[str, str]],  # [(url, platform), ...]
    ) -> list[ListingScrapResult]:
        """
        Scrape hàng loạt listing pages.
        
        Args:
            page: Shared Playwright Page
            listings: List[(url, platform)]
            
        Returns:
            List[ListingScrapResult]
        """
        results = []
        
        for url, platform in listings:
            try:
                result = await self.scrape_listing_page(
                    page, url, platform
                )
                results.append(result)
                
                # Delay giữa requests
                await asyncio.sleep(0.5)
            
            except Exception as e:
                log.error(f"Batch scrape error: {e}")
                results.append(ListingScrapResult(
                    platform=platform,
                    url=url,
                    urls_found=0,
                    error=str(e),
                ))
        
        return results

    def get_stats(self) -> dict:
        """Lấy thống kê scraping."""
        return dict(self._stats)
