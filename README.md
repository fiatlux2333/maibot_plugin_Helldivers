# maibot_plugin_Helldivers · 绝地潜兵2情报助手

[English](README_EN.md) | 简体中文

> MaiBot 上的 Helldivers 2 银河战争图片情报插件。

提供银河战争 Dashboard、实时统计、主要/个人任务、战争地图、战线排行、全球事件、
Steam 公告、Helldivers Wiki、军需簿（武器·护甲·敌人）、Companion 网页截图翻译、
B站银河快报订阅推送与数据源自诊断。内置双层缓存、限流重试、译名词表预替换与
AI 翻译。

## 功能

- **银河战争图片卡片**：Dashboard 总览、详细统计、主要任务、个人任务、战争地图、
  全球事件、阵营战线 Top 10、星球详情
- **Companion 截图翻译**：原网页截图（新闻/首页/DSS/星球）+ 中文翻译，后台预热，
  新闻更新自动推送到订阅群
- **外部资讯**：Steam 更新公告、Helldivers Wiki 查询（中文自动译名）、军需簿装备/敌人数据库
- **B站银河快报**：监听指定 UP 主动态，关键字命中后自动推送到订阅群
- **数据源自诊断**：`/hd2ping` 查看各数据源健康、缓存年龄与关键配置一览

## 指令一览

| 指令 | 说明 |
|---|---|
| `/dashboard`（总览 / 战况总览） | 银河战争总览（实时数据，图片） |
| `/hd2stats` | 银河战争详细统计（实时数据，图片） |
| `/order`（major_order / 最高命令） | 当前最高指令任务卡 |
| `/po`（personal_order / 个人任务） | 当前个人指令 |
| `/map`（地图） | 银河战争地图（阵营领土） |
| `/warfront <阵营>`（战线） | 阵营战线 Top 10（阵营：Terminids / Automaton / Illuminate） |
| `/global_events`（全球事件 / events） | 全球事件 |
| `/steam` | Steam 更新公告（图片优先，文本兜底） |
| `/wiki <关键词> [-f]`（维基 / 百科） | Wiki 查询，`-f` 查看全文 |
| `/hd2data <名称>`（军需簿 / 装备 / 武器库） | 军需簿查询，支持俗称（电喷、泰坦…） |
| `/hd2ping`（诊断 / 自检） | 数据源健康 / 缓存年龄自诊断 |
| `/hd2news` | Companion 最新新闻（截图+翻译） |
| `/hd2news订阅` / `/hd2news退订` | 本群新闻更新自动推送开关 |
| `/companion`（首页） | Companion 首页截图 |
| `/dss`（空间站 / 民主空间站） | 民主空间站面板 + 中文情报 |
| `/planet <名称/编号/链接>`（星球） | 星球详情截图（支持中文名与链接） |
| `/hd2refresh`（刷新缓存） | 强制刷新 Companion 截图缓存 |
| `/银河快报`（galaxy_news） | 立即获取最新一期 B站银河快报 |
| `/银河快报订阅` / `/银河快报退订` | 本群银河快报推送开关 |
| `/hd2`、`/hd2help` | 简短帮助 / 全部指令说明 |

所有指令同时接受 `/` 前缀与裸命令词（如 `总览`、`银河快报`），大小写不敏感。

## 安装

1. 将本目录整体复制到 MaiBot 的 `plugins/` 目录下。
2. 启动 MaiBot（或重载插件）。`_manifest.json` 中声明的 Python 依赖
   （aiohttp、Pillow）会由依赖管线自动安装；也可手动执行
   `pip install -r requirements.txt`。
3. Runner 首次加载时校验并合并 `config.toml`。仓库附带的
   `config.toml` 自带**中文注释**与默认值（Runner 以"补齐缺失字段"
   方式合并，注释会保留）；也可在 MaiBot WebUI 中修改。

### 可选：Companion 网页截图

`/hd2news`、`/companion`、`/dss`、`/planet` 需要 Playwright + Chromium：

```bash
pip install "playwright>=1.50.0"
python -m playwright install --with-deps chromium
```

未安装时这些指令会优雅降级并提示；其余指令不受影响。

**系统依赖库**：Playwright 的 Chromium 需要系统依赖库，缺失时截图会报
`Host system is missing dependencies` 或直接超时。`--with-deps` 会自动通过
apt 安装（Debian/Ubuntu）。

**中文字体**：必须安装 CJK 字体（Debian/Ubuntu：`apt-get install fonts-noto-cjk`）。
字体缺失**不会报错**，但 Pillow 渲染的图片卡片和 Companion 截图里的中文会
显示为方框（□）。插件按 `NotoSansCJK` → `wqy-zenhei` → `DejaVu` 顺序查找字体。

**国内服务器下载 Chromium 缓慢或失败**时，可在网络正常的机器下载对应版本的
`chrome-headless-shell-linux64.zip`（插件以 headless 模式启动，无需完整
Chrome），解压到 `~/.cache/ms-playwright/chromium_headless_shell-<build>/` 下
并 `chmod +x`；版本号以 `python -m playwright install --dry-run chromium`
或报错信息中的路径为准。

## 配置

仓库附带的 `config.toml` 已带**中文注释**与默认值（88 项，含 Runner 保留节），
MaiBot WebUI 的设置表单同样以中文展示；保存后插件自动按新配置重建组件（约 3 秒防抖），无需重载。关键字段：

| 配置 | 说明 |
|---|---|
| `api_contact` | 建议填写真实邮箱，遵守 Helldivers 社区 API 礼仪 |
| `war_id` | 当前战争 ID（默认 801，赛季变更时修改） |
| `proxy_url` | HTTP 代理（可选） |
| `enable_companion_screenshots` | Companion 截图总开关（默认开） |
| `companion_render_backend` | playwright（推荐）/ local / browserless |
| `enable_bilibili_galaxy_news` | B站银河快报推送总开关（默认关） |
| `bilibili_cookie` | B站 Cookie，必须包含 SESSDATA；勿提交到仓库 |
| `enable_translation` | AI 翻译开关；`translation_*` 系列配置详见 config.toml 注释 |

完整字段与说明见 [`hd2/config_schema.py`](hd2/config_schema.py)（与 WebUI 展示一致）。

## 注意事项

- **API 频率限制**：社区 API 有 429 限流，插件已内置全局限流与有限次重试；
  `cache_update_interval` 建议保持 120–300 秒。
- **翻译模型**：免费模型建议关闭流式（`translation_stream=false`）并适当调高
  `translation_timeout`；Companion 截图翻译依赖后台预热。
- **Companion 截图**：需 Playwright + Chromium；截图体积超 IPC 帧上限时
  插件自动降质重编码为 JPEG 发送。
- **银河快报**：B站后台监听必填 `bilibili_cookie`（含 SESSDATA），轮询间隔
  建议 ≥300 秒以降低风控概率；首次启动只建立动态基线，不补发旧内容。
- **配置热应用**：WebUI 保存配置后插件自动重建客户端、监听与预热组件（约 3 秒防抖），订阅名单持久化不受影响；如需整体重载可发送 `/pm plugin reload github.fiatlux2333.hd2-helper`。

## 数据源

- [Helldivers 2 Community API](https://api.helldivers2.dev) — 银河战争数据
- [Steam News API](https://store.steampowered.com/news/?appids=553850) — Steam 更新公告
- [Helldivers Wiki](https://helldivers.wiki.gg) — Wiki 词条
- [Helldivers Companion](https://helldiverscompanion.com) — 网页截图与个人任务
- 银河快报 B站空间 — 快报动态

> 趋势速度、预计完成时间和派系战线为插件估算结果，不代表官方结论。

## 参考与致谢

- [astrbot_plugin_Helldivers](https://github.com/fiatlux2333/astrbot_plugin_Helldivers) — 指令设计与数据层参考
- [xiaoyueyoqwq/hd2_qqbot](https://github.com/xiaoyueyoqwq/hd2_qqbot) — 早期实现与指令设计参考
- [Stonemercy/Galactic-Wide-Web](https://github.com/Stonemercy/Galactic-Wide-Web) — 战况面板参考
- Helldivers Companion — 数据与视觉参考
- [Helldivers 2 Community API](https://api.helldivers2.dev) — 银河战争数据
- [MaiBot](https://github.com/Mai-with-u/MaiBot) / [maibot-plugin-sdk](https://github.com/Mai-with-u/maibot-plugin-sdk) — 机器人框架与插件 SDK

## 免责声明

本项目为非官方社区作品，与 Arrowhead Game Studios、Sony、PlayStation 无任何隶属或授权关系。
“HELLDIVERS” 等名称属于各自权利人，仅作兼容说明必要引用。使用本插件需遵守各数据源的使用条款。

本项目使用 [MIT License](LICENSE) 授权。

为了超级地球，为了管理式民主！🌍
