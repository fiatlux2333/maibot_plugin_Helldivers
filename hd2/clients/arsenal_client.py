"""HD2 数据库客户端：装备（HD2Tool）+ 敌人（helldivers.wiki.gg Cargo）。

装备数据来自 SalmonC/HD2Tool (MIT) 的 catalog.json + community-aliases.json，
含武器/战备/护甲/手榴弹的官方中文译名、战斗数值和玩家俚语别名。
敌人数据来自 helldivers.wiki.gg 的 Cargo 查询（CC BY-NC-SA，需注明来源）。
缓存到 data/arsenal/，每 24 小时检查更新；GitHub 直连失败时回退镜像。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Final

import aiohttp

from ..core.diagnostics import HEALTH

from ..compat import logger

RAW_URLS: Final[tuple[str, ...]] = (
    "https://raw.githubusercontent.com/SalmonC/HD2Tool/main/src/data/catalog.json",
    "https://gh-proxy.org/https://raw.githubusercontent.com/SalmonC/HD2Tool/main/src/data/catalog.json",
)
ALIAS_URLS: Final[tuple[str, ...]] = (
    "https://raw.githubusercontent.com/SalmonC/HD2Tool/main/"
    "src/data/community-aliases.json",
    "https://gh-proxy.org/https://raw.githubusercontent.com/SalmonC/HD2Tool/main/"
    "src/data/community-aliases.json",
)
ENEMIES_API: Final[str] = (
    "https://helldivers.wiki.gg/api.php?action=cargoquery&tables=Enemies"
    "&fields=title,health,faction,size,class,damage&limit=500&format=json"
)
REFRESH_INTERVAL: Final[int] = 24 * 3600
# 下载体积上限：目录数据约 500KB，敌人/部位数据远小于此；16MB 上限只防
# 异常镜像返回超大响应拖垮进程内存。
MAX_DOWNLOAD_BYTES: Final[int] = 16 * 1024 * 1024
# 敌人数据下载失败后的退避间隔（秒）：避免 wiki.gg 不可用时每次查询都重试
ENEMIES_RETRY_BACKOFF: Final[int] = 15 * 60

# HD1 阵营精确值——命中的敌人条目跳过（Cyborgs/Bugs/HD1 Illuminate 等纯 HD1 老阵营）
# 用精确匹配而非子串匹配，避免误杀 Cyborg Legion / Appropriators 等 HD2 新阵营
_HD1_FACTION_EXACT: Final[frozenset[str]] = frozenset(
    {"cyborgs", "bugs", "hd1 illuminate", "super earth federation"}
)

_FACTION_ZH: Final[dict[str, str]] = {
    "Terminids": "终结族",
    "Automatons": "机器人",
    "Illuminate": "光能者",
    "Jet Brigade": "喷气旅",
    "Incineration Corps": "焚烧军团",
    "Spore Burst Strain": "孢子爆发株",
    "Rupture Strain": "破裂株",
    "Predator Strain": "掠食者株",
    "Vote Snatchers": "窃票者",
    "Cyborg Legion": "生化军团",
    "Appropriators": "掠夺者",
}

# wiki.gg Cargo Enemies 表遗漏的 HD2 敌人，手动补全
_MANUAL_ENEMIES: Final[tuple[tuple[str, str, str], ...]] = (
    ("Illuminate Overship", "Illuminate", ""),
)


def enemy_name_zh(name_en: str) -> str:
    """用官方敌人词表把英文名转中文，未收录时原样返回。"""
    try:
        from ..core.glossary import ENEMY_NAMES

        zh = ENEMY_NAMES.get(name_en.strip().casefold())
        if zh:
            return zh
    except Exception:
        pass
    return name_en


def parse_health(raw: str) -> list[tuple[str, str]]:
    """解析 wiki 敌人血量字段。

    "4,000 (Hull Main) <br> 2,100 (Turret Main)" -> [("4,000", "Hull Main"), ...]
    纯数字 "6,500" -> [("6,500", "")]
    """
    text = re.sub(r"<br\s*/?>", "\n", raw or "")
    text = re.sub(r"<[^>]+>", "", text)
    parts: list[tuple[str, str]] = []
    for chunk in text.split("\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.match(
            r"([\d,\.]+)\s*(?:HP)?\s*(?:\+\s*[\d,\.]+\s*Constitution)?\s*(?:\(([^)]+)\))?",
            chunk,
        )
        if m:
            parts.append((m.group(1), (m.group(2) or "").strip()))
    return parts


# 敌人护甲类型中文映射
_ENEMY_CLASS_ZH: Final[dict[str, str]] = {
    "Light": "轻型",
    "Medium": "中型",
    "Heavy": "重型",
    "Superheavy": "超重型",
    "Miniboss": "首领",
    "Boss": "Boss",
}


# 敌人护甲等级中文映射（游戏内 0-10 护甲体系）
ARMOR_TIER_ZH: Final[dict[int, str]] = {
    0: "无甲",
    1: "超轻型",
    2: "轻型",
    3: "中型",
    4: "重型",
    5: "坦克 I",
    6: "坦克 II",
    7: "坦克 III",
    8: "坦克 IV",
    9: "坦克 V",
    10: "坦克 VI",
}


# 敌人部位名中文映射
_PART_NAME_ZH: Final[dict[str, str]] = {
    "Main": "主体",
    "Head": "头部",
    "Torso": "躯干",
    "Butt": "臀部",
    "Legs": "腿部",
    "Leg": "腿部",
    "Arms": "手臂",
    "Arm": "手臂",
    "Shoulders": "肩部",
    "Shoulder": "肩部",
    "Stomach": "腹部",
    "Belly": "腹部",
    "Pelvis": "骨盆",
    "Mouth": "口部",
    "Eye": "眼部",
    "Eyes": "眼部",
    "Weak Point": "弱点",
    "Tail": "尾部",
    "Wings": "翼部",
    "Sac": "囊袋",
    "Turret": "炮塔",
    "Hull": "车体",
    "Front": "前部",
    "Rear": "后部",
    "Side": "侧部",
    "Top": "顶部",
    "Bottom": "底部",
    "Inner": "内部",
    "Underside": "下腹",
    "Stratagem": "战备背包",
    "Cannon": "加农炮",
    "Fusion Gatling": "聚变机枪",
    "Chin Gun": "颚部机炮",
    "Mortar": "迫击炮",
    "Rocket Pods": "火箭巢",
    "Missile Pods": "导弹巢",
    "Gatling": "机枪",
    "Thruster": "推进器",
    "Eye Stem": "眼柄",
    "Pustules": "脓疱",
    "Legs (4)": "腿部",
    "Arms (2)": "手臂",
    "Legs (2)": "腿部",
    "Shoulders (2)": "肩部",
    "Abdomen": "腹部",
    "Thorax": "胸部",
    "Pilot": "驾驶员",
    "Weapon": "武器",
    "Glowing Orifice": "发光孔",
}


def armor_tier_label(value: int) -> str:
    """护甲等级数字转中文标签。"""
    return f"{value} {ARMOR_TIER_ZH.get(int(value), '未知')}"


def parse_anatomy_armor(wikitext: str) -> list[tuple[str, int]]:
    """从敌人页面的 wikitext 解析 {{Anatomy Row}} 部位护甲。

    返回 [(部位名, 护甲等级), ...]，如 [("Head", 1), ("Torso", 2)]。
    """
    parts: list[tuple[str, int]] = []
    for m in re.finditer(
        r"\{\{Anatomy Row(.*?)\}\}", wikitext or "", re.DOTALL
    ):
        block = m.group(1)
        name_m = re.search(r"\|\s*part_name\s*=\s*([^\n|]+)", block)
        av_m = re.search(r"\|\s*av\s*=\s*(\d+)", block)
        if not name_m or not av_m:
            continue
        name = name_m.group(1).strip()
        # 去掉 <br> 和括号备注
        name = re.sub(r"<br[^>]*>.*", "", name).strip()
        av = int(av_m.group(1))
        parts.append((name, av))
    return parts


def parse_damage(raw: str) -> list[tuple[str, str]]:
    """解析 wiki 敌人伤害字段，清洗维基标记。

    输入形如:
      <span class="DamageIcons">[[File:...]]</span>&nbsp;[[Damage#|60 Bile Spew +3/s Acid]]
    输出: [("60 Bile Spew +3/s Acid Burn (4s)", "酸"), ...]
    """
    text = raw or ""
    text = re.sub(r"\[\[File:[^\]]+\]\]", "", text)
    text = re.sub(r"\[\[[^|]*\|([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ")
    parts: list[tuple[str, str]] = []
    for chunk in re.split(r";\s*|\s{2,}", text):
        chunk = chunk.strip()
        if not chunk or len(chunk) < 2:
            continue
        dtype = ""
        for keyword, label in (
            ("Acid", "酸"),
            ("Ballistic", "弹道"),
            ("Explosion", "爆炸"),
            ("Melee", "近战"),
            ("Laser", "激光"),
            ("Fire", "火焰"),
            ("Gas", "毒气"),
            ("Arc", "电弧"),
            ("Energy", "能量"),
        ):
            if keyword.lower() in chunk.lower():
                dtype = label
                break
        parts.append((chunk[:60], dtype))
    return parts


def _edit_distance_le1(a: str, b: str) -> bool:
    """编辑距离是否 ≤1：改一字 / 多一字 / 少一字都算命中。

    用于中文错字容错：用户打错一个同音字（座/坐）、多打或少打
    一个字（无后坐力炮机 / 后坐力炮）仍能命中。
    """
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = sum(1 for x, y in zip(a, b) if x != y)
        return diff == 1
    # 长度差 1：双指针找插入/删除点
    if len(a) > len(b):
        a, b = b, a
    i = j = 0
    skipped = False
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = True
            j += 1
    return True


def normalize_query(text: str) -> str:
    """规范化查询/索引键：去标点 + 去空格 + 全角转半角 + 大小写折叠。

    让 "飞鹰500KG炸弹" 和 ""飞鹰"500KG炸弹"（含全角引号）都能匹配同一物品。
    """
    text = (text or "").strip()
    # 全角→半角（片假名/中文标点保留，只转 ASCII 范围的全角字符）
    text = text.translate(
        str.maketrans(
            {i: i - 0xFEE0 for i in range(0xFF01, 0xFF5F)}
        )
    )
    # 去掉所有标点符号和空白（保留字母/数字/中文/连字符）
    text = re.sub(r"[\s\u3000\u201c\u201d\u2018\u2019\u00ab\u00bb\"'`~!@#$%^&*()+=\[\]{}|\\/:;<>,.\-_]", "", text)
    return text.casefold()

PRODUCT_KIND_ZH: Final[dict[str, str]] = {
    "primary-weapon": "主武器",
    "secondary-weapon": "副武器",
    "support-weapon": "支援武器",
    "other-stratagem": "战备",
    "body-armor": "护甲",
    "grenade": "手榴弹",
}

FIELD_ZH: Final[dict[str, str]] = {
    "standardDamage": "伤害",
    "durableDamage": "耐久伤害",
    "dps": "秒伤",
    "demolitionForce": "拆除力",
    "stagger": "硬直",
    "push": "击退",
    "innerRadius": "内半径",
    "outerRadius": "外半径",
    "armorPenetration": "穿甲",
    "statusEffects": "状态效果",
}

COMPONENT_LABEL_ZH: Final[dict[str, str]] = {
    "Ballistic": "弹道",
    "Explosion": "爆炸",
    "Beam": "光束",
    "Melee": "近战",
    "Spray": "喷射",
    "Shrapnel": "破片",
    "Status": "状态",
}

HANDLING_ZH: Final[dict[str, str]] = {
    "magazine": "弹匣",
    "spareMagazines": "备用弹匣",
    "fireRate": "射速",
    "recoil": "后坐力",
    "firingModes": "射击模式",
    "reloadSeconds": "装填",
}

ACQUISITION_ZH: Final[dict[str, str]] = {
    "warbond": "战争债券",
    "requisition": "申请单",
    "superstore": "超级商店",
    "default": "初始解锁",
    "event": "活动",
    "poi": "地图探索",
    "edition": "版本特典",
    "unavailable": "暂不可获取",
}


class ArsenalClient:
    """catalog.json 的下载、缓存与多路名称匹配。"""

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        proxy_url: str = "",
        timeout: int = 30,
        user_agent: str = "maibot_plugin_helldivers",
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.proxy_url = proxy_url or None
        self.timeout_seconds = timeout
        self.user_agent = user_agent
        self._items: list[dict[str, Any]] = []
        self._enemies: list[dict[str, Any]] = []
        self._aliases: dict[str, list[str]] = {}
        self._index: dict[str, dict[str, Any]] = {}
        self._data_version: str = ""
        self._loaded_at: float = 0.0
        self._lock = asyncio.Lock()
        self._enemies_lock = asyncio.Lock()
        self._enemies_failed_at: float = 0.0

    @property
    def available(self) -> bool:
        return bool(self._items)

    @property
    def data_version(self) -> str:
        return self._data_version

    @property
    def item_count(self) -> int:
        return len(self._items)

    @property
    def enemy_count(self) -> int:
        return len(self._enemies)

    async def ensure_loaded(self, *, force: bool = False) -> bool:
        """加载缓存数据；超过刷新间隔或强制时重新下载。"""
        async with self._lock:
            if self._items and not force:
                if time.time() - self._loaded_at < REFRESH_INTERVAL:
                    return True
            catalog_path = self.cache_dir / "catalog.json"
            aliases_path = self.cache_dir / "aliases.json"
            stale = force or not catalog_path.is_file()
            if not stale and time.time() - catalog_path.stat().st_mtime > REFRESH_INTERVAL:
                stale = True
            if stale:
                ok = await self._download(catalog_path, aliases_path)
                if not ok and not catalog_path.is_file():
                    return False  # 下载失败且无本地缓存
            if not self._load_from(catalog_path, aliases_path):
                return False
            self._loaded_at = time.time()
            return True

    async def _download(
        self, catalog_path: Path, aliases_path: Path
    ) -> bool:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        try:
            async with aiohttp.ClientSession(
                headers={"User-Agent": self.user_agent},
                timeout=timeout,
                trust_env=False,
            ) as session:
                for urls, path in (
                    (RAW_URLS, catalog_path),
                    (ALIAS_URLS, aliases_path),
                ):
                    body = await self._fetch_any(session, urls)
                    if body is None:
                        HEALTH.record_fail("hd2tool", detail="镜像全部失败")
                        return False
                    tmp = path.with_suffix(".tmp")
                    tmp.write_bytes(body)
                    tmp.replace(path)
            HEALTH.record_ok("hd2tool", detail="catalog+aliases 下载成功")
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"[HD2] arsenal download failed: {exc}")
            HEALTH.record_fail("hd2tool", detail=str(exc))
            return False

    @staticmethod
    async def _read_capped(resp: aiohttp.ClientResponse) -> bytes:
        """读取响应体，超过 MAX_DOWNLOAD_BYTES 时截断报错，防异常镜像 OOM。"""
        length = resp.content_length
        if length is not None and length > MAX_DOWNLOAD_BYTES:
            raise ValueError(
                f"response too large: {length} > {MAX_DOWNLOAD_BYTES}"
            )
        chunks: list[bytes] = []
        received = 0
        async for chunk in resp.content.iter_chunked(256 * 1024):
            received += len(chunk)
            if received > MAX_DOWNLOAD_BYTES:
                raise ValueError(
                    f"response exceeded {MAX_DOWNLOAD_BYTES} bytes"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    async def _fetch_any(
        session: aiohttp.ClientSession, urls: tuple[str, ...]
    ) -> bytes | None:
        """依次尝试多个镜像 URL，返回首个成功的响应体。"""
        for url in urls:
            try:
                async with session.get(url, proxy=None) as resp:
                    if resp.status != 200:
                        logger.warning(
                            f"[HD2] arsenal download HTTP {resp.status}: {url}"
                        )
                        continue
                    return await ArsenalClient._read_capped(resp)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(f"[HD2] arsenal mirror failed ({url}): {exc}")
        return None

    def _load_from(self, catalog_path: Path, aliases_path: Path) -> bool:
        try:
            raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning(f"[HD2] arsenal catalog unreadable: {exc}")
            return False
        items = raw.get("items")
        if not isinstance(items, list) or not items:
            return False
        self._items = [i for i in items if isinstance(i, dict)]
        meta = raw.get("meta") or {}
        self._data_version = str(meta.get("dataVersion") or "")

        try:
            alias_raw = json.loads(aliases_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            alias_raw = {}
        self._aliases = {}
        for entry in (alias_raw.get("entries") or []) if isinstance(alias_raw, dict) else []:
            if isinstance(entry, dict) and entry.get("equipmentId"):
                self._aliases[str(entry["equipmentId"])] = [
                    str(a) for a in entry.get("aliases") or [] if a
                ]

        self._build_index()
        return True

    async def ensure_enemies(self) -> None:
        """加载敌人数据（wiki.gg Cargo）；失败静默——装备查询不受影响。

        下载失败后进入 15 分钟退避，避免 wiki.gg 不可用时每次查询都
        阻塞等待超时；并发调用由锁串行化，防止重复下载与 tmp 文件竞争。
        """
        async with self._enemies_lock:
            await self._ensure_enemies_locked()

    async def _ensure_enemies_locked(self) -> None:
        enemies_path = self.cache_dir / "enemies.json"
        # 判断是否需要重新下载：文件不存在 / TTL 过期 / 缓存版本旧（无 class/damage 字段）
        needs_refresh = not enemies_path.is_file()
        if not needs_refresh:
            age = time.time() - enemies_path.stat().st_mtime
            if age > REFRESH_INTERVAL:
                needs_refresh = True
            else:
                # 检查缓存是否包含 class/damage 字段（旧版 API 缓存没有）
                try:
                    cached = json.loads(enemies_path.read_text(encoding="utf-8"))
                    first = (
                        (cached.get("cargoquery") or [{}])[0].get("title", {})
                        if isinstance(cached, dict)
                        else {}
                    )
                    if "class" not in first or "damage" not in first:
                        needs_refresh = True
                except (OSError, ValueError, IndexError, TypeError):
                    needs_refresh = True
        if needs_refresh:
            # 失败退避：上次下载失败后 15 分钟内不再尝试
            if time.time() - self._enemies_failed_at < ENEMIES_RETRY_BACKOFF:
                logger.debug("[HD2] enemies download in failure backoff")
            else:
                timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
                try:
                    async with aiohttp.ClientSession(
                        headers={"User-Agent": self.user_agent},
                        timeout=timeout,
                        trust_env=False,
                    ) as session:
                        async with session.get(
                            ENEMIES_API, proxy=self.proxy_url
                        ) as resp:
                            if resp.status == 200:
                                body = await self._read_capped(resp)
                                tmp = enemies_path.with_suffix(".tmp")
                                tmp.write_bytes(body)
                                tmp.replace(enemies_path)
                                self._enemies_failed_at = 0.0
                                HEALTH.record_ok("wiki", detail="enemies cargoquery")
                            else:
                                self._enemies_failed_at = time.time()
                                logger.warning(
                                    f"[HD2] enemies download HTTP {resp.status}"
                                )
                                HEALTH.record_fail(
                                    "wiki", detail=f"enemies HTTP {resp.status}"
                                )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._enemies_failed_at = time.time()
                    logger.warning(f"[HD2] enemies download failed: {exc}")
                    HEALTH.record_fail("wiki", detail=f"enemies: {exc}")
        try:
            raw = json.loads(enemies_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self._enemies = []
        for row in (
            raw.get("cargoquery") or [] if isinstance(raw, dict) else []
        ):
            entry = row.get("title") if isinstance(row, dict) else None
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("title") or "").strip()
            faction = str(entry.get("faction") or "").strip()
            if not name or not faction:
                continue
            # 跳过 HD1 敌人（Cyborgs/Bugs/HD1 Illuminate 等老阵营）
            faction_key = faction.casefold()
            if faction_key in _HD1_FACTION_EXACT:
                continue
            self._enemies.append(
                {
                    "id": f"enemy:{name.casefold()}",
                    "productKind": "enemy",
                    "nameZh": enemy_name_zh(name),
                    "nameEn": name,
                    "faction": faction,
                    "factionZh": _FACTION_ZH.get(faction, faction),
                    "healthRaw": str(entry.get("health") or "").strip(),
                    "size": str(entry.get("size") or "").strip(),
                    "enemyClass": str(entry.get("class") or "").strip(),
                    "damageRaw": str(entry.get("damage") or "").strip(),
                    "wiki": {"url": f"https://helldivers.wiki.gg/wiki/{name.replace(' ', '_')}"},
                }
            )
        # wiki.gg Cargo 表遗漏的敌人条目手动补全
        cargo_names = {e["nameEn"] for e in self._enemies}
        for name, faction, health in _MANUAL_ENEMIES:
            if name not in cargo_names:
                self._enemies.append(
                    {
                        "id": f"enemy:{name.casefold()}",
                        "productKind": "enemy",
                        "nameZh": enemy_name_zh(name),
                        "nameEn": name,
                        "faction": faction,
                    "factionZh": _FACTION_ZH.get(faction, faction),
                    "healthRaw": health,
                    "size": "",
                    "enemyClass": "",
                    "damageRaw": "",
                    "wiki": {"url": f"https://helldivers.wiki.gg/wiki/{name.replace(' ', '_')}"},
                    }
                )
        # 敌人并入索引（走和装备相同的规范化逻辑）
        for e in self._enemies:
            for key in (e["nameZh"], e["nameEn"]):
                k = key.strip().casefold()
                if k and k not in self._index:
                    self._index[k] = e
                norm = normalize_query(k)
                if norm and norm not in self._index:
                    self._index[norm] = e

    def enemies_available(self) -> bool:
        return bool(getattr(self, "_enemies", None))

    async def fetch_enemy_armor(self, name_en: str) -> list[tuple[str, int]]:
        """按需拉取敌人页面的部位护甲（带缓存，TTL 与主数据一致）。

        返回 [(部位名, 护甲等级), ...]；页面无 Anatomy Row 或请求失败时为空。
        同一锁串行化并发查询，防止对同一敌人重复下载。
        """
        import urllib.parse

        cache_path = (
            self.cache_dir / f"armor_{hashlib.sha1(name_en.encode()).hexdigest()[:16]}.json"
        )
        async with self._enemies_lock:
            if cache_path.is_file() and (
                time.time() - cache_path.stat().st_mtime < REFRESH_INTERVAL
            ):
                try:
                    cached = json.loads(cache_path.read_text(encoding="utf-8"))
                    if isinstance(cached, list):
                        return [(str(p), int(a)) for p, a in cached]
                except (OSError, ValueError, TypeError):
                    pass
            api = (
                f"https://helldivers.wiki.gg/api.php?action=parse&page="
                f"{urllib.parse.quote(name_en, safe='')}&prop=wikitext&format=json"
            )
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            wikitext = ""
            try:
                async with aiohttp.ClientSession(
                    headers={"User-Agent": self.user_agent},
                    timeout=timeout,
                    trust_env=False,
                ) as session:
                    async with session.get(api, proxy=self.proxy_url) as resp:
                        if resp.status == 200:
                            data = json.loads(
                                await self._read_capped(resp)
                            )
                            wikitext = str(
                                (
                                    (data.get("parse") or {}).get("wikitext")
                                    or {}
                                ).get("*", "")
                                if isinstance(data, dict)
                                else ""
                            )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    f"[HD2] enemy armor fetch failed ({name_en}): {exc}"
                )
                return []
            parts = parse_anatomy_armor(wikitext)
            if parts:
                try:
                    tmp = cache_path.with_suffix(".tmp")
                    tmp.write_text(
                        json.dumps(parts, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    tmp.replace(cache_path)
                except OSError:
                    pass
            return parts

    def _build_index(self) -> None:
        index: dict[str, dict[str, Any]] = {}

        def put(key: str, item: dict[str, Any]) -> None:
            key = (key or "").strip().casefold()
            if key and key not in index:
                index[key] = item
            # 规范化键（去标点/空格 + 全半角统一）：用户漏打引号也能命中
            norm = normalize_query(key)
            if norm and norm not in index:
                index[norm] = item

        for item in self._items:
            put(str(item.get("nameZh") or ""), item)
            put(str(item.get("nameEn") or ""), item)
            put(str(item.get("model") or ""), item)
            put(str(item.get("id") or ""), item)
            for name in item.get("alternateNames") or []:
                put(str(name), item)
            for alias in self._aliases.get(str(item.get("id") or ""), []):
                put(alias, item)
        self._index = index

    def aliases_for(self, item_id: str) -> list[str]:
        """返回某物品的玩家俗称列表（无则空）。"""
        return self._aliases.get(str(item_id or ""), [])

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """精确 → 规范化精确 → 前缀 → 规范化子串的多路匹配，去重保序。"""
        query = (query or "").strip()
        if not query:
            return []
        q = query.casefold()
        exact = self._index.get(q)
        if exact is not None:
            return [exact]
        # 规范化精确匹配（去标点/空格，如 "飞鹰500KG炸弹" → "飞鹰500kg炸弹"）
        qn = normalize_query(q)
        if qn and qn != q:
            hit = self._index.get(qn)
            if hit is not None:
                return [hit]
        # 型号前缀提取：从查询中提取 "字母+数字" 前缀（如 "m102gunnerfrv" → "m102"）
        # 让 "M-102 Gunner FRV" 能命中 "M-102 Fast Recon Vehicle"
        prefix_match = re.match(r"^([a-z]+[0-9]+)", qn or "")
        qp = prefix_match.group(1) if prefix_match and len(prefix_match.group(1)) >= 3 else None
        seen: set[int] = set()
        results: list[dict[str, Any]] = []
        for key, item in self._index.items():
            ident = id(item)
            if ident in seen:
                continue
            if key.startswith(q) or (qn and key.startswith(qn)) or (qp and key.startswith(qp) and len(qp) >= 3):
                seen.add(ident)
                results.append(item)
        for key, item in self._index.items():
            ident = id(item)
            if ident in seen:
                continue
            if q in key or (qn and qn in key) or (qp and qp in key and len(qp) >= 4):
                seen.add(ident)
                results.append(item)
            if len(results) >= limit:
                break
        # 中文错字容错：前面全部未命中时，做编辑距离 ≤1 的模糊匹配
        # （错一字如"无后座力炮"、多一字如"无后坐力炮机"、少一字如"后坐力炮"）。
        # 只对较长的中文查询生效，避免短查询产生大量误匹配。
        if not results and len(q) >= 4 and re.search(r"[\u4e00-\u9fff]", q):
            fuzzy_seen: set[int] = set()
            for key, item in self._index.items():
                # 只和长度相近的中文键比较；同一物品的多个键都命中时只取一次
                ident = id(item)
                if ident in fuzzy_seen:
                    continue
                if abs(len(key) - len(q)) <= 1 and _edit_distance_le1(q, key):
                    fuzzy_seen.add(ident)
                    results.append(item)
                    if len(results) >= limit:
                        break
        return results[:limit]


__all__ = [
    "ArsenalClient",
    "ACQUISITION_ZH",
    "ARMOR_TIER_ZH",
    "COMPONENT_LABEL_ZH",
    "FIELD_ZH",
    "HANDLING_ZH",
    "PRODUCT_KIND_ZH",
    "armor_tier_label",
    "enemy_name_zh",
    "normalize_query",
    "parse_anatomy_armor",
    "parse_damage",
    "parse_health",
]
