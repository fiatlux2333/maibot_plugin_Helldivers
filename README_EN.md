# maibot_plugin_Helldivers · Helldivers 2 Intel Assistant

English | [简体中文](README.md)

> A Helldivers 2 galactic-war image-intelligence plugin for MaiBot.

Provides the galactic-war Dashboard, real-time statistics, major/personal
orders, the war map, warfront rankings, global events, Steam announcements,
the Helldivers Wiki, the arsenal database (weapons · armor · enemies),
Companion webpage screenshots with translation, Bilibili "Galaxy News"
subscription push, and a data-source self-diagnostic. Includes two-layer
caching, rate-limited retries, glossary pre-substitution, and AI translation.

## Features

- **Galactic-war image cards**: Dashboard overview, detailed statistics,
  major order, personal order, war map, global events, faction warfront Top 10,
  and planet details.
- **Companion screenshots with translation**: native webpage screenshots
  (news / homepage / DSS / planet) plus Chinese translation, with background
  warm-up and automatic push of news updates to subscribed groups.
- **External info**: Steam update announcements, Helldivers Wiki lookup
  (with automatic Chinese translation), and the arsenal equipment/enemy database.
- **Bilibili Galaxy News**: watches a configured uploader's dynamics and pushes
  keyword-matched posts to subscribed groups.
- **Data-source self-diagnostic**: `/hd2ping` reports data-source health,
  cache age, and key configuration at a glance.

## Commands

| Command | Description |
|---|---|
| `/dashboard` | Galactic-war overview (real-time data, image) |
| `/hd2stats` | Detailed galactic-war statistics (real-time data, image) |
| `/order` | Current major order card |
| `/po` | Current personal order |
| `/map` | Galactic-war map (faction territory) |
| `/warfront <faction>` | Faction warfront Top 10 (factions: Terminids / Automaton / Illuminate) |
| `/global_events` (`events`) | Global events |
| `/steam` | Steam update announcements (image first, text fallback) |
| `/wiki <keyword> [-f]` | Wiki lookup; `-f` for the full text |
| `/hd2data <name>` | Arsenal lookup; supports nicknames (e.g., 电喷, 泰坦) |
| `/hd2ping` | Data-source health / cache-age self-diagnostic |
| `/hd2news` | Companion latest news (screenshot + translation) |
| `/hd2news subscribe` / `/hd2news unsubscribe` | Toggle automatic news-update push for this group |
| `/companion` | Companion homepage screenshot |
| `/dss` | Democratic Space Station panel + Chinese intel |
| `/planet <name/number/link>` | Planet detail screenshot (supports Chinese names and links) |
| `/hd2refresh` | Force-refresh Companion screenshot cache |
| `/银河快报` (galaxy_news) | Fetch the latest Bilibili Galaxy News issue immediately |
| `/银河快报 subscribe` / `/银河快报 unsubscribe` | Toggle Galaxy News push for this group |
| `/hd2`, `/hd2help` | Short help / full command list |

All commands accept both a `/` prefix and the bare command word (e.g. `总览`,
`银河快报`), case-insensitive.

## Installation

1. Copy this directory as a whole into MaiBot's `plugins/` directory.
2. Start MaiBot (or reload the plugin). The Python dependencies declared in
   `_manifest.json` (aiohttp, Pillow) are installed automatically by the
   dependency pipeline; you can also run `pip install -r requirements.txt`
   manually.
3. On first load the Runner generates `config.toml` in the plugin directory;
   edit it via the MaiBot WebUI.

### Optional: Companion webpage screenshots

`/hd2news`, `/companion`, `/dss`, and `/planet` require Playwright + Chromium:

```bash
pip install playwright>=1.50.0
python -m playwright install chromium
```

Without it these commands degrade gracefully with a hint; other commands are
unaffected.

## Configuration

On first load the Runner generates `config.toml` from the config model and
renders a form in the WebUI; changes take effect after reloading the plugin.
There are 87 config fields in total. Key fields:

| Field | Description |
|---|---|
| `api_contact` | Recommended: a real email, to follow Helldivers community API etiquette |
| `war_id` | Current war ID (default 801; change on season rotation) |
| `proxy_url` | HTTP proxy (optional) |
| `enable_companion_screenshots` | Companion screenshot master switch (on by default) |
| `companion_render_backend` | playwright (recommended) / local / browserless |
| `enable_bilibili_galaxy_news` | Bilibili Galaxy News push master switch (off by default) |
| `bilibili_cookie` | Bilibili cookie; must contain SESSDATA; do not commit to the repo |
| `enable_translation` | AI translation switch; see `translation_*` fields in config.toml |

Full field list and descriptions: [`hd2/config_schema.py`](hd2/config_schema.py)
(consistent with the WebUI).

## Notes

- **API rate limits**: the community API returns 429; the plugin includes global
  rate limiting and bounded retries. Keep `cache_update_interval` at 120–300s.
- **Translation model**: for free models, disable streaming
  (`translation_stream=false`) and raise `translation_timeout`. Companion
  screenshot translation relies on background warm-up.
- **Companion screenshots**: require Playwright + Chromium. Images exceeding the
  IPC frame budget are automatically re-encoded to JPEG before sending.
- **Galaxy News**: background monitoring requires `bilibili_cookie` (with
  SESSDATA); a polling interval of ≥300s is recommended to reduce risk-control
  triggers. The first start only builds a dynamic baseline and does not backfill
  old posts.
- **Hot reload**: configuration involving clients, monitors, and warm-up requires
  a plugin reload to take effect.

## Data Sources

- [Helldivers 2 Community API](https://api.helldivers2.dev) — galactic-war data
- [Steam News API](https://store.steampowered.com/news/?appids=553850) — Steam update announcements
- [Helldivers Wiki](https://helldivers.wiki.gg) — wiki articles
- [Helldivers Companion](https://helldiverscompanion.com) — webpage screenshots and personal orders
- Bilibili Galaxy News space — Galaxy News dynamics

> Trend speed, estimated completion time, and faction warfronts are
> plugin-computed estimates and do not represent official conclusions.

## References & Credits

- [astrbot_plugin_Helldivers](https://github.com/fiatlux2333/astrbot_plugin_Helldivers) — command-design and data-layer reference
- [xiaoyueyoqwq/hd2_qqbot](https://github.com/xiaoyueyoqwq/hd2_qqbot) — early implementation and command-design reference
- [Stonemercy/Galactic-Wide-Web](https://github.com/Stonemercy/Galactic-Wide-Web) — war-panel reference
- Helldivers Companion — data and visual reference
- [Helldivers 2 Community API](https://api.helldivers2.dev) — galactic-war data
- [MaiBot](https://github.com/Mai-with-u/MaiBot) / [maibot-plugin-sdk](https://github.com/Mai-with-u/maibot-plugin-sdk) — bot framework and plugin SDK

## Disclaimer

This is an unofficial community project with no affiliation or authorization
from Arrowhead Game Studios, Sony, or PlayStation. "HELLDIVERS" and other names
belong to their respective rights holders and are referenced only as necessary
for compatibility. Use of this plugin must comply with the terms of each data
source.

This project is licensed under the [MIT License](LICENSE).

For Super Earth, for managed democracy! 🌍
