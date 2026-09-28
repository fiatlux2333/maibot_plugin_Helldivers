"""完整 on_load / on_unload 集成测试：验证全部配置属性引用与组件构造。"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path("/tmp/hd2_onload_data")


class FakeSend:
    async def text(self, content, stream_id, **kw):
        return True

    async def image(self, data, stream_id, **kw):
        return True


class FakeCtx:
    def __init__(self) -> None:
        self.send = FakeSend()
        self.paths = type("P", (), {"data_dir": str(DATA_DIR)})()


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "_maibot_plugin_hd2_onload",
        str(PLUGIN_DIR / "plugin.py"),
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_maibot_plugin_hd2_onload"] = module
    spec.loader.exec_module(module)
    return module.create_plugin()


async def main() -> int:
    inst = load_plugin()
    inst._ctx = FakeCtx()
    # 关闭会拉起浏览器/网络轮询的开关，其余走默认配置以覆盖全部属性引用
    raw_config = inst.get_default_config()  # Runner 首次生成 config.toml 的同款数据
    raw_config["enable_companion_screenshots"] = False
    raw_config["enable_background_refresh"] = False
    inst.set_plugin_config(raw_config)

    await inst.on_load()
    assert inst.service is not None, "on_load 后 service 应已构造"
    assert inst.companion_news_monitor is not None
    assert inst.bilibili_monitor is not None
    assert inst.companion_enabled is False
    print("[OK] on_load 完整构造：service / monitors / 客户端与渲染器全部就绪")

    svc = inst.service
    assert svc.client is not None and svc.client.war_id == 801
    assert svc.arsenal_client is not None
    assert svc.enable_translation is True
    print("[OK] 默认配置生效：war_id=801，军需簿与翻译已启用")

    # Runner 生成 config.toml 用的默认配置导出
    defaults = inst.get_default_config()
    assert len(defaults) == 88, f"默认配置应 87 业务项 + 1 保留节，实际 {len(defaults)}"
    schema = inst.get_webui_config_schema()
    assert isinstance(schema, (dict, list)) and schema
    print(f"[OK] 默认配置导出 {len(defaults)} 项（含保留节），WebUI schema 可生成")

    await inst.on_unload()
    assert inst.service is None
    print("[OK] on_unload 清理完成（service 置空）")

    print("\n=== on_load/on_unload 集成测试通过 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
