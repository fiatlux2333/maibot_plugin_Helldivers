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
    assert defaults["enable_companion_screenshots"] is False, (
        "Companion 截图应默认关闭（依赖 playwright，见插件中心评审意见）"
    )
    schema = inst.get_webui_config_schema()
    assert isinstance(schema, (dict, list)) and schema
    print(f"[OK] 默认配置导出 {len(defaults)} 项（含保留节），WebUI schema 可生成")

    await inst.on_unload()
    assert inst.service is None
    print("[OK] on_unload 清理完成（service 置空）")

    # ---- 配置热应用：保存配置后自动按新配置重建组件，无需重载插件 ----
    inst2 = load_plugin()
    inst2._ctx = FakeCtx()
    raw2 = inst2.get_default_config()
    raw2["enable_companion_screenshots"] = False
    raw2["enable_background_refresh"] = False
    inst2.set_plugin_config(raw2)
    await inst2.on_load()
    old_service = inst2.service
    assert old_service is not None

    sys.modules["_maibot_plugin_hd2_onload"]._CONFIG_REAPPLY_DEBOUNCE_SECONDS = 0.05
    raw2["war_id"] = 802
    inst2.set_plugin_config(raw2)
    await inst2.on_config_update("self", raw2, "test-version")
    assert inst2._config_reapply_task is not None, "on_config_update 应调度重建任务"
    await inst2._config_reapply_task
    assert inst2.service is not old_service, "热应用应重建 service 实例"
    assert inst2.service.client.war_id == 802, "重建后应使用新配置"
    assert inst2._config_reapply_task is None, "worker 结束后应清空任务引用"
    assert not inst2._config_reapply_pending
    print("[OK] on_config_update 热应用：组件按新配置自动重建（war_id=802）")

    # ---- on_unload 取消挂起的重建，不再拉起组件 ----
    raw2["war_id"] = 803
    inst2.set_plugin_config(raw2)
    await inst2.on_config_update("self", raw2, "test-version")
    pending_task = inst2._config_reapply_task
    assert pending_task is not None and not pending_task.done()
    await inst2.on_unload()
    assert pending_task.done(), "on_unload 应取消挂起的重建任务"
    assert inst2.service is None, "卸载后不应因热应用再次构造组件"
    assert inst2._config_reapply_task is None
    print("[OK] on_unload 取消挂起的配置重建，干净卸载")

    print("\n=== on_load/on_unload 集成测试通过 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
