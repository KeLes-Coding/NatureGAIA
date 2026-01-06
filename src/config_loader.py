# -*- coding: utf-8 -*-
"""
统一配置加载器
负责加载和管理 LightManus 框架的所有配置
"""

import yaml
import os
from typing import Dict, Any, Optional


class ConfigLoader:
    """统一配置加载器"""

    _instance = None
    _config: Dict[str, Any] = None

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化配置加载器"""
        if self._config is None:
            self.load_config()

    @staticmethod
    def get_project_root() -> str:
        """获取项目根目录"""
        # 从当前文件向上查找项目根目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 假设项目根目录是 src 的上一级
        project_root = os.path.dirname(current_dir)
        return project_root

    def get_config_path(self) -> str:
        """获取配置文件路径"""
        project_root = self.get_project_root()
        config_path = os.path.join(project_root, "config.yaml")
        return config_path

    def load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        加载配置文件

        Args:
            config_path: 配置文件路径，如果为 None 则使用默认路径

        Returns:
            配置字典
        """
        if config_path is None:
            config_path = self.get_config_path()

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f)
            return self._config
        except FileNotFoundError:
            raise FileNotFoundError(
                f"配置文件未找到: {config_path}\n"
                f"请确保 config.yaml 文件存在于项目根目录"
            )
        except yaml.YAMLError as e:
            raise ValueError(f"配置文件格式错误: {e}")

    def get_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        if self._config is None:
            self.load_config()
        return self._config

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        使用点号分隔的路径获取配置值

        Args:
            key_path: 配置路径，例如 "lightmanus.task_decomposer.model"
            default: 默认值

        Returns:
            配置值，如果不存在则返回默认值

        Examples:
            config = ConfigLoader()
            api_key = config.get("lightmanus.task_decomposer.api_key")
            enabled = config.get("jarvis.enabled", False)
        """
        config = self.get_config()
        keys = key_path.split(".")

        value = config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    # ========== LightManus 框架配置 ==========

    def get_global_proxy(self) -> Optional[str]:
        """获取全局代理设置"""
        enabled = self.get("global.proxy.enabled", False)
        if enabled:
            return self.get("global.proxy.server")
        return None

    def get_task_loader_config(self) -> Dict[str, Any]:
        """获取任务加载器配置"""
        return self.get("lightmanus.task_loader", {})

    def get_task_decomposer_config(self) -> Dict[str, Any]:
        """获取任务分解 Agent 配置"""
        config = self.get("lightmanus.task_decomposer", {})
        # 如果没有单独配置代理，使用全局代理
        if config.get("proxy") is None:
            config["proxy"] = self.get_global_proxy()
        return config

    def get_task_executor_config(self) -> Dict[str, Any]:
        """获取任务执行 Agent 配置"""
        config = self.get("lightmanus.task_executor", {})
        if config.get("proxy") is None:
            config["proxy"] = self.get_global_proxy()
        return config

    def get_answer_validator_config(self) -> Dict[str, Any]:
        """获取答案验证 Agent 配置"""
        config = self.get("lightmanus.answer_validator", {})
        if config.get("proxy") is None:
            config["proxy"] = self.get_global_proxy()
        return config

    # ========== Jarvis Agent 配置 ==========

    def is_jarvis_enabled(self) -> bool:
        """检查 Jarvis Agent 是否启用"""
        return self.get("jarvis.enabled", False)

    def get_jarvis_config(self) -> Dict[str, Any]:
        """获取 Jarvis Agent 完整配置"""
        jarvis_config = self.get("jarvis", {})

        # 处理代理设置
        global_proxy = self.get_global_proxy()
        if global_proxy and "proxy" not in jarvis_config:
            jarvis_config["proxy"] = {"enabled": True, "server": global_proxy}
        elif "proxy" not in jarvis_config:
            jarvis_config["proxy"] = {"enabled": False}

        return jarvis_config

    def get_jarvis_adb_config(self) -> Dict[str, Any]:
        """获取 Jarvis ADB 配置"""
        return self.get("jarvis.adb", {"executable_path": "adb"})

    def get_jarvis_device_providers(self) -> Dict[str, Any]:
        """获取 Jarvis 设备提供者配置"""
        return self.get("jarvis.device_providers", {})

    def get_jarvis_agent_config(self) -> Dict[str, Any]:
        """获取 Jarvis Agent 行为配置"""
        return self.get("jarvis.agent", {
            "max_steps": 15,
            "retry_on_error": {"enabled": True, "attempts": 3},
            "image_compression": {"enabled": True, "scale_factor": 0.5}
        })

    def get_jarvis_llm_config(self) -> Dict[str, Any]:
        """获取 Jarvis LLM 配置"""
        return self.get("jarvis.llm", {})

    # ========== Mobile-Agent-E 配置 ==========

    def is_ma_e_enabled(self) -> bool:
        """检查 Mobile-Agent-E 是否启用"""
        return self.get("mobile_agent_e.enabled", False)

    def get_ma_e_config(self) -> Dict[str, Any]:
        """获取 Mobile-Agent-E 配置"""
        return self.get("mobile_agent_e", {})

    # ========== PC-Agent 配置 ==========

    def is_pc_agent_enabled(self) -> bool:
        """检查 PC-Agent 是否启用"""
        return self.get("pc_agent.enabled", False)

    def get_pc_agent_config(self) -> Dict[str, Any]:
        """获取 PC-Agent 配置"""
        return self.get("pc_agent", {})


# ========== 便捷函数 ==========

# 全局配置加载器实例
_config_loader = None


def get_config_loader() -> ConfigLoader:
    """获取配置加载器实例"""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader


def reload_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """重新加载配置"""
    loader = get_config_loader()
    return loader.load_config(config_path)


def get_config(key_path: str, default: Any = None) -> Any:
    """便捷函数：获取配置值"""
    loader = get_config_loader()
    return loader.get(key_path, default)


# ========== 兼容性：支持旧的 config.py ==========

def create_legacy_config_module():
    """
    创建与旧 config.py 兼容的接口
    这个函数会生成一个包含所有旧配置变量的字典
    """
    loader = get_config_loader()

    # 从新配置中提取旧格式的配置
    legacy_config = {
        # 全局代理
        "GlOBAL_PROXY": loader.get_global_proxy() or "",

        # 任务加载器
        "JSON_PATH": loader.get("lightmanus.task_loader.json_path", "task/0101.json"),
        "MAE_MODEL": loader.get("lightmanus.task_decomposer.model", "qwen-vl-max"),

        # 任务分解 Agent
        "TD_API_KEY": loader.get("lightmanus.task_decomposer.api_key", ""),
        "TD_API_URL": loader.get("lightmanus.task_decomposer.api_url", ""),
        "TD_MODEL": loader.get("lightmanus.task_decomposer.model", "qwen-vl-max"),

        # 任务执行 Agent
        "TE_API_KEY": loader.get("lightmanus.task_executor.api_key", ""),
        "TE_API_URL": loader.get("lightmanus.task_executor.api_url", ""),
        "TE_MODEL": loader.get("lightmanus.task_executor.model", "qwen-vl-max"),

        # 答案验证 Agent
        "AV_API_KEY": loader.get("lightmanus.answer_validator.api_key", ""),
        "AV_API_URL": loader.get("lightmanus.answer_validator.api_url", ""),
        "AV_MODEL": loader.get("lightmanus.answer_validator.model", "deepseek-v3"),
    }

    return legacy_config


if __name__ == "__main__":
    """测试配置加载"""
    print("=== 测试配置加载器 ===\n")

    loader = ConfigLoader()

    print("1. 全局配置:")
    print(f"   代理: {loader.get_global_proxy()}")
    print(f"   日志级别: {loader.get('global.logging.level')}")

    print("\n2. LightManus 配置:")
    print(f"   任务文件: {loader.get('lightmanus.task_loader.json_path')}")
    print(f"   分解模型: {loader.get('lightmanus.task_decomposer.model')}")
    print(f"   执行模型: {loader.get('lightmanus.task_executor.model')}")
    print(f"   验证模型: {loader.get('lightmanus.answer_validator.model')}")

    print("\n3. Jarvis 配置:")
    print(f"   启用: {loader.is_jarvis_enabled()}")
    print(f"   ADB路径: {loader.get_jarvis_adb_config().get('executable_path')}")
    print(f"   最大步数: {loader.get_jarvis_agent_config().get('max_steps')}")
    print(f"   LLM模式: {loader.get_jarvis_llm_config().get('api_mode')}")

    print("\n4. 便捷路径访问:")
    print(f"   jarvis.agent.max_steps = {loader.get('jarvis.agent.max_steps')}")
    print(f"   jarvis.llm.api_mode = {loader.get('jarvis.llm.api_mode')}")

    print("\n5. 兼容旧配置:")
    legacy_config = create_legacy_config_module()
    for key, value in legacy_config.items():
        print(f"   {key} = {value if value else '(空)'}")

    print("\n=== 测试完成 ===")
