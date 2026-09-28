"""maibot_plugin_Helldivers — Helldivers 2 银河战争查询插件（MaiBot 版）。

自 astrbot_plugin_Helldivers v1.9.0 移植。指令:
  /dashboard /hd2stats /order /personal_order /map /warfront
  /global_events /steam /wiki /hd2data /hd2ping
  /hd2news (+订阅/退订) /companion /dss /planet /hd2refresh
  /银河快报 (+订阅/退订)
  /hd2 | /hd2help

所有指令同时接受 ``/`` 前缀与裸命令词（如 ``总览``、``银河快报``）。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from pathlib import Path
from typing import Any

from maibot_sdk import Command, MaiBotPlugin

from .hd2.clients.api_client import HD2Client
from .hd2.clients.arsenal_client import ArsenalClient
from .hd2.clients.bilibili_monitor import (
    GALAXY_NEWS_UID,
    LEGACY_GALAXY_NEWS_UID,
    BilibiliAuthenticationError,
    BilibiliMonitor,
    BilibiliPost,
    BilibiliRiskControlError,
)
from .hd2.clients.companion_news_monitor import CompanionNewsMonitor
from .hd2.clients.companion_screenshot import (
    CompanionConfigurationError,
    CompanionPlaywrightClient,
    CompanionScreenshotClient,
    CompanionTarget,
    CompanionTargetError,
    companion_dss_target,
    companion_homepage_target,
    companion_latest_news_target,
    parse_companion_planet_target,
)
from .hd2.clients.remote_image_cache import RemoteImageCache
from .hd2.clients.translator import TranslationCache, TranslationService
from .hd2.clients.wiki_client import WikiCache, WikiClient
from .hd2.compat import get_plugin_data_dir, logger, set_plugin_data_base
from .hd2.config_schema import HD2Config
from .hd2.core.cache import CacheService
from .hd2.core.campaign_trends import CampaignTrendStore
from .hd2.core.diagnostics import (
    EXPECTED_SOURCES,
    HEALTH,
    build_ping_report,
    humanize_age,
    humanize_uptime,
)
from .hd2.core.plugin_info import PLUGIN_NAME, PLUGIN_VERSION, USER_AGENT
from .hd2.renderers.awaiting_orders_renderer import AwaitingOrdersRenderer
from .hd2.renderers.card_renderer import CardRenderer
from .hd2.renderers.dashboard_renderer import DashboardRenderer
from .hd2.renderers.dispatch_renderer import DispatchRenderer
from .hd2.renderers.dss_renderer import DSSRenderer
from .hd2.renderers.global_event_renderer import GlobalEventRenderer
from .hd2.renderers.major_order_renderer import MajorOrderRenderer
from .hd2.renderers.map_renderer import MapRenderer
from .hd2.renderers.stats_renderer import StatsRenderer
from .hd2.renderers.steam_renderer import SteamRenderer
from .hd2.renderers.visual_assets import configure_asset_manifest
from .hd2.renderers.warfront_renderer import WarfrontRenderer
from .hd2.services import HelldiversService

HELP_TEXT = f"""\
Helldivers 2 银河战争 {PLUGIN_VERSION}
━━━━━━━━━━━━━━━━━━━━
【战况 · 图片卡片】
/dashboard            银河战争总览（实时数据）
/hd2stats             银河战争详细统计（实时数据）
/major_order          主要任务（同 /order）
/personal_order       个人任务
/map                  战争地图（阵营领土）
/dss                  Companion 民主空间站图文
/global_events        全球事件
/hd2news              Companion 最新新闻
/hd2news订阅 / 退订   新闻更新自动推送
/companion            Companion 首页（截图+翻译）
/warfront <阵营>      战线战况
/planet <名称/编号>   星球详情
/steam                Steam 新闻图片
【文本】
/wiki <关键词>        Helldivers Wiki（-f 查看全文）
/hd2data <名称>       军需簿：武器/护甲/敌人
/银河快报             立即获取最新一期银河快报
/hd2ping              数据源自诊断（健康/缓存）
/hd2help              全部指令说明
/hd2                  简短帮助
━━━━━━━━━━━━━━━━━━━━
阵营: Terminids / Automaton / Illuminate
     （终结族 / 机器人 / 光能者）
数据: api.helldivers2.dev · wiki.gg · HD2Tool
为了超级地球！🌍"""

HDHELP_TEXT = f"""\
绝地潜兵2情报助手 {PLUGIN_VERSION} · 全部指令
━━━━━━━━━━━━━━━━━━━━

【核心战况 · 实时数据】
/dashboard            银河战争总览（防御/解放/重点战线）
/hd2stats             在线人数、击杀、命中率等统计
/order                当前最高指令任务卡
/po                   当前个人指令

【Companion 截图 · 翻译】
/hd2news              最新新闻（截图+翻译）
/hd2news订阅 / 退订   新闻更新自动推送到本群
/companion            Companion 首页
/dss                  民主空间站面板+摘要
/planet <名称/编号>   星球详情（支持中文名和链接）
/hd2refresh           强制刷新截图缓存

【地图与战线】
/map                  银河战争地图
/warfront <阵营>      阵营战线 Top 10
/events               全球事件

【外部资讯】
/steam                Steam 更新公告
/wiki <关键词>        Wiki 查询（中文自动译名；加 -f 看全文）
/hd2data <名称>       军需簿：武器/护甲/敌人（俗称：电喷/泰坦）
/银河快报             最新一期快报
/银河快报订阅 / 退订   群推送开关

【帮助】
/hd2                  简短帮助
/hd2help              本说明
/hd2ping              自诊断：数据源健康、缓存年龄
━━━━━━━━━━━━━━━━━━━━
阵营: 终结族 / 机器人 / 光能者
为了超级地球！🌍"""


def _planet_search_query(value: str) -> str:
    """planet 目标 value 可能带 `_(index)` 编号后缀，文本查询用纯星球名。"""
    name = value
    if name.endswith(")") and "_(" in name:
        name = name.rsplit("_(", 1)[0]
    return name.replace("_", " ")


def _strip_cmd(text: str, names: set[str]) -> list[str]:
    """从原始消息中剥掉命令词得到参数列表（matched_groups 缺失时兜底）。"""
    parts = (text or "").strip().split()
    args: list[str] = []
    for p in parts:
        token = p.lstrip("/").lower()
        if token in names:
            continue
        args.append(p)
    return args


# 权重 2：命令命中后优先于普通 LLM 回复
_CMD_WEIGHT = 2

# Host↔Runner 的 IPC 帧硬上限为 16 MiB（transport/base.py MAX_FRAME_SIZE），
# 图片以 base64（≈原始体积 4/3）随信封过帧；预留余量后的单张原始字节预算。
_MAX_IMAGE_WIRE_BYTES = 11 * 1024 * 1024


class HelldiversPlugin(MaiBotPlugin):
    """Helldivers 2 银河战争情报助手。"""

    config_model = HD2Config

    def __init__(self) -> None:
        super().__init__()
        self.service: HelldiversService | None = None
        self.bilibili_monitor: BilibiliMonitor | None = None
        self.bilibili_auto_enabled = False
        self.companion_enabled = False
        self.companion_backend = "playwright"
        self.companion_playwright: CompanionPlaywrightClient | None = None
        self.companion_screenshots: CompanionScreenshotClient | None = None
        self._companion_warmup_task: asyncio.Task | None = None
        self.companion_news_monitor: CompanionNewsMonitor | None = None
        self._companion_news_push_enabled = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def on_load(self) -> None:
        set_plugin_data_base(Path(self.ctx.paths.data_dir))
        data_dir = get_plugin_data_dir(PLUGIN_NAME)
        HEALTH.mark_boot()
        cfg = self.config

        self.companion_enabled = bool(cfg.enable_companion_screenshots)
        self.companion_backend = str(cfg.companion_render_backend or "playwright")
        self.companion_backend = self.companion_backend.strip().casefold()
        if self.companion_backend not in {"local", "playwright", "browserless"}:
            logger.warning(
                "[HD2] Invalid companion_render_backend=%s; using playwright",
                self.companion_backend,
            )
            self.companion_backend = "playwright"
        self.companion_playwright = None
        self.companion_screenshots = None
        if self.companion_enabled and self.companion_backend == "playwright":
            try:
                self.companion_playwright = CompanionPlaywrightClient(
                    data_dir / "companion_screenshots",
                    timeout=int(cfg.companion_screenshot_timeout or 60),
                    wait_ms=int(cfg.companion_screenshot_wait_ms or 5000),
                    cache_ttl=int(cfg.companion_screenshot_cache_ttl or 300),
                    max_bytes=int(
                        cfg.companion_screenshot_max_bytes or 12 * 1024 * 1024
                    ),
                    max_pixels=int(cfg.companion_screenshot_max_pixels or 20_000_000),
                    page_load_timeout=float(cfg.companion_page_load_timeout or 20.0),
                    translation_timeout=float(cfg.companion_translation_timeout or 60.0),
                    show_inactive=bool(cfg.companion_show_inactive),
                )
                await self.companion_playwright.start()
            except (CompanionConfigurationError, TypeError, ValueError) as e:
                logger.warning(f"[HD2] Local Playwright disabled: {e}")
                self.companion_playwright = None
        elif self.companion_enabled and self.companion_backend == "browserless":
            try:
                self.companion_screenshots = CompanionScreenshotClient(
                    data_dir / "companion_screenshots",
                    endpoint_url=str(cfg.companion_browserless_url or ""),
                    token=str(cfg.companion_browserless_token or ""),
                    proxy_url=str(cfg.companion_browserless_proxy_url or ""),
                    timeout=int(cfg.companion_screenshot_timeout or 60),
                    wait_ms=int(cfg.companion_screenshot_wait_ms or 5000),
                    cache_ttl=int(cfg.companion_screenshot_cache_ttl or 300),
                    max_bytes=int(
                        cfg.companion_screenshot_max_bytes or 12 * 1024 * 1024
                    ),
                    max_pixels=int(cfg.companion_screenshot_max_pixels or 20_000_000),
                )
            except (CompanionConfigurationError, TypeError, ValueError) as e:
                logger.warning(f"[HD2] Companion screenshot disabled: {e}")

        client = HD2Client(
            base_url=str(cfg.api_base or "https://api.helldivers2.dev"),
            war_id=int(cfg.war_id or 801),
            client_name=str(cfg.api_client_name or PLUGIN_NAME),
            contact=str(cfg.api_contact or ""),
            user_agent=str(cfg.api_user_agent or USER_AGENT),
            timeout=int(cfg.api_timeout or 20),
            proxy_url=str(cfg.proxy_url or ""),
            retry_base_delay=float(cfg.retry_base_delay or 3.0),
            retry_max_delay=float(cfg.retry_max_delay or 15.0),
            retry_max_attempts=int(cfg.retry_max_attempts or 2),
            min_request_interval=float(cfg.min_request_interval or 3.0),
            steam_appid=int(cfg.steam_appid or 553850),
            steam_news_count=int(cfg.steam_news_count or 10),
        )

        cache = CacheService(
            data_dir,
            update_interval=int(cfg.cache_update_interval or 300),
            request_delay=float(cfg.request_delay or 6),
            enable_background=bool(cfg.enable_background_refresh),
        )

        enable_translation = bool(cfg.enable_translation)
        translator = TranslationService(
            api_url=str(
                cfg.translation_api_url or "https://uapis.cn/api/v1/ai/translate"
            ),
            timeout=int(cfg.translation_timeout or 20),
            target_lang=str(cfg.translation_target_lang or "zh"),
            user_agent=str(cfg.api_user_agent or USER_AGENT),
            proxy_url=str(cfg.proxy_url or ""),
            enabled=enable_translation,
            mode=str(cfg.translation_mode or "auto"),
            api_key=str(cfg.translation_api_key or ""),
            model=str(cfg.translation_model or "gpt-4o-mini"),
            stream=bool(cfg.translation_stream),
            fallback_ttl=int(cfg.translation_retry_fallback_seconds or 180),
            error_cooldown=int(cfg.translation_error_cooldown_seconds or 120),
            max_tokens=int(cfg.translation_max_tokens),
            min_interval=float(cfg.translation_min_interval_seconds or 0),
        )
        logger.info("[HD2] translation provider: %s", translator.diagnostic())

        translation_cache = TranslationCache(
            data_dir,
            provider_fingerprint=translator.provider_fingerprint(),
            fallback_ttl=int(cfg.translation_retry_fallback_seconds or 180),
        )

        enable_wiki = bool(cfg.enable_wiki)
        wiki_client: WikiClient | None = None
        if enable_wiki:
            wiki_cache = WikiCache(
                data_dir,
                page_ttl=int(cfg.wiki_cache_ttl or 21600),
                search_ttl=int(cfg.wiki_search_cache_ttl or 1800),
            )
            wiki_client = WikiClient(
                base_url=str(cfg.wiki_base or "https://helldivers.wiki.gg"),
                api_path=str(cfg.wiki_api_path or "/api.php"),
                user_agent=str(cfg.api_user_agent or USER_AGENT),
                timeout=int(cfg.api_timeout or 30),
                proxy_url=str(cfg.proxy_url or ""),
                search_limit=int(cfg.wiki_search_limit or 5),
                extract_chars=int(cfg.wiki_extract_chars or 900),
                full_extract_chars=int(cfg.wiki_full_extract_chars or 3000),
                prefer_hd2=bool(cfg.wiki_prefer_hd2),
                retry_max_attempts=int(cfg.retry_max_attempts or 3),
                retry_base_delay=float(cfg.retry_base_delay or 2.0),
                cache=wiki_cache,
            )
        manifest_path = str(cfg.asset_manifest_path or "").strip()
        configure_asset_manifest(manifest_path or None)

        map_renderer = MapRenderer(
            data_dir / "maps",
            cache_ttl=int(cfg.map_cache_ttl or 600),
            label_top_n=int(cfg.map_label_top_n or 15),
            visual_mode=str(cfg.map_visual_mode or "uploaded_reference"),
        )
        card_renderer = CardRenderer(data_dir / "cards")
        dashboard_renderer = DashboardRenderer(data_dir / "dashboard")
        stats_renderer = StatsRenderer(data_dir / "stats")
        dss_renderer = DSSRenderer(data_dir / "dss")
        major_order_renderer = MajorOrderRenderer(data_dir / "orders")
        awaiting_orders_renderer = AwaitingOrdersRenderer(data_dir / "cards")
        dispatch_renderer = DispatchRenderer(data_dir / "dispatches")
        warfront_renderer = WarfrontRenderer(data_dir / "warfront")
        global_event_renderer = GlobalEventRenderer(data_dir / "global_events")
        steam_renderer = SteamRenderer(data_dir / "steam")
        remote_image_cache = RemoteImageCache(
            data_dir / "remote_images",
            max_bytes=int(cfg.remote_image_max_bytes or 8388608),
            max_pixels=int(cfg.remote_image_max_pixels or 16000000),
            max_cache_bytes=int(cfg.image_cache_max_mb or 150) * 1024 * 1024,
            user_agent=str(cfg.api_user_agent or USER_AGENT),
            proxy_url=str(cfg.proxy_url or ""),
        )
        campaign_trends = CampaignTrendStore(
            data_dir / "campaign_history.json",
            window_minutes=max(
                1.0, float(cfg.campaign_rate_window_minutes or 20)
            ),
            prune_hours=float(cfg.campaign_history_hours or 2),
        )

        self.service = HelldiversService(
            client,
            cache,
            translator,
            translation_cache,
            steam_max_content_length=int(cfg.steam_max_content_length or 2000),
            steam_balancing_limit=int(cfg.steam_balancing_limit or 800),
            steam_fixes_limit=int(cfg.steam_fixes_limit or 600),
            steam_issues_limit=int(cfg.steam_issues_limit or 300),
            steam_max_sections=int(cfg.steam_max_sections or 3),
            steam_image_enabled=bool(cfg.steam_image_enabled),
            rotation_dispatches=int(cfg.rotation_dispatches or 300),
            rotation_orders=int(cfg.rotation_orders or 600),
            rotation_steam=int(cfg.rotation_steam or 900),
            enable_translation=enable_translation,
            wiki_client=wiki_client,
            enable_wiki=enable_wiki,
            translate_wiki=bool(cfg.translate_wiki),
            map_renderer=map_renderer,
            enable_map=bool(cfg.enable_map),
            personal_order_api_url=str(cfg.personal_order_api_url or ""),
            allow_private_personal_order_url=bool(
                cfg.allow_private_personal_order_url
            ),
            card_renderer=card_renderer,
            dashboard_renderer=dashboard_renderer,
            stats_renderer=stats_renderer,
            dss_renderer=dss_renderer,
            major_order_renderer=major_order_renderer,
            awaiting_orders_renderer=awaiting_orders_renderer,
            dispatch_renderer=dispatch_renderer,
            warfront_renderer=warfront_renderer,
            global_event_renderer=global_event_renderer,
            steam_renderer=steam_renderer,
            remote_image_cache=remote_image_cache,
            campaign_trends=campaign_trends,
            dashboard_low_impact_threshold=int(
                cfg.dashboard_low_impact_threshold or 800
            ),
            drop_untranslated_content=bool(cfg.drop_untranslated_content),
            companion_translation_batch_timeout=float(
                cfg.companion_translation_batch_timeout or 20.0
            ),
            companion_translation_budget=float(
                cfg.companion_translation_timeout or 60.0
            ),
            arsenal_client=ArsenalClient(
                data_dir / "arsenal",
                proxy_url=str(cfg.proxy_url or ""),
                timeout=int(cfg.api_timeout or 30),
                user_agent=str(cfg.api_user_agent or USER_AGENT),
            )
            if bool(cfg.enable_arsenal)
            else None,
        )

        if self.companion_playwright is not None and enable_translation:
            self.companion_playwright.set_translate_callback(
                self.service.translate_companion_fragments,
                cache_namespace=self.service.translation_cache.provider_fingerprint,
            )

        await self.service.start()

        configured_bilibili_uid = str(
            cfg.bilibili_uid or GALAXY_NEWS_UID
        ).strip()
        if configured_bilibili_uid == LEGACY_GALAXY_NEWS_UID:
            logger.warning(
                "[HD2] 已自动修正银河快报旧 UID：%s -> %s",
                LEGACY_GALAXY_NEWS_UID,
                GALAXY_NEWS_UID,
            )
            configured_bilibili_uid = GALAXY_NEWS_UID
        self.bilibili_monitor = BilibiliMonitor(
            data_dir / "bilibili_galaxy_news",
            uid=configured_bilibili_uid,
            keyword=str(cfg.bilibili_keyword or "银河快报"),
            interval=int(cfg.bilibili_poll_interval or 300),
            cookie=str(cfg.bilibili_cookie or ""),
            proxy_url=str(cfg.proxy_url or ""),
            timeout=int(cfg.api_timeout or 30),
            max_image_bytes=int(cfg.bilibili_image_max_bytes or 16 * 1024 * 1024),
            send_post=self._send_bilibili_post,
            log_info=logger.info,
            log_warning=logger.warning,
            image_cache=RemoteImageCache(
                data_dir / "bilibili_galaxy_news" / "secure_images_v3",
                allowed_hosts=frozenset(
                    {
                        "i0.hdslb.com",
                        "i1.hdslb.com",
                        "i2.hdslb.com",
                        "archive.biliimg.com",
                        "album.biliimg.com",
                    }
                ),
                max_bytes=int(cfg.bilibili_image_max_bytes or 16 * 1024 * 1024),
                max_pixels=int(cfg.bilibili_image_max_pixels or 64000000),
                max_cache_bytes=int(cfg.image_cache_max_mb or 150) * 1024 * 1024,
                user_agent=str(cfg.api_user_agent or USER_AGENT),
                proxy_url=str(cfg.proxy_url or ""),
                negative_ttl=60,
                request_headers={
                    "Referer": "https://www.bilibili.com/",
                },
            ),
        )
        self.bilibili_auto_enabled = bool(cfg.enable_bilibili_galaxy_news)
        if self.bilibili_auto_enabled:
            if not self.bilibili_monitor.has_login_cookie:
                logger.warning(
                    "[HD2] 银河快报后台监听未启动：bilibili_cookie 缺少 SESSDATA。"
                    "请填写浏览器登录后的完整 B站 Cookie 并重载插件。"
                )
            else:
                await self.bilibili_monitor.start()
                logger.info(
                    "[HD2] Bilibili galaxy news enabled: uid=%s keyword=%s sessions=%s",
                    self.bilibili_monitor.uid,
                    self.bilibili_monitor.keyword,
                    len(self.bilibili_monitor.sessions),
                )

        contact = str(cfg.api_contact or "").strip()
        if not contact:
            logger.warning(
                "[HD2] 建议在插件配置中填写 api_contact（联系邮箱），"
                "以遵守 Helldivers API 礼仪"
            )
        logger.info(
            f"[HD2] plugin initialized {PLUGIN_VERSION}, data_dir={data_dir}"
        )
        self.companion_news_monitor = CompanionNewsMonitor(
            data_dir / "companion_news"
        )
        self._companion_news_push_enabled = bool(cfg.companion_news_push_enabled)
        self._start_companion_warmup()

    async def on_unload(self) -> None:
        if self._companion_warmup_task is not None:
            self._companion_warmup_task.cancel()
            try:
                await self._companion_warmup_task
            except (asyncio.CancelledError, Exception):
                pass
            self._companion_warmup_task = None
        if self.bilibili_monitor is not None:
            try:
                await self.bilibili_monitor.stop()
            except Exception as e:
                logger.warning(f"[HD2] Bilibili monitor stop error: {e}")
            self.bilibili_monitor = None
        self.bilibili_auto_enabled = False
        if self.companion_playwright is not None:
            try:
                await self.companion_playwright.close()
            except Exception as e:
                logger.warning(f"[HD2] Local Playwright stop error: {e}")
        self.companion_playwright = None
        self.companion_enabled = False
        self.companion_screenshots = None
        if self.service is not None:
            try:
                await self.service.stop()
            except Exception as e:
                logger.warning(f"[HD2] service stop error: {e}")
            self.service = None
        logger.info("[HD2] plugin unloaded")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        if scope == "self":
            logger.info(
                "[HD2] 插件配置已更新 (version=%s)；涉及客户端、监听与预热的配置"
                "需重载插件后生效",
                version,
            )

    # ------------------------------------------------------------------
    # 发送辅助
    # ------------------------------------------------------------------

    async def _send_text(self, stream_id: str, text: str) -> bool:
        if not stream_id:
            logger.warning("[HD2] send text skipped: empty stream_id")
            return False
        try:
            return bool(await self.ctx.send.text(text, stream_id))
        except Exception as e:
            logger.warning(f"[HD2] send text failed: {e}")
            return False

    @staticmethod
    def _fit_image_for_transport(data: bytes) -> bytes | None:
        """把超出 IPC 帧预算的图片降质/缩放到可发送体积；失败返回 None。

        队列语义：先降 JPEG 质量，仍超限再逐级缩小（最高 16 次编码，
        仅命中超限长图/大图这一罕见路径）。
        """
        if len(data) <= _MAX_IMAGE_WIRE_BYTES:
            return data
        try:
            from io import BytesIO

            from PIL import Image
        except ImportError:
            return None
        try:
            with Image.open(BytesIO(data)) as src:
                src.load()
                img: Image.Image = src
                if img.mode in ("RGBA", "LA", "PA"):
                    flat = Image.new("RGB", img.size, (255, 255, 255))
                    flat.paste(img.convert("RGB"), mask=img.getchannel("A"))
                    img = flat
                elif img.mode != "L":
                    img = img.convert("RGB")
                scale = 1.0
                while True:
                    out = img
                    if scale < 1.0:
                        out = img.resize(
                            (
                                max(1, int(img.width * scale)),
                                max(1, int(img.height * scale)),
                            ),
                            Image.Resampling.LANCZOS,
                        )
                    for quality in (85, 70, 55, 40):
                        buf = BytesIO()
                        out.save(buf, format="JPEG", quality=quality)
                        if buf.tell() <= _MAX_IMAGE_WIRE_BYTES:
                            return buf.getvalue()
                    if scale <= 0.25:
                        return None
                    scale -= 0.25
        except Exception as e:
            logger.warning(f"[HD2] image recompress failed: {e}")
            return None

    async def _send_image_bytes(self, stream_id: str, data: bytes) -> bool:
        if not stream_id:
            return False
        fitted = await asyncio.to_thread(self._fit_image_for_transport, data)
        if fitted is None:
            logger.warning(
                "[HD2] image over transport budget and recompress failed: %d bytes",
                len(data),
            )
            return False
        try:
            encoded = base64.b64encode(fitted).decode("ascii")
            return bool(await self.ctx.send.image(encoded, stream_id))
        except Exception as e:
            logger.warning(f"[HD2] send image failed: {e}")
            return False

    async def _send_image_path(self, stream_id: str, path: Path) -> bool:
        """读取本地图片文件并发送；读取失败记日志并返回 False。"""
        try:
            data = await asyncio.to_thread(path.read_bytes)
        except OSError as e:
            logger.warning(f"[HD2] image unreadable: {path} error={e}")
            return False
        return await self._send_image_bytes(stream_id, data)

    async def _send_images(
        self,
        stream_id: str,
        paths: list[Path],
        *,
        fallback: str = "❌ 生成图片失败，请稍后重试。",
    ) -> bool:
        """逐张发送图片；全部失败时发送 fallback 文本。"""
        if not paths:
            return await self._send_text(stream_id, fallback)
        sent_any = False
        for path in paths:
            if await self._send_image_path(stream_id, path):
                sent_any = True
        if not sent_any:
            await self._send_text(stream_id, fallback)
        return sent_any

    async def _send_mixed(
        self,
        stream_id: str,
        *,
        text: str | None = None,
        image_paths: list[Path] | None = None,
    ) -> bool:
        """先文本后图片的顺序发送（替代 AstrBot 的 chain_result）。"""
        ok = True
        if text:
            ok = await self._send_text(stream_id, text) and ok
        for path in image_paths or []:
            if not await self._send_image_path(stream_id, path):
                ok = False
        return ok

    def _svc(self) -> HelldiversService:
        if self.service is None:
            raise RuntimeError("插件尚未初始化完成")
        return self.service

    def _is_group(self, kwargs: dict[str, Any]) -> bool:
        message = kwargs.get("message") or {}
        info = message.get("message_info") or {}
        return bool(info.get("group_info"))

    def _session_key(self, kwargs: dict[str, Any]) -> str:
        stream_id = str(kwargs.get("stream_id") or "").strip()
        if stream_id:
            return stream_id
        # 宿主变体容错：MessageDict 自带同义字段 session_id
        message = kwargs.get("message") or {}
        return str(message.get("session_id") or "").strip()

    def _arg(
        self,
        kwargs: dict[str, Any],
        group: str,
        tokens: set[str],
    ) -> str:
        """取指令参数：优先正则命名捕获组，否则从原始消息剥词兜底。"""
        matched = kwargs.get("matched_groups") or {}
        value = str(matched.get(group) or "").strip()
        if value:
            return value
        raw = str(kwargs.get("raw_message") or "")
        return " ".join(_strip_cmd(raw, tokens)).strip()

    # ------------------------------------------------------------------
    # Companion 截图
    # ------------------------------------------------------------------

    async def _capture_companion_page(
        self, target: CompanionTarget, *, force: bool = False
    ) -> Path:
        if not self.companion_enabled:
            raise CompanionConfigurationError("Companion 网页截图尚未启用")
        if self.companion_backend == "local":
            raise CompanionConfigurationError("当前配置为 Pillow 本地渲染后端")

        if self.companion_backend == "playwright":
            client = self.companion_playwright
            if client is None:
                raise CompanionConfigurationError(
                    "本地 Playwright 尚未启用，请检查容器中的 Chromium 和插件日志"
                )
            return await client.capture(target, force=force)

        client = self.companion_screenshots
        if client is None:
            raise CompanionConfigurationError("Browserless 网页截图尚未启用")
        if self._svc().enable_translation:
            raise CompanionConfigurationError(
                "Browserless /screenshot 后端无法调用插件翻译器，"
                "无法生成中文 Companion 截图"
            )
        return await client.capture(target, force=force)

    def _served_companion_stale(self, kind: str) -> bool:
        """Whether the last capture for *kind* served a stale cache."""
        client = self.companion_playwright
        if client is None:
            return False
        return kind in client.served_stale_kinds()

    def _stale_fallback_path(self, target: CompanionTarget) -> Path | None:
        """Return a stale cached screenshot path if one exists, else None."""
        client = self.companion_playwright
        if client is None:
            return None
        output = client.cached_output_path(target)
        if output.is_file():
            return output
        return None

    # ------------------------------------------------------------------
    # Companion 预热与新闻推送
    # ------------------------------------------------------------------

    def _start_companion_warmup(self) -> None:
        """Launch the background Companion screenshot warmup loop.

        The warmup loop periodically captures Companion pages (news, DSS, …)
        in the background so that translation results are pre-populated in
        the disk cache.  When a user actually runs ``/hd2news``, the
        screenshot is already cached and returned instantly.
        """

        if self._companion_warmup_task is not None:
            return
        if self.companion_playwright is None:
            return
        if not bool(self.config.companion_warmup_enabled):
            return
        self._companion_warmup_task = asyncio.create_task(
            self._companion_warmup_loop(), name="hd2-companion-warmup"
        )
        logger.info("[HD2] Companion 截图后台预热已启动")

    async def _companion_warmup_loop(self) -> None:
        """Periodically pre-capture Companion pages in the background."""

        interval = max(60, int(self.config.companion_warmup_interval or 300))
        kinds_raw = str(
            self.config.companion_warmup_kinds or "news_latest,station"
        ).strip()
        kind_map = {
            "news_latest": companion_latest_news_target,
            "station": companion_dss_target,
            "homepage": companion_homepage_target,
        }
        targets: list[CompanionTarget] = []
        for token in kinds_raw.split(","):
            kind = token.strip().casefold()
            factory = kind_map.get(kind)
            if factory is not None:
                targets.append(factory())
        if not targets:
            return
        # Give the rest of the plugin a moment to settle before the first run.
        await asyncio.sleep(15)
        while True:
            for target in targets:
                try:
                    # When news push is enabled, force a fresh capture for
                    # news_latest so text extraction always runs (the TTL
                    # cache would otherwise skip the page load and leave
                    # capture_texts stale, preventing change detection).
                    force = (
                        target.kind == "news_latest"
                        and self._companion_news_push_enabled
                        and self.companion_news_monitor is not None
                    )
                    path = await self.companion_playwright.capture(  # type: ignore[union-attr]
                        target, force=force
                    )
                    logger.info("[HD2] Companion 预热完成: %s", target.kind)
                    if target.kind == "news_latest":
                        await self._check_companion_news_change(path)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - background warmup
                    # news_latest 失败会影响订阅推送的及时性，用 WARNING 留痕；
                    # 其余页面预热失败属正常降级，保持 DEBUG。
                    log = logger.warning if target.kind == "news_latest" else logger.debug
                    log("[HD2] Companion 预热失败 %s: %s", target.kind, exc)
                # Small spacing between captures to avoid bursting.
                await asyncio.sleep(5)
            await asyncio.sleep(interval)

    async def _check_companion_news_change(self, path: Path) -> None:
        """Detect news content changes via fingerprint and push to subscribers."""

        monitor = self.companion_news_monitor
        if monitor is None:
            return
        client = self.companion_playwright
        if client is None:
            return
        texts = client.capture_texts("news_latest")
        if not texts:
            return
        fingerprint = hashlib.sha1("\n".join(texts).encode("utf-8")).hexdigest()
        if not monitor.check_fingerprint(fingerprint):
            return
        if not monitor.sessions:
            logger.info("[HD2] Companion 新闻已更新，但无订阅群，跳过推送")
            monitor.commit_fingerprint(fingerprint)
            return
        if not self._companion_news_push_enabled:
            logger.info("[HD2] Companion 新闻已更新，但推送总开关未启用，跳过推送")
            monitor.commit_fingerprint(fingerprint)
            return
        # 翻译未完成时 capture 会返回旧缓存截图（stale-while-revalidate），
        # 而文本指纹已是新内容——此时推送的是过期图片。跳过推送且不提交
        # 指纹，等下一轮预热拿到带新内容的截图再推。
        if self._served_companion_stale("news_latest"):
            logger.info(
                "[HD2] Companion 新闻已更新，但截图为旧缓存（翻译未完成），"
                "本轮跳过推送，下一轮重试"
            )
            return
        delivered = await self._push_companion_news(path, list(monitor.sessions))
        if delivered > 0:
            monitor.commit_fingerprint(fingerprint)
        else:
            logger.warning(
                "[HD2] Companion 新闻推送全部失败（delivered=0/%d），"
                "不提交指纹，下一轮预热将重试推送",
                len(monitor.sessions),
            )

    async def _push_companion_news(self, path: Path, sessions: list[str]) -> int:
        """Send a news-update screenshot to all subscribed sessions."""

        if not path or not path.is_file():
            logger.warning("[HD2] Companion news push image missing: %s", path)
            return 0
        try:
            image_bytes = await asyncio.to_thread(path.read_bytes)
        except OSError as exc:
            logger.warning(
                "[HD2] Companion news push image unreadable: %s error=%s",
                path,
                exc,
            )
            return 0
        delivered = 0
        for stream_id in sessions:
            try:
                sent = await self._send_text(stream_id, "📰 Companion 新闻更新")
                sent = await self._send_image_bytes(stream_id, image_bytes) and sent
            except Exception as e:
                logger.warning(
                    "[HD2] Companion news push failed: session=%s error=%s",
                    stream_id,
                    e,
                )
                continue
            if sent:
                delivered += 1
            else:
                logger.warning(
                    "[HD2] Companion news push not delivered: session=%s",
                    stream_id,
                )
        if delivered:
            logger.info(
                "[HD2] Companion 新闻推送完成: delivered=%d/%d",
                delivered,
                len(sessions),
            )
        return delivered

    # ------------------------------------------------------------------
    # B 站银河快报推送回调
    # ------------------------------------------------------------------

    async def _send_bilibili_post(
        self,
        post: BilibiliPost,
        image_paths: list[Path],
        sessions: list[str],
    ) -> int:
        """推送一条 B 站动态到全部订阅会话，返回实际送达数。"""
        if not sessions:
            logger.info(
                "[HD2] matched Bilibili dynamic %s, but no session subscribed",
                post.dynamic_id,
            )
            return 0
        text = post.text or "（该动态没有文字内容）"
        image_bytes: list[bytes] = []
        for path in image_paths:
            try:
                image_bytes.append(await asyncio.to_thread(path.read_bytes))
            except OSError as exc:
                logger.warning(
                    "[HD2] Bilibili image unreadable: path=%s error=%s",
                    path,
                    exc,
                )
        delivered = 0
        for stream_id in sessions:
            try:
                sent = await self._send_text(stream_id, f"【{post.author}】\n{text}")
                for data in image_bytes:
                    sent = await self._send_image_bytes(stream_id, data) and sent
                sent = (
                    await self._send_text(stream_id, f"\n原动态：{post.url}")
                    and sent
                )
            except Exception as e:
                logger.warning(
                    "[HD2] Bilibili push failed: session=%s dynamic=%s error=%s",
                    stream_id,
                    post.dynamic_id,
                    e,
                )
                continue
            # 全部环节都成功才计为送达，否则推送重试机制无法触发。
            if sent:
                delivered += 1
            else:
                logger.warning(
                    "[HD2] Bilibili push not delivered: session=%s dynamic=%s",
                    stream_id,
                    post.dynamic_id,
                )
        if delivered == 0:
            raise RuntimeError(
                f"Bilibili dynamic {post.dynamic_id} failed for all subscribed groups"
            )
        return delivered

    # ------------------------------------------------------------------
    # 帮助
    # ------------------------------------------------------------------

    @Command(
        "hd2",
        description="Helldivers 2 插件简短帮助",
        pattern=r"(?i)^\s*[/!]?\s*(?:hd2|helldivers)\s*$",
    )
    async def cmd_help(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        await self._send_text(stream_id, HELP_TEXT)
        return True, "已发送 HD2 帮助", _CMD_WEIGHT

    @Command(
        "hd2help",
        description="Helldivers 2 插件全部指令说明",
        pattern=r"(?i)^\s*[/!]?\s*(?:hd2help|hdhelp)\s*$",
    )
    async def cmd_hdhelp(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        await self._send_text(stream_id, HDHELP_TEXT)
        return True, "已发送 HD2 全部指令说明", _CMD_WEIGHT

    # ------------------------------------------------------------------
    # 战况图片指令
    # ------------------------------------------------------------------

    @Command(
        "hd2stats",
        description="查看当前银河战争实时统计（图片）",
        pattern=r"(?i)^\s*[/!]?\s*hd2stats\s*$",
    )
    async def cmd_stats(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        try:
            paths = await self._svc().get_stats_images(realtime=True)
        except Exception as e:
            logger.exception(f"[HD2] /hd2stats error: {e}")
            await self._send_text(stream_id, "❌ 获取银河战争统计失败，请稍后重试。")
            return True, "获取银河战争统计失败", _CMD_WEIGHT
        await self._send_images(
            stream_id, paths, fallback="❌ 获取银河战争统计失败，请稍后重试。"
        )
        return True, f"已发送银河战争统计（{len(paths)} 张）", _CMD_WEIGHT

    @Command(
        "dashboard",
        description="银河战争总览 Dashboard（图片，实时数据）",
        pattern=r"(?i)^\s*[/!]?\s*(?:dashboard|总览|战况总览)\s*$",
    )
    async def cmd_dashboard(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        try:
            paths = await self._svc().get_dashboard_image(realtime=True)
        except Exception as e:
            logger.exception(f"[HD2] /dashboard error: {e}")
            await self._send_text(stream_id, "❌ 获取战争总览失败，请稍后重试。")
            return True, "获取战争总览失败", _CMD_WEIGHT
        await self._send_images(
            stream_id, paths, fallback="❌ 获取战争总览失败，请稍后重试。"
        )
        return True, f"已发送战争总览（{len(paths)} 张）", _CMD_WEIGHT

    @Command(
        "order",
        description="获取当前活跃的最高命令 / 主要任务（图片）",
        pattern=r"(?i)^\s*[/!]?\s*(?:order|major_order|最高命令)\s*$",
    )
    async def cmd_order(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        try:
            paths = await self._svc().get_order_images()
        except Exception as e:
            logger.exception(f"[HD2] /order error: {e}")
            await self._send_text(stream_id, "❌ 获取最高命令失败，请稍后重试。")
            return True, "获取最高命令失败", _CMD_WEIGHT
        await self._send_images(
            stream_id, paths, fallback="❌ 获取最高命令失败，请稍后重试。"
        )
        return True, f"已发送最高命令（{len(paths)} 张）", _CMD_WEIGHT

    @Command(
        "personal_order",
        description="查看个人任务 Personal Order（图片）",
        pattern=r"(?i)^\s*[/!]?\s*(?:personal_order|po|个人任务)\s*$",
    )
    async def cmd_personal_order(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        try:
            paths = await self._svc().get_personal_order_image()
        except Exception as e:
            logger.exception(f"[HD2] /personal_order error: {e}")
            await self._send_text(stream_id, "❌ 获取个人任务失败，请稍后重试。")
            return True, "获取个人任务失败", _CMD_WEIGHT
        await self._send_images(
            stream_id, paths, fallback="❌ 获取个人任务失败，请稍后重试。"
        )
        return True, f"已发送个人任务（{len(paths)} 张）", _CMD_WEIGHT

    @Command(
        "map",
        description="生成当前银河战争地图图片",
        pattern=r"(?i)^\s*[/!]?\s*(?:map|地图)\s*$",
    )
    async def cmd_map(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        try:
            caption, path = await self._svc().get_map_result()
        except Exception as e:
            logger.exception(f"[HD2] /map error: {e}")
            await self._send_text(stream_id, "❌ 生成地图失败，请稍后重试。")
            return True, "生成地图失败", _CMD_WEIGHT

        if path is not None:
            text_sent = await self._send_text(stream_id, caption + "\n")
            image_sent = await self._send_image_path(stream_id, path)
            if image_sent:
                return True, "已发送银河战争地图", _CMD_WEIGHT
            # 文本已送达时不再重复 caption，仅补一条失败说明。
            note = (
                f"（图片发送失败: {path}）"
                if text_sent
                else caption + f"\n（图片发送失败: {path}）"
            )
            await self._send_text(stream_id, note)
            return True, "地图图片发送失败，已发送文本", _CMD_WEIGHT
        await self._send_text(stream_id, caption)
        return True, "已发送地图文本信息", _CMD_WEIGHT

    @Command(
        "warfront",
        description="查看特定阵营战线（图片），用法: /warfront Terminids",
        pattern=r"(?i)^\s*[/!]?\s*(?:warfront|战线)(?:\s+(?P<faction>.+?))?\s*$",
    )
    async def cmd_warfront(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        faction = self._arg(kwargs, "faction", {"warfront", "战线"})
        try:
            err, paths = await self._svc().get_warfront_image(faction)
        except Exception as e:
            logger.exception(f"[HD2] /warfront error: {e}")
            await self._send_text(stream_id, "❌ 获取战线信息失败，请稍后重试。")
            return True, "获取战线信息失败", _CMD_WEIGHT
        if err:
            await self._send_text(stream_id, err)
            return True, "已发送战线用法提示", _CMD_WEIGHT
        await self._send_images(
            stream_id, paths, fallback="❌ 获取战线信息失败，请稍后重试。"
        )
        return True, f"已发送战线战况（{len(paths)} 张）", _CMD_WEIGHT

    @Command(
        "global_events",
        description="查看全球事件（图片）",
        pattern=r"(?i)^\s*[/!]?\s*(?:global_events|全球事件|events)\s*$",
    )
    async def cmd_global_events(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        try:
            paths = await self._svc().get_global_events_image()
        except Exception as e:
            logger.exception(f"[HD2] /global_events error: {e}")
            await self._send_text(stream_id, "❌ 获取全球事件失败，请稍后重试。")
            return True, "获取全球事件失败", _CMD_WEIGHT
        await self._send_images(
            stream_id, paths, fallback="❌ 获取全球事件失败，请稍后重试。"
        )
        return True, f"已发送全球事件（{len(paths)} 张）", _CMD_WEIGHT

    @Command(
        "steam",
        description="获取最新 Steam 新闻（图片优先，文本兜底）",
        pattern=r"(?i)^\s*[/!]?\s*steam\s*$",
    )
    async def cmd_steam(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        try:
            paths = await self._svc().get_steam_images()
        except Exception as e:
            logger.exception(f"[HD2] /steam image error: {e}")
            paths = []
        if paths:
            await self._send_images(
                stream_id, paths, fallback="❌ Steam 新闻图片生成失败，请稍后重试。"
            )
            return True, f"已发送 Steam 新闻（{len(paths)} 张）", _CMD_WEIGHT
        # Pillow/远程图片不可用时回退文本输出。
        try:
            msg = await self._svc().get_steam_message()
        except Exception as e:
            logger.exception(f"[HD2] /steam fallback error: {e}")
            msg = "❌ 获取 Steam 更新日志失败，请稍后重试。"
        await self._send_text(stream_id, msg)
        return True, "已发送 Steam 更新文本", _CMD_WEIGHT

    # ------------------------------------------------------------------
    # 文本查询指令
    # ------------------------------------------------------------------

    @Command(
        "wiki",
        description="查询 Helldivers Wiki，用法: /wiki <关键词> [-f 全文]",
        pattern=r"(?i)^\s*[/!]?\s*(?:wiki|维基|百科)(?:\s+(?P<query>.+?))?\s*$",
    )
    async def cmd_wiki(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        args = self._arg(kwargs, "query", {"wiki", "维基", "百科"}).split()
        # -f / --full 开关：返回全文而不是摘要
        full = False
        if "-f" in args or "--full" in args:
            full = True
            args = [a for a in args if a not in ("-f", "--full")]
        query = " ".join(args).strip()
        try:
            msg = await self._svc().get_wiki_message(query, full=full)
        except Exception as e:
            logger.exception(f"[HD2] /wiki error: {e}")
            msg = "❌ Wiki 查询失败，请稍后重试。"
        await self._send_text(stream_id, msg)
        return True, "已发送 Wiki 查询结果", _CMD_WEIGHT

    @Command(
        "hd2data",
        description="军需簿查询：/hd2data <名称>，武器/战备/护甲/敌人",
        pattern=(
            r"(?i)^\s*[/!]?\s*(?:hd2data|军需簿|数据库|装备|武器库)"
            r"(?:\s+(?P<query>.+?))?\s*$"
        ),
    )
    async def cmd_arsenal_data(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        query = self._arg(
            kwargs, "query", {"hd2data", "军需簿", "数据库", "装备", "武器库"}
        )
        if not query:
            await self._send_text(
                stream_id,
                "用法: /hd2data <名称>（武器/战备/护甲/敌人）\n"
                "例如: /hd2data 磁轨炮 · /hd2data 电喷 · /hd2data 泰坦",
            )
            return True, "已发送军需簿用法", _CMD_WEIGHT
        try:
            result = await self._svc().get_arsenal_image(query)
            if isinstance(result, str):
                await self._send_text(stream_id, result)
                return True, "已发送军需簿查询结果", _CMD_WEIGHT
            await self._send_images(stream_id, result, fallback="❌ 军需簿查询失败。")
            return True, f"已发送军需簿图片（{len(result)} 张）", _CMD_WEIGHT
        except Exception as e:
            logger.exception(f"[HD2] /hd2data error: {e}")
            await self._send_text(stream_id, "❌ 军需簿查询失败，请稍后重试。")
            return True, "军需簿查询失败", _CMD_WEIGHT

    @Command(
        "hd2ping",
        description="自诊断：各数据源健康、缓存年龄与关键配置一览",
        pattern=r"(?i)^\s*[/!]?\s*(?:hd2ping|诊断|自检)\s*$",
    )
    async def cmd_hd2ping(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        svc = self._svc()
        now = time.time()
        client = svc.client

        monitor = self.bilibili_monitor
        if monitor is not None:
            bilibili_part = (
                f"UID {monitor.uid}"
                + ("（带登录态）" if monitor.has_login_cookie else "（游客）")
            )
        else:
            bilibili_part = "未启用"
        companion_part = (
            str(self.companion_backend) if self.companion_enabled else "关"
        )
        info_lines = [
            f"⏱ 运行 {humanize_uptime(HEALTH.uptime_seconds)} · 战争 ID "
            f"{client.war_id} · 主API {client.base_url} · 代理: "
            f"{'已配置' if client.proxy_url else '未配置'}",
            (
                f"翻译: {'开(' + str(svc.translator.mode) + ')' if svc.enable_translation else '关'}"
                f" · Companion: {companion_part}"
                f" · 军需簿: {'开' if svc.arsenal_client is not None else '关'}"
                f" · B站: {bilibili_part}"
            ),
        ]

        ages: list[str] = []
        for name in (
            svc.CACHE_WAR_STATUS,
            svc.CACHE_ORDERS,
            svc.CACHE_DISPATCHES,
            svc.CACHE_STEAM,
            svc.CACHE_PLANETS,
            svc.CACHE_CAMPAIGNS,
            svc.CACHE_SPACE_STATIONS,
        ):
            entry = await svc.cache.get_entry(name)
            age = humanize_age(now - entry.updated_at) if entry else "无缓存"
            ages.append(f"{name} {age}")
        cache_lines = [" · ".join(ages[:4]), " · ".join(ages[4:])]

        arsenal = svc.arsenal_client
        if arsenal is not None:
            catalog_path = arsenal.cache_dir / "catalog.json"
            enemies_path = arsenal.cache_dir / "enemies.json"

            def _arsenal_cache_mtimes() -> tuple[float, float]:
                return (
                    catalog_path.stat().st_mtime if catalog_path.is_file() else 0.0,
                    enemies_path.stat().st_mtime if enemies_path.is_file() else 0.0,
                )

            catalog_mtime, enemies_mtime = await asyncio.to_thread(
                _arsenal_cache_mtimes
            )
            parts = ["军需簿:"]
            if catalog_mtime > 0:
                detail = f"目录 {humanize_age(now - catalog_mtime)}"
                if arsenal.data_version:
                    detail += f" (v{arsenal.data_version})"
                detail += f" {arsenal.item_count} 条"
                parts.append(detail)
            else:
                parts.append("目录未下载")
            if enemies_mtime > 0:
                parts.append(
                    f"敌人表 {humanize_age(now - enemies_mtime)}"
                    f" {arsenal.enemy_count} 种"
                )
            cache_lines.append(" · ".join(parts))

        await self._send_text(
            stream_id,
            build_ping_report(
                HEALTH.snapshot(),
                title=f"🩺 HD2 自诊断 {PLUGIN_VERSION}",
                info_lines=info_lines,
                cache_lines=cache_lines,
                expected_sources=EXPECTED_SOURCES,
                now=now,
            ),
        )
        return True, "已发送自诊断报告", _CMD_WEIGHT

    # ------------------------------------------------------------------
    # Companion 截图指令
    # ------------------------------------------------------------------

    @Command(
        "hd2news",
        description="截图 Companion 最新新闻（翻译后返回）",
        pattern=r"(?i)^\s*[/!]?\s*hd2news\s*$",
    )
    async def cmd_news(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        target = companion_latest_news_target()
        try:
            path = await self._capture_companion_page(target)
        except Exception as e:
            logger.exception(f"[HD2] /hd2news Companion capture failed: {e}")
            try:
                _, paths = await self._svc().get_news_image(1)
            except Exception as fallback_error:
                logger.warning(
                    f"[HD2] /hd2news local fallback failed: {fallback_error}"
                )
                paths = []
            if paths:
                await self._send_text(
                    stream_id,
                    "⚠️ Companion 翻译暂时繁忙，已为你展示基础新闻卡片，"
                    "稍后重试可获取完整翻译截图。",
                )
                await self._send_images(
                    stream_id, paths[:1], fallback="❌ 新闻图片发送失败。"
                )
            else:
                await self._send_text(
                    stream_id, "❌ Companion 最新新闻暂时不可用，请稍后重试。"
                )
            return True, "Companion 新闻获取失败，已发送兜底内容", _CMD_WEIGHT

        prefix = None
        if self._served_companion_stale(target.kind):
            prefix = (
                "📰 翻译快照（内容稍旧），后台正在刷新，"
                "稍后重试可获取最新翻译。\n"
            )
        await self._send_mixed(stream_id, text=prefix, image_paths=[path])
        return True, "已发送 Companion 最新新闻", _CMD_WEIGHT

    @Command(
        "companion",
        description="截图 Helldivers Companion 首页并翻译",
        pattern=r"(?i)^\s*[/!]?\s*(?:companion|首页|companion_home)\s*$",
    )
    async def cmd_companion(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        target = companion_homepage_target()
        try:
            path = await self._capture_companion_page(target)
            await self._send_images(stream_id, [path], fallback="❌ Companion 首页截图失败。")
            return True, "已发送 Companion 首页截图", _CMD_WEIGHT
        except Exception as e:
            logger.exception(f"[HD2] /companion Companion capture failed: {e}")
            stale = self._stale_fallback_path(target)
            if stale:
                await self._send_text(
                    stream_id, "⚠️ Companion 首页暂时加载失败，返回上次缓存截图。"
                )
                await self._send_images(stream_id, [stale], fallback="❌ 缓存截图不可用。")
            else:
                await self._send_text(stream_id, "❌ Companion 首页截图失败，请稍后重试。")
            return True, "Companion 首页获取失败", _CMD_WEIGHT

    @Command(
        "dss",
        description="截图 Companion DSS 页面并附中文情报",
        pattern=r"(?i)^\s*[/!]?\s*(?:dss|空间站|民主空间站)\s*$",
    )
    async def cmd_dss(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        target = companion_dss_target()
        try:
            path = await self._capture_companion_page(target)
        except Exception as e:
            logger.exception(f"[HD2] /dss Companion capture failed: {e}")
            stale = self._stale_fallback_path(target)
            if stale:
                path = stale
            else:
                await self._send_text(stream_id, "❌ Companion DSS 截图失败，请稍后重试。")
                return True, "Companion DSS 截图失败", _CMD_WEIGHT

        try:
            message = await self._svc().get_dss_message()
        except Exception as e:
            logger.warning(f"[HD2] /dss translated text failed: {e}")
            message = "民主空间站中文情报暂时不可用。"
        await self._send_mixed(stream_id, text=message, image_paths=[path])
        return True, "已发送 DSS 图文", _CMD_WEIGHT

    @Command(
        "planet",
        description="截图 Companion 星球页，用法: /planet <名称/编号/链接>",
        pattern=r"(?i)^\s*[/!]?\s*(?:planet|星球)(?:\s+(?P<query>.+?))?\s*$",
    )
    async def cmd_planet(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        query = self._arg(kwargs, "query", {"planet", "星球"})
        if not query:
            await self._send_text(
                stream_id,
                "❌ 用法: /planet <星球名称、编号、slug 或 Companion 链接>",
            )
            return True, "已发送 planet 用法", _CMD_WEIGHT

        try:
            if "://" in query or query.lstrip("#/").casefold().startswith(
                "hellpad/planets/"
            ):
                target = parse_companion_planet_target(query)
                if target.value.endswith(")"):
                    fallback_query = _planet_search_query(target.value)
                else:
                    # 旧格式链接（无编号后缀）会被新版站点弹回首页，
                    # 用战争数据把编号补全后再构建目标。
                    err, _, slug = await self._svc().resolve_companion_planet(
                        _planet_search_query(target.value)
                    )
                    if err or not slug:
                        await self._send_text(stream_id, err or "❌ 无法解析该星球。")
                        return True, "无法解析该星球", _CMD_WEIGHT
                    target = parse_companion_planet_target(slug)
                    fallback_query = _planet_search_query(target.value)
            else:
                err, canonical_name, slug = await self._svc().resolve_companion_planet(
                    query
                )
                if err or not canonical_name or not slug:
                    if query.isdigit():
                        await self._send_text(
                            stream_id, err or "❌ 无法解析该星球。"
                        )
                        return True, "无法解析该星球", _CMD_WEIGHT
                    try:
                        target = parse_companion_planet_target(query)
                    except CompanionTargetError:
                        await self._send_text(
                            stream_id, err or "❌ 无法解析该星球。"
                        )
                        return True, "无法解析该星球", _CMD_WEIGHT
                    fallback_query = _planet_search_query(target.value)
                else:
                    target = parse_companion_planet_target(slug)
                    fallback_query = canonical_name
        except CompanionTargetError as e:
            await self._send_text(stream_id, f"❌ {e}")
            return True, "星球目标解析失败", _CMD_WEIGHT
        except Exception as e:
            logger.exception(f"[HD2] /planet resolve error: {e}")
            await self._send_text(stream_id, "❌ 解析星球失败，请稍后重试。")
            return True, "解析星球失败", _CMD_WEIGHT

        try:
            path = await self._capture_companion_page(target)
            try:
                message = await self._svc().get_planet_message(fallback_query)
            except Exception as message_error:
                logger.warning(
                    f"[HD2] /planet translated text failed: {message_error}"
                )
                message = ""
            await self._send_mixed(stream_id, text=message or None, image_paths=[path])
            return True, "已发送星球详情", _CMD_WEIGHT
        except Exception as e:
            logger.exception(f"[HD2] /planet Companion capture failed: {e}")
            stale = self._stale_fallback_path(target)
            if stale:
                await self._send_text(
                    stream_id, "⚠️ Companion 星球页暂时加载失败，返回上次缓存截图。"
                )
                await self._send_images(stream_id, [stale], fallback="❌ 缓存截图不可用。")
            else:
                await self._send_text(stream_id, "❌ Companion 星球截图失败，请稍后重试。")
            return True, "Companion 星球截图失败", _CMD_WEIGHT

    @Command(
        "hd2refresh",
        description="强制刷新 Companion 截图缓存（跳过缓存重新截图+翻译）",
        pattern=r"(?i)^\s*[/!]?\s*(?:hd2refresh|刷新缓存|hd2clear)\s*$",
    )
    async def cmd_refresh(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        if not self.companion_enabled or self.companion_backend != "playwright":
            await self._send_text(
                stream_id, "❌ 当前未启用 Playwright Companion 截图，无需刷新。"
            )
            return True, "Companion 截图未启用", _CMD_WEIGHT
        targets = [
            companion_latest_news_target(),
            companion_dss_target(),
        ]
        if self.companion_playwright is not None:
            targets.append(companion_homepage_target())
        await self._send_text(
            stream_id, "🔄 正在强制刷新 Companion 截图缓存，请稍候…"
        )
        results: list[str] = []
        for target in targets:
            try:
                await self._capture_companion_page(target, force=True)
                results.append(f"✅ {target.label}")
            except Exception as e:
                logger.warning(f"[HD2] /hd2refresh {target.kind} failed: {e}")
                results.append(f"❌ {target.label}（{e}）")
        await self._send_text(
            stream_id, "Companion 缓存刷新完成：\n" + "\n".join(results)
        )
        return True, "Companion 缓存刷新完成", _CMD_WEIGHT

    # ------------------------------------------------------------------
    # 订阅开关（群聊限定）
    # ------------------------------------------------------------------

    def _group_only_reply(self, kwargs: dict[str, Any]) -> str | None:
        if self._is_group(kwargs):
            return None
        return "ℹ️ 该订阅功能仅支持在群聊中使用。"

    @Command(
        "hd2news_subscribe",
        description="在当前群订阅 Companion 新闻推送",
        pattern=r"(?i)^\s*[/!]?\s*(?:hd2news订阅|hd2news\s*订阅|news_subscribe)\s*$",
    )
    async def cmd_news_subscribe(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        if (reply := self._group_only_reply(kwargs)) is not None:
            await self._send_text(stream_id, reply)
            return True, "私聊中拒绝订阅", _CMD_WEIGHT
        monitor = self.companion_news_monitor
        if monitor is None:
            await self._send_text(stream_id, "❌ Companion 新闻推送尚未初始化。")
            return True, "Companion 新闻推送未初始化", _CMD_WEIGHT
        if not self.companion_enabled or self.companion_backend != "playwright":
            await self._send_text(
                stream_id,
                "❌ 需先启用 Companion Playwright 截图（配置 enable_companion_screenshots "
                "并选择 playwright 后端），才能订阅新闻推送。",
            )
            return True, "Companion 截图未启用", _CMD_WEIGHT
        if not self._companion_news_push_enabled:
            await self._send_text(
                stream_id,
                "❌ 新闻推送总开关未启用，请在插件配置中开启 "
                "companion_news_push_enabled 后重载插件。",
            )
            return True, "新闻推送总开关未启用", _CMD_WEIGHT
        if not bool(self.config.companion_warmup_enabled):
            await self._send_text(
                stream_id,
                "❌ Companion 后台预热未启用，新闻推送依赖预热循环检测变更。"
                "请在配置中开启 companion_warmup_enabled。",
            )
            return True, "后台预热未启用", _CMD_WEIGHT
        if monitor.subscribe(stream_id):
            await self._send_text(
                stream_id, "✅ 已订阅 Companion 新闻推送，有新新闻时将自动同步到本群。"
            )
            return True, "已订阅 Companion 新闻推送", _CMD_WEIGHT
        await self._send_text(stream_id, "ℹ️ 本群已经订阅 Companion 新闻推送。")
        return True, "重复订阅", _CMD_WEIGHT

    @Command(
        "hd2news_unsubscribe",
        description="取消当前群的 Companion 新闻推送",
        pattern=r"(?i)^\s*[/!]?\s*(?:hd2news退订|hd2news\s*退订|news_unsubscribe)\s*$",
    )
    async def cmd_news_unsubscribe(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        monitor = self.companion_news_monitor
        if monitor is None:
            await self._send_text(stream_id, "ℹ️ Companion 新闻推送当前未启用。")
            return True, "Companion 新闻推送未启用", _CMD_WEIGHT
        if stream_id and monitor.unsubscribe(stream_id):
            await self._send_text(stream_id, "✅ 已取消本群的 Companion 新闻推送。")
            return True, "已退订 Companion 新闻推送", _CMD_WEIGHT
        await self._send_text(stream_id, "ℹ️ 本群尚未订阅 Companion 新闻推送。")
        return True, "尚未订阅", _CMD_WEIGHT

    @Command(
        "galaxy_news",
        description="立即获取并发送最新一期 B站银河快报",
        pattern=(
            r"(?i)^\s*[/!]?\s*(?:银河快报|galaxy_news)(?:推送)?\s*$"
        ),
    )
    async def cmd_galaxy_news(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        monitor = self.bilibili_monitor
        if monitor is None:
            await self._send_text(stream_id, "❌ 银河快报服务尚未初始化完成。")
            return True, "银河快报服务未初始化", _CMD_WEIGHT
        try:
            posts = await monitor.fetch_posts()
            post = monitor.latest_matching(posts)
            if post is None:
                previews = [
                    f"{item.dynamic_id}:{item.text[:40]!r}" for item in posts[:5]
                ]
                logger.warning(
                    "[HD2] no Bilibili keyword match: keyword=%r posts=%s previews=%s",
                    monitor.keyword,
                    len(posts),
                    previews,
                )
                if posts and not any(item.text for item in posts):
                    await self._send_text(
                        stream_id,
                        "❌ B站返回了动态，但正文结构暂时无法识别，"
                        "请查看日志中的动态 ID。",
                    )
                    return True, "B站动态结构无法识别", _CMD_WEIGHT
                await self._send_text(
                    stream_id, f"ℹ️ 最近的动态中没有找到关键字“{monitor.keyword}”。"
                )
                return True, "未匹配到银河快报动态", _CMD_WEIGHT
            paths = await monitor.download_images(post)
            await self._send_mixed(
                stream_id, text=f"【{post.author}】\n{post.text}", image_paths=paths
            )
            await self._send_text(stream_id, f"\n原动态：{post.url}")
        except (BilibiliAuthenticationError, BilibiliRiskControlError) as e:
            logger.warning(f"[HD2] manual Bilibili galaxy news blocked: {e}")
            await self._send_text(stream_id, f"❌ {e}")
        except Exception as e:
            logger.warning(f"[HD2] manual Bilibili galaxy news error: {e}")
            await self._send_text(stream_id, "❌ 获取银河快报失败，请查看宿主日志。")
        return True, "已处理银河快报请求", _CMD_WEIGHT

    @Command(
        "galaxy_news_subscribe",
        description="在当前群订阅 B站“银河快报”动态推送",
        pattern=(
            r"(?i)^\s*[/!]?\s*(?:银河快报订阅|银河快报\s*订阅"
            r"|galaxy_news_subscribe)\s*$"
        ),
    )
    async def cmd_galaxy_news_subscribe(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        if (reply := self._group_only_reply(kwargs)) is not None:
            await self._send_text(stream_id, reply)
            return True, "私聊中拒绝订阅", _CMD_WEIGHT
        if self.bilibili_monitor is None or not self.bilibili_auto_enabled:
            await self._send_text(
                stream_id, "❌ 银河快报监听未启用，请先在插件配置中开启。"
            )
            return True, "银河快报监听未启用", _CMD_WEIGHT
        if not self.bilibili_monitor.has_login_cookie:
            await self._send_text(
                stream_id,
                "❌ 银河快报监听缺少有效 B站登录 Cookie（必须包含 SESSDATA），"
                "请在插件配置中填写后重载插件。",
            )
            return True, "缺少 B站登录 Cookie", _CMD_WEIGHT
        if self.bilibili_monitor.subscribe(stream_id):
            await self._send_text(
                stream_id, "✅ 已订阅银河快报，新动态将自动同步到本群。"
            )
            return True, "已订阅银河快报", _CMD_WEIGHT
        await self._send_text(stream_id, "ℹ️ 本群已经订阅银河快报。")
        return True, "重复订阅", _CMD_WEIGHT

    @Command(
        "galaxy_news_unsubscribe",
        description="取消当前群的 B站“银河快报”动态推送",
        pattern=(
            r"(?i)^\s*[/!]?\s*(?:银河快报退订|银河快报\s*退订"
            r"|galaxy_news_unsubscribe)\s*$"
        ),
    )
    async def cmd_galaxy_news_unsubscribe(
        self, **kwargs: Any
    ) -> tuple[bool, str, int]:
        stream_id = self._session_key(kwargs)
        if self.bilibili_monitor is None:
            await self._send_text(stream_id, "ℹ️ 银河快报监听当前未启用。")
            return True, "银河快报监听未启用", _CMD_WEIGHT
        if stream_id and self.bilibili_monitor.unsubscribe(stream_id):
            await self._send_text(stream_id, "✅ 已取消本群的银河快报订阅。")
            return True, "已退订银河快报", _CMD_WEIGHT
        await self._send_text(stream_id, "ℹ️ 本群尚未订阅银河快报。")
        return True, "尚未订阅", _CMD_WEIGHT


def create_plugin() -> HelldiversPlugin:
    """MaiBot Runner 插件工厂入口。"""
    return HelldiversPlugin()
