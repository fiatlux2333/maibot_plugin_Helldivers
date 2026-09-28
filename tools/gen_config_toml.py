"""从 hd2/config_schema.py 生成带中文注释的 config.toml。

仓库附带生成结果，用户安装即得中文注释配置；Runner 加载时以
"更新已有键、补充缺失键"策略合并（tomlkit 保留注释），仅在配置
版本升级时才整体重写。

用法：在仓库根目录执行  python tools/gen_config_toml.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util


def _load_plugin_module():
    spec = importlib.util.spec_from_file_location(
        "_gen_cfg", str(ROOT / "plugin.py"), submodule_search_locations=[str(ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_gen_cfg"] = module
    spec.loader.exec_module(module)
    return module


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"不支持的默认值类型: {type(value)!r}")


def main() -> int:
    module = _load_plugin_module()
    inst = module.create_plugin()
    defaults = inst.build_default_config()

    # 从 config_schema.py 源码解析「分组注释 -> 字段名」序列，保证与模型同序
    src = (ROOT / "hd2" / "config_schema.py").read_text("utf-8")
    tokens: list[tuple[str | None, str]] = []
    section: str | None = None
    for line in src.splitlines():
        m_section = re.match(r"^\s*#\s*----\s*(.+?)\s*----\s*$", line)
        if m_section:
            section = m_section.group(1).strip()
            continue
        m_field = re.match(r"^    (\w+):", line)
        if m_field:
            tokens.append((section, m_field.group(1)))

    config_cls = type(inst.config_model())
    descriptions = {}
    for name, field in config_cls.model_fields.items():
        descriptions[name] = str(field.description or "").strip()

    lines: list[str] = []
    lines.append("# ============================================================")
    lines.append("# 绝地潜兵2情报助手（maibot_plugin_Helldivers）配置")
    lines.append("# -------------------------------------------------------------")
    lines.append("# · 本文件附带中文注释；MaiBot Runner 加载时会保留注释，")
    lines.append("#   仅自动补齐缺失字段，可放心修改和保留注释。")
    lines.append("# · 修改后需重载插件（WebUI 或 touch plugin.py）生效。")
    lines.append("# · 文件末尾 [plugin] 节为 Runner 保留节（config_version），勿删改。")
    lines.append("# · bilibili_cookie / translation_api_key 等密钥请勿提交到仓库。")
    lines.append("# ============================================================")
    lines.append("")

    seen: set[str] = set()
    current_section = None
    for section_name, field_name in tokens:
        if field_name in seen or field_name not in defaults or field_name == "plugin":
            continue
        if section_name != current_section:
            current_section = section_name
            lines.append("")
            lines.append(f"# ──────────── {section_name} ────────────")
            lines.append("")
        desc = descriptions.get(field_name, "").replace("\n", " ")
        if desc:
            lines.append(f"# {desc}")
        lines.append(f"{field_name} = {_toml_value(defaults[field_name])}")
        lines.append("")
        seen.add(field_name)

    missing = set(defaults) - seen - {"plugin"}
    if missing:
        raise SystemExit(f"生成器遗漏字段: {sorted(missing)}")

    # TOML 语法：顶层键必须位于任何表头之前，保留节放文件末尾
    lines.append("# [plugin] 保留节：由 Runner 维护，勿修改")
    lines.append("[plugin]")
    lines.append('config_version = "1"')

    out = ROOT / "config.toml"
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    # 自校验：生成的值必须与模型默认值完全一致
    import tomllib

    parsed = tomllib.loads(out.read_text("utf-8"))
    assert parsed["plugin"]["config_version"] == defaults["plugin"]["config_version"]
    for key, value in defaults.items():
        if key == "plugin":
            continue
        assert parsed[key] == value, f"{key}: {parsed[key]!r} != {value!r}"
    print(f"OK: 生成 {out}（{len(defaults)} 项，值与模型默认值一致）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
