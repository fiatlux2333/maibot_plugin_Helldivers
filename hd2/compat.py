"""跨平台兼容层：替代 AstrBot 的 logger 与插件数据目录解析。

MaiBot 插件运行在 Runner 子进程中，业务代码只依赖本模块即可，
不感知宿主平台；宿主相关能力（发送消息、配置）由 plugin.py 注入。
"""

from __future__ import annotations

import logging
from pathlib import Path

# 统一日志名：Runner 侧日志聚合按 "plugin." 前缀识别插件日志。
logger = logging.getLogger("plugin.hd2")

_DATA_DIR_BASE: Path | None = None


def set_plugin_data_base(base: Path | str | None) -> None:
    """由入口（plugin.py 的 on_load）注入 MaiBot 持久化数据目录基路径。"""
    global _DATA_DIR_BASE
    _DATA_DIR_BASE = Path(base) if base is not None else None


def get_plugin_data_dir(plugin_name: str = "hd2") -> Path:
    """获取插件持久化数据目录。

    已注入 MaiBot 数据目录时返回 ``<data_dir>/<plugin_name>``；
    未注入（脱离宿主的单元测试场景）时退回源码包旁的运行目录。
    """
    if _DATA_DIR_BASE is not None:
        path = _DATA_DIR_BASE / plugin_name
    else:
        path = Path(__file__).resolve().parent / "data_runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path
