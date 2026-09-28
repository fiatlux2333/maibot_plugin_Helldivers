"""插件配置模型：由 AstrBot 版 _conf_schema.json (v1.9.0) 等价移植。

Runner 首次加载时据此自动生成 config.toml 并在 WebUI 呈现；
字段顺序即 WebUI 展示顺序。
"""

from __future__ import annotations

from maibot_sdk import Field, PluginConfigBase


class _PluginSection(PluginConfigBase):
    """config.toml 的保留 ``[plugin]`` 节（SDK 2.8.x 配置版本策略必需）。"""

    __ui_label__ = "保留字段"

    config_version: str = Field(
        default="1",
        description="配置版本号（保留字段，勿修改）",
    )


class HD2Config(PluginConfigBase):
    """Helldivers 2 银河战争情报助手配置。"""

    __ui_label__ = "Helldivers 2 情报助手"

    # ---- 保留节（Runner 维护） ----
    plugin: _PluginSection = Field(
        default_factory=_PluginSection,
        description="插件配置元信息（保留节，由 Runner 维护）",
    )

    # ---- API 基础 ----
    api_base: str = Field(
        default="https://api.helldivers2.dev",
        description="Helldivers 2 社区 API 根地址（默认官方社区 API）",
    )
    war_id: int = Field(
        default=801,
        description="当前战争 ID（赛季变更时可能需要修改，当前默认 801）",
    )
    api_contact: str = Field(
        default="",
        description="API 联系邮箱 (X-Super-Contact)；建议填写真实邮箱，遵守 API 礼仪",
    )
    api_client_name: str = Field(
        default="maibot_plugin_Helldivers",
        description="API 客户端标识 (X-Super-Client)",
    )
    api_user_agent: str = Field(
        default="maibot_plugin_Helldivers/1.0.0",
        description="User-Agent",
    )
    api_timeout: int = Field(
        default=20,
        description="API 请求超时（秒）",
    )
    proxy_url: str = Field(
        default="",
        description="HTTP 代理（可选），例如 http://127.0.0.1:7890，留空不使用",
    )

    # ---- Companion 截图 ----
    enable_companion_screenshots: bool = Field(
        default=True,
        description=(
            "启用 Helldivers Companion 图片指令（/hd2news、/companion、/dss、"
            "/planet 的原网页截图）；失败时返回错误提示"
        ),
    )
    companion_render_backend: str = Field(
        default="playwright",
        description=(
            "Companion 图片后端：playwright=容器内 Chromium 原网页截图并支持翻译"
            "（推荐）；local=Pillow 数据卡片；browserless=仅在关闭翻译时使用远程"
            "英文网页截图"
        ),
    )
    companion_browserless_url: str = Field(
        default="http://browserless:3000",
        description=(
            "Browserless 截图服务地址；同一 Docker 网络可使用 "
            "http://browserless:3000，也可填写 Browserless Cloud 地址"
        ),
    )
    companion_browserless_token: str = Field(
        default="",
        description="Browserless Token（可选）；自建服务未配置 Token 时留空，勿提交到仓库",
    )
    companion_browserless_proxy_url: str = Field(
        default="",
        description="访问 Browserless 服务所用代理（可选）；同 Docker 网络时通常留空",
    )
    companion_screenshot_timeout: int = Field(
        default=60,
        description="Companion 截图总超时（秒）",
    )
    companion_screenshot_wait_ms: int = Field(
        default=5000,
        description="Companion 页面加载后的额外等待时间（毫秒）；SPA 页面建议 3000-8000",
    )
    companion_page_load_timeout: float = Field(
        default=40.0,
        description=(
            "Companion 页面数据加载等待时间（秒）；等待 PLEASE WAIT DEMOCRATICALLY "
            "消失或目标页面就绪，国内服务器建议 30-40"
        ),
    )
    companion_translation_timeout: float = Field(
        default=60.0,
        description=(
            "Companion 前台翻译等待时间（秒）；免费模型建议 45-90，超时后发送"
            "已完成的部分翻译，后台继续写入缓存"
        ),
    )
    companion_translation_batch_timeout: float = Field(
        default=20.0,
        description=(
            "Companion 单批翻译等待时间（秒）；每批最多 16 段，免费模型建议 15-25，"
            "且不得高于前台翻译等待时间"
        ),
    )
    companion_screenshot_cache_ttl: int = Field(
        default=300,
        description="Companion 截图缓存时间（秒）",
    )
    companion_screenshot_max_bytes: int = Field(
        default=12582912,
        description="Companion 单张截图最大字节数",
    )
    companion_screenshot_max_pixels: int = Field(
        default=20000000,
        description="Companion 单张截图最大像素数",
    )
    companion_show_inactive: bool = Field(
        default=False,
        description=(
            "Companion 首页显示低活跃度战役卡片（约 +1.5s）；注意该设置会持久化到"
            "网站，可能影响浏览器访问 Companion 的默认状态"
        ),
    )
    companion_warmup_enabled: bool = Field(
        default=True,
        description=(
            "Companion 截图后台预热：后台定时截图并预翻译，用户请求时直接返回"
            "已翻译缓存截图，无需等待翻译 API"
        ),
    )
    companion_warmup_interval: int = Field(
        default=300,
        description="Companion 后台预热间隔（秒）；建议 300，最小 60",
    )
    companion_warmup_kinds: str = Field(
        default="news_latest,station,homepage",
        description=(
            "Companion 后台预热页面（逗号分隔）：news_latest=最新新闻、"
            "station=民主空间站、homepage=首页；默认含 homepage 以便 "
            "/companion 命中热缓存（MaiBot 命令有调用时长上限）"
        ),
    )
    companion_news_push_enabled: bool = Field(
        default=False,
        description=(
            "启用 Companion 新闻推送：开启后在目标群发送 /hd2news订阅，"
            "Companion 新闻更新时自动推送翻译截图；需同时启用截图与后台预热"
        ),
    )

    # ---- B 站银河快报 ----
    enable_bilibili_galaxy_news: bool = Field(
        default=False,
        description=(
            "启用 B站银河快报自动推送：开启后在目标群发送 /银河快报订阅；"
            "首次启动只建立动态基线，不补发旧内容"
        ),
    )
    bilibili_uid: str = Field(
        default="3546777720457465",
        description="B站银河快报 UP主 UID（默认是“银河快报”账号的空间 UID）",
    )
    bilibili_keyword: str = Field(
        default="银河快报",
        description="B站动态监听关键字；动态文字包含此关键字时转发，忽略大小写",
    )
    bilibili_poll_interval: int = Field(
        default=300,
        description="B站动态轮询间隔（秒）；最小 60，建议 300 或更长，降低风控概率",
    )
    bilibili_cookie: str = Field(
        default="",
        description=(
            "B站 Cookie（后台监听必填）：从已登录 B站的浏览器请求中复制完整 "
            "Cookie，必须包含 SESSDATA；请勿公开或提交到仓库，修改后需重载插件"
        ),
    )
    bilibili_image_max_bytes: int = Field(
        default=16777216,
        description="B站单张图片最大字节数（默认 16 MiB，超限时缓存层自动降质重编码）",
    )
    bilibili_image_max_pixels: int = Field(
        default=64000000,
        description=(
            "B站单张长图最大解码像素（银河快报常用超长图；默认 6400 万像素，"
            "仍保留解压炸弹防护）"
        ),
    )

    # ---- 缓存与限速 ----
    enable_background_refresh: bool = Field(
        default=True,
        description="启用后台定时同步；关闭后仅在缓存缺失时按需拉取",
    )
    cache_update_interval: int = Field(
        default=300,
        description="API 缓存刷新间隔（秒）；建议 120-300，过短容易触发 429 限流",
    )
    request_delay: int = Field(
        default=6,
        description="批量请求间隔（秒）；刷新多类数据时的请求间隔，建议 ≥3",
    )
    min_request_interval: float = Field(
        default=3.0,
        description="任意两次 API 请求最小间隔（秒）；全局限流，降低 429 概率",
    )
    retry_base_delay: float = Field(
        default=3.0,
        description="API 重试基础延迟（秒）",
    )
    retry_max_delay: float = Field(
        default=15.0,
        description="API 重试最大延迟（秒）",
    )
    retry_max_attempts: int = Field(
        default=2,
        description="API 最大重试次数",
    )

    # ---- AI 翻译 ----
    enable_translation: bool = Field(
        default=True,
        description="启用 AI 智能翻译：将最高命令/快讯/Steam 更新翻译为中文",
    )
    translation_mode: str = Field(
        default="auto",
        description=(
            "翻译模式：auto=按地址和 Key 自动判断；builtin=第三方翻译接口；"
            "openai=OpenAI 兼容 chat/completions"
        ),
    )
    translation_api_url: str = Field(
        default="https://uapis.cn/api/v1/ai/translate",
        description=(
            "翻译 API 地址；builtin 模式填完整翻译端点，openai 模式填 base"
            "（如 https://api.openai.com/v1）或完整 /chat/completions 地址"
        ),
    )
    translation_api_key: str = Field(
        default="",
        description="翻译 API Key（openai 模式的 Bearer Token）；builtin 模式可留空",
    )
    translation_model: str = Field(
        default="gpt-4o-mini",
        description="翻译模型名（openai 模式），如 gpt-4o-mini、deepseek-chat 等",
    )
    translation_stream: bool = Field(
        default=False,
        description=(
            "OpenAI 兼容翻译使用流式响应；免费/慢速模型建议关闭，"
            "流式更容易触发超时和异常"
        ),
    )
    translation_max_tokens: int = Field(
        default=1200,
        description=(
            "翻译输出最大 token 数（0=不限制）；防止免费模型输出爆炸，"
            "16 条短语约需 800-1000，建议 1000-1500"
        ),
    )
    translation_timeout: int = Field(
        default=20,
        description=(
            "翻译请求超时（秒）；慢速模型或批量送译时输出更长，建议 60 以上"
            "避免批量被超时截断"
        ),
    )
    translation_target_lang: str = Field(
        default="zh-CN",
        description="翻译目标语言",
    )
    translation_retry_fallback_seconds: int = Field(
        default=180,
        description=(
            "翻译失败回退缓存时间（秒）；失败后短暂记录失败状态避免连续打爆接口，"
            "到期后重新尝试翻译"
        ),
    )
    translation_error_cooldown_seconds: int = Field(
        default=120,
        description=(
            "翻译接口错误冷却时间（秒）；OpenAI 兼容接口返回 429/5xx 后暂停翻译"
            "请求，避免拥塞时连续漏翻"
        ),
    )
    translation_min_interval_seconds: int = Field(
        default=0,
        description=(
            "翻译请求最小间隔（秒）；API 有每分钟 N 次配额时填 60/N（如 5 次/分钟"
            "填 12），从源头避免 429；0 为不限"
        ),
    )
    drop_untranslated_content: bool = Field(
        default=True,
        description=(
            "剔除未翻译英文内容：翻译失败或译文等于原文时不再发送明显英文正文；"
            "翻译接口限流（429/冷却）期间例外，保留英文原文稍后自动补翻"
        ),
    )
    rotation_dispatches: int = Field(
        default=300,
        description="快讯翻译轮转间隔（秒）",
    )
    rotation_orders: int = Field(
        default=600,
        description="最高命令翻译轮转间隔（秒）",
    )
    rotation_steam: int = Field(
        default=900,
        description="Steam 更新翻译轮转间隔（秒）",
    )

    # ---- Steam ----
    steam_max_content_length: int = Field(
        default=2000,
        description="Steam 更新内容最大长度",
    )
    steam_balancing_limit: int = Field(
        default=800,
        description="Steam 平衡性调整节最大长度",
    )
    steam_fixes_limit: int = Field(
        default=600,
        description="Steam 修复节最大长度",
    )
    steam_issues_limit: int = Field(
        default=300,
        description="Steam 已知问题节最大长度",
    )
    steam_max_sections: int = Field(
        default=3,
        description="Steam 更新最多展示节数",
    )
    steam_appid: int = Field(
        default=553850,
        description="Steam 游戏 App ID",
    )
    steam_news_count: int = Field(
        default=10,
        description="Steam 新闻缓存数量；官方公告接口一次获取的数量，建议 5-20",
    )
    steam_image_enabled: bool = Field(
        default=True,
        description="启用 Steam 新闻主图",
    )

    # ---- Wiki ----
    enable_wiki: bool = Field(
        default=True,
        description="启用 Helldivers Wiki 查询（/wiki）",
    )
    wiki_base: str = Field(
        default="https://helldivers.wiki.gg",
        description="Wiki 站点根地址",
    )
    wiki_api_path: str = Field(
        default="/api.php",
        description="MediaWiki API 路径",
    )
    wiki_search_limit: int = Field(
        default=5,
        description="Wiki 搜索候选数量；建议 3-8",
    )
    wiki_extract_chars: int = Field(
        default=900,
        description="Wiki 摘要最大字符数",
    )
    wiki_full_extract_chars: int = Field(
        default=3000,
        description="Wiki 全文模式最大字符数（/wiki 关键词 -f）；建议 2000-4000",
    )
    wiki_prefer_hd2: bool = Field(
        default=True,
        description="优先 Helldivers 2 词条（过滤 Helldivers 1: 前缀）",
    )
    translate_wiki: bool = Field(
        default=True,
        description=(
            "自动翻译 Wiki 摘要为中文（依赖 enable_translation）；"
            "启用 drop_untranslated_content 时失败不发送英文摘要"
        ),
    )
    wiki_cache_ttl: int = Field(
        default=21600,
        description="Wiki 词条缓存有效期（秒）；默认 6 小时",
    )
    wiki_search_cache_ttl: int = Field(
        default=1800,
        description="Wiki 搜索结果缓存有效期（秒）",
    )

    # ---- 军需簿 ----
    enable_arsenal: bool = Field(
        default=True,
        description=(
            "启用军需簿查询（/hd2data）；数据来自开源 HD2Tool 项目，含官方中文译名"
            "和玩家俗称，首次使用自动下载约 500KB 数据，每 24 小时检查更新"
        ),
    )

    # ---- 地图 ----
    enable_map: bool = Field(
        default=True,
        description="启用 /map 战争地图（图片）",
    )
    map_cache_ttl: int = Field(
        default=600,
        description="地图图片缓存有效期（秒）",
    )
    map_label_top_n: int = Field(
        default=15,
        description="地图上标注的活跃星球数量",
    )
    map_visual_mode: str = Field(
        default="uploaded_reference",
        description=(
            "地图视觉模式：uploaded_reference=使用上传的 map.png 作为圆形银河基底；"
            "derived=程序化地图"
        ),
    )
    asset_manifest_path: str = Field(
        default="",
        description="本地图片素材 manifest 路径（留空使用插件内置素材）",
    )

    # ---- 个人任务 ----
    personal_order_api_url: str = Field(
        default="https://cdn.helldiverscompanion.com/live/personalOrders/current.json",
        description=(
            "个人任务 JSON 数据源 URL（默认 Companion 社区 CDN，插件会拒绝超过 "
            "3 天的旧快照）；未发现 Arrowhead 官方公开 Personal Order API"
        ),
    )
    allow_private_personal_order_url: bool = Field(
        default=False,
        description=(
            "允许个人指令数据源访问私有网络；仅在使用可信的局域网或本机 JSON 服务"
            "时开启，开启后允许 HTTP 和私有 IP"
        ),
    )

    # ---- 战役趋势 ----
    campaign_history_hours: float = Field(
        default=2.0,
        description="战役趋势历史保留小时数（1-3）；用于 Warfront 与 Dashboard 的近期净推进速率",
    )
    campaign_rate_window_minutes: float = Field(
        default=20.0,
        description="战役趋势采样窗口（分钟，10-30）；用于计算 Recent Liberation Rate",
    )

    # ---- 远程图片 ----
    remote_image_max_bytes: int = Field(
        default=8388608,
        description="远程新闻图片最大字节数（仅允许 Steam 官方 CDN，默认 8 MiB）",
    )
    remote_image_max_pixels: int = Field(
        default=16000000,
        description="远程新闻图片最大解码像素",
    )
    image_cache_max_mb: int = Field(
        default=150,
        description="远程图片缓存上限（MiB）",
    )

    # ---- Dashboard ----
    dashboard_low_impact_threshold: int = Field(
        default=800,
        description=(
            "Dashboard 低影响星球玩家数阈值；低于该在线人数的进攻星球会折叠为"
            "「低影响星球」汇总"
        ),
    )


def _derive_label(description: str) -> str:
    """从字段描述派生简短中文标签（在最早出现的分隔符处截断）。"""
    text = (description or "").strip()
    cut = len(text)
    for ch in "；：（，。(":
        idx = text.find(ch)
        if 0 < idx < cut:
            cut = idx
    return text[:cut].strip() or text


_LABEL_OVERRIDES: dict[str, str] = {
    "api_base": "主 API 地址",
    "companion_screenshot_wait_ms": "页面加载后额外等待(ms)",
    "companion_page_load_timeout": "页面数据加载等待(s)",
    "companion_translation_timeout": "前台翻译等待(s)",
    "companion_translation_batch_timeout": "单批翻译等待(s)",
    "companion_screenshot_cache_ttl": "截图缓存时长(s)",
    "companion_screenshot_max_bytes": "单张截图最大字节",
    "companion_screenshot_max_pixels": "单张截图最大像素",
    "companion_show_inactive": "显示低活跃度战役",
    "companion_warmup_interval": "预热间隔(s)",
    "companion_warmup_kinds": "预热页面",
    "companion_news_push_enabled": "启用新闻推送",
    "enable_companion_screenshots": "启用 Companion 截图",
    "companion_render_backend": "Companion 截图后端",
    "enable_bilibili_galaxy_news": "启用银河快报推送",
    "bilibili_cookie": "B站 Cookie",
    "bilibili_poll_interval": "B站轮询间隔(s)",
    "bilibili_image_max_bytes": "B站单图最大字节",
    "bilibili_image_max_pixels": "长图最大解码像素",
    "enable_background_refresh": "启用后台定时同步",
    "cache_update_interval": "缓存刷新间隔(s)",
    "request_delay": "批量请求间隔(s)",
    "min_request_interval": "API 最小请求间隔(s)",
    "translation_stream": "翻译使用流式响应",
    "translation_max_tokens": "翻译最大 token",
    "translation_min_interval_seconds": "翻译最小间隔(s)",
    "translation_error_cooldown_seconds": "翻译错误冷却(s)",
    "translation_retry_fallback_seconds": "翻译回退缓存(s)",
    "drop_untranslated_content": "剔除未翻译英文",
    "steam_balancing_limit": "平衡性调整节长度",
    "steam_fixes_limit": "修复节长度",
    "steam_issues_limit": "已知问题节长度",
    "steam_appid": "Steam App ID",
    "wiki_full_extract_chars": "Wiki 全文最大字符",
    "translate_wiki": "翻译 Wiki 摘要",
    "map_visual_mode": "地图视觉模式",
    "personal_order_api_url": "个人任务数据源 URL",
    "allow_private_personal_order_url": "允许访问私有网络",
    "campaign_history_hours": "趋势历史保留(小时)",
    "campaign_rate_window_minutes": "趋势采样窗口(分钟)",
    "dashboard_low_impact_threshold": "低影响星球阈值",
    "plugin": "保留节(勿改)",
}

# 为每个字段注入中文 label（WebUI 表单以 label 为显示名，字段名保持不变）
for _cls in (_PluginSection, HD2Config):
    for _name, _field in _cls.model_fields.items():
        _extra = dict(_field.json_schema_extra or {})
        _extra["label"] = _LABEL_OVERRIDES.get(_name) or _derive_label(
            str(_field.description or "")
        )
        _field.json_schema_extra = _extra
