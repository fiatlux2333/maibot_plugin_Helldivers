"""模拟 MaiBot Runner 的 plugin_loader 加载本插件并断言组件注册。"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_DIR.parent))  # 与 Runner 一致


def load_plugin():
    # 复刻 src/plugin_runtime/runner/plugin_loader.py 的加载方式
    module_name = "_maibot_plugin_hd2_smoke"
    spec = importlib.util.spec_from_file_location(
        module_name,
        str(PLUGIN_DIR / "plugin.py"),
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module, module.create_plugin()


def main() -> int:
    manifest = json.loads((PLUGIN_DIR / "_manifest.json").read_text("utf-8"))
    assert manifest["manifest_version"] == 2, "manifest_version 应为 2"
    assert re.match(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$", manifest["id"]), "id 格式非法"
    assert re.match(r"^\d+\.\d+\.\d+$", manifest["version"]), "version 格式非法"

    module, instance = load_plugin()
    print(f"[OK] create_plugin -> {type(instance).__name__}")

    components = instance.get_components()
    commands = [c for c in components if c.get("type") == "COMMAND"]
    others = [c for c in components if c.get("type") != "COMMAND"]
    print(f"[OK] 组件总数 {len(components)}，其中 Command {len(commands)} 个")
    assert len(commands) == 23, f"应为 23 条命令，实际 {len(commands)}"
    assert not others, f"存在非 Command 组件: {others}"

    names = [c["name"] for c in commands]
    assert len(names) == len(set(names)), f"命令名重复: {names}"
    print("[OK] 命令名唯一:", ", ".join(sorted(names)))

    # ---- 模拟消息匹配测试 ----
    samples_ok = [
        "/hd2", "hd2", "HELLDIVERS", "/hd2help", "/hd2stats", "总览",
        "/dashboard", "战况总览", "/order", "最高命令", "major_order", "/po",
        "个人任务", "/map", "地图", "/warfront Terminids", "战线 机器人",
        "/global_events", "全球事件", "events", "/steam", "/wiki 磁轨炮",
        "wiki 心得 -f", "维基 泰坦", "/hd2data 电喷", "军需簿 泰坦",
        "/hd2ping", "诊断", "/hd2news", "hd2news订阅", "news_subscribe",
        "/hd2news退订", "/companion", "首页", "/dss", "民主空间站",
        "/planet 马里卡特", "星球 7", "/hd2refresh", "刷新缓存",
        "银河快报", "银河快报推送", "银河快报订阅", "银河快报退订",
        "/galaxy_news",
    ]
    samples_no = [
        "hd2statsx", "hd", "po2", "orders", "mapping", "steak", "wiki2",
        "银河快报推", "首页x", "dsss", "你好", "银河快报订阅了",
        "/hd2news订阅x", "随机聊天消息",
    ]
    compiled = [
        (c["name"], re.compile(c["metadata"]["command_pattern"])) for c in commands
    ]
    for text in samples_ok:
        hit = [name for name, pat in compiled if pat.match(text)]
        assert hit, f"应命中但未命中: {text!r}"
        assert len(hit) == 1, f"多条命令同时命中 {text!r}: {hit}"
    for text in samples_no:
        hit = [name for name, pat in compiled if pat.match(text)]
        assert not hit, f"不应命中却命中: {text!r} -> {hit}"
    print(f"[OK] 模式匹配 {len(samples_ok)} 正例 / {len(samples_no)} 反例全部符合")

    # ---- 配置模型 ----
    from maibot_sdk import PluginConfigBase  # noqa: F401 确认可导入
    model = instance.config_model()
    data = model.model_dump()
    assert len(data) == 88, f"配置项应为 87 业务项 + 1 保留节，实际 {len(data)}"
    assert data["plugin"]["config_version"] == "1", "保留 [plugin] 节缺失"
    assert data["war_id"] == 801 and data["api_base"] == "https://api.helldivers2.dev"
    print("[OK] 配置模型默认值可实例化：87 业务项 + [plugin] 保留节")

    # ---- 参数捕获组 ----
    warfront = next(c for c in commands if c["name"] == "warfront")
    m = re.compile(warfront["metadata"]["command_pattern"]).match("/warfront Terminids")
    assert m and m.group("faction") == "Terminids"
    wiki = next(c for c in commands if c["name"] == "wiki")
    m = re.compile(wiki["metadata"]["command_pattern"]).match("维基 泰坦 -f")
    assert m and m.group("query").strip() == "泰坦 -f"
    planet = next(c for c in commands if c["name"] == "planet")
    m = re.compile(planet["metadata"]["command_pattern"]).match("/planet 7")
    assert m and m.group("query").strip() == "7"
    print("[OK] warfront/wiki/planet 命名捕获组正确")

    # ---- 生命周期方法存在（Runner 契约）----
    for method in ("on_load", "on_unload", "on_config_update"):
        assert asyncio.iscoroutinefunction(getattr(instance, method)), method
    print("[OK] on_load / on_unload / on_config_update 均为 async 实现")

    print("\n=== 冒烟测试全部通过 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
