"""注入假 ctx，验证命令处理器的发送链路与参数解析（不联网）。"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import sys
from pathlib import Path

from PIL import Image

PLUGIN_DIR = Path(__file__).resolve().parent.parent


class FakeSend:
    def __init__(self) -> None:
        self.texts: list[tuple[str, str]] = []
        self.images: list[tuple[bytes, str]] = []
        self.hybrids: list[tuple[list, str]] = []

    async def text(self, content: str, stream_id: str, **kwargs):
        self.texts.append((content, stream_id))
        return True

    async def image(self, data: str, stream_id: str, **kwargs):
        self.images.append((base64.b64decode(data), stream_id))
        return True

    async def hybrid(self, segments: list, stream_id: str, **kwargs):
        self.hybrids.append((segments, stream_id))
        for seg in segments:
            if seg.get("type") == "image":
                self.images.append((base64.b64decode(seg["content"]), stream_id))
            elif seg.get("type") == "text":
                self.texts.append((seg["content"], stream_id))
        return True


class FakePaths:
    data_dir = "/tmp/hd2_fake_data"


class FakeCtx:
    def __init__(self) -> None:
        self.send = FakeSend()
        self.paths = FakePaths()


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        "_maibot_plugin_hd2_fake",
        str(PLUGIN_DIR / "plugin.py"),
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_maibot_plugin_hd2_fake"] = module
    spec.loader.exec_module(module)
    return module.create_plugin()


async def main() -> int:
    inst = load_plugin()
    ctx = FakeCtx()
    inst._ctx = ctx

    # 1) 帮助命令
    result = await inst.cmd_help(stream_id="s1")
    assert result[0] is True and result[2] == 2, result
    assert ctx.send.texts and ctx.send.texts[0][1] == "s1"
    assert "Helldivers 2 银河战争" in ctx.send.texts[0][0]
    print("[OK] cmd_help 发送 HELP_TEXT，返回三元组")

    # 2) 图片发送（真实 PNG -> base64 -> send.image）
    tmp_png = Path("/tmp/hd2_test_img.png")
    Image.new("RGB", (32, 16), (30, 120, 60)).save(tmp_png)
    sent = await inst._send_images("s2", [tmp_png])
    assert sent and ctx.send.images and ctx.send.images[0][1] == "s2"
    assert ctx.send.images[0][0][:8] == b"\x89PNG\r\n\x1a\n"
    print("[OK] _send_images 读取 PNG 并以 base64 发送")

    # 3) 空图片列表 -> fallback 文本
    ctx2 = FakeCtx()
    inst._ctx = ctx2
    await inst._send_images("s3", [])
    assert "❌ 生成图片失败" in ctx2.send.texts[0][0]
    print("[OK] 空图片列表发送 fallback 文本")

    # 4) 军需簿无参数 -> 用法提示（不联网）
    await inst.cmd_arsenal_data(stream_id="s4")
    assert "用法: /hd2data" in ctx2.send.texts[-1][0]
    print("[OK] cmd_arsenal_data 空参数发送用法提示")

    # 5) planet 无参数 -> 用法提示
    await inst.cmd_planet(stream_id="s4")
    assert "用法: /planet" in ctx2.send.texts[-1][0]
    print("[OK] cmd_planet 空参数发送用法提示")

    # 6) 私聊中拒绝订阅（无 group_info）
    await inst.cmd_galaxy_news_subscribe(stream_id="s5")
    assert "仅支持在群聊" in ctx2.send.texts[-1][0]
    print("[OK] 订阅命令私聊防护生效")

    # 7) 未初始化时退订银河快报 -> 提示
    await inst.cmd_galaxy_news_unsubscribe(stream_id="s5")
    assert "未启用" in ctx2.send.texts[-1][0]
    print("[OK] 未启用监听时退订提示正常")

    # 8) matched_groups 与 raw_message 兜底解析
    arg1 = inst._arg({"matched_groups": {"faction": "Automaton"}}, "faction", set())
    assert arg1 == "Automaton"
    arg2 = inst._arg(
        {"matched_groups": {}, "raw_message": "/warfront 光能者"},
        "faction",
        {"warfront", "战线"},
    )
    assert arg2 == "光能者"
    print("[OK] _arg 命名组优先、raw_message 剥词兜底")

    # 9) cmd_map：图片发送失败时不得重复 caption
    from types import SimpleNamespace

    async def fake_map_result():
        return "CAPTION", tmp_png

    inst.service = SimpleNamespace(get_map_result=fake_map_result)

    ctx_map = FakeCtx()

    async def broken_image(data, stream_id, **kw):
        raise RuntimeError("send failed")

    async def broken_hybrid(segments, stream_id, **kw):
        raise RuntimeError("hybrid failed")

    ctx_map.send.image = broken_image
    ctx_map.send.hybrid = broken_hybrid
    inst._ctx = ctx_map
    await inst.cmd_map(stream_id="s6")
    captions = [t for t, _ in ctx_map.send.texts if t.startswith("CAPTION")]
    assert len(captions) == 1, f"caption 不应重复发送: {ctx_map.send.texts}"
    assert any("图片发送失败" in t for t, _ in ctx_map.send.texts)
    print("[OK] cmd_map 图片失败仅补发说明，不重复 caption")

    # 10) cmd_map：成功路径应走 hybrid 合并为一条消息
    ctx_map2 = FakeCtx()
    inst._ctx = ctx_map2
    await inst.cmd_map(stream_id="s6")
    assert len(ctx_map2.send.hybrids) == 1, "成功路径应使用 hybrid 单条发送"
    segs = ctx_map2.send.hybrids[0][0]
    assert [s["type"] for s in segs] == ["text", "image"], f"段顺序异常: {segs}"
    assert not any("图片发送失败" in t for t, _ in ctx_map2.send.texts)
    print("[OK] cmd_map 成功路径 hybrid 合并为一条图文消息")

    inst.service = None

    # 11) 超出 IPC 帧预算的图片自动降质；小图原样直通
    import os

    big = Image.frombytes("RGB", (2300, 2300), os.urandom(2300 * 2300 * 3))
    big_png = Path("/tmp/hd2_big_img.png")
    big.save(big_png, format="PNG")
    raw = big_png.read_bytes()
    assert len(raw) > 11 * 1024 * 1024, "测试图片应超过传输预算"
    fitted = inst._fit_image_for_transport(raw)
    assert fitted is not None, "超限图片应能重编码"
    assert len(fitted) <= 11 * 1024 * 1024, f"重编码后仍超限: {len(fitted)}"
    assert fitted[:2] == b"\xff\xd8", "应输出 JPEG"
    small = tmp_png.read_bytes()
    assert inst._fit_image_for_transport(small) == small, "小图应原样返回"
    ctx_img = FakeCtx()
    inst._ctx = ctx_img
    assert await inst._send_image_bytes("s7", raw)
    assert len(ctx_img.send.images) == 1
    print(
        f"[OK] 超帧图片 {len(raw) >> 20} MiB -> {len(fitted) >> 10} KiB，"
        "小图直通"
    )

    # 12) on_unload 空状态安全执行
    await inst.on_unload()
    print("[OK] on_unload 空状态安全执行")

    print("\n=== 交互测试全部通过 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
