#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置迁移脚本
自动将旧的 config.py 迁移到新的 config.yaml
"""

import os
import sys
import yaml


def read_old_config():
    """读取旧的 config.py 文件"""
    config_path = os.path.join(os.path.dirname(__file__), "config.py")

    if not os.path.exists(config_path):
        print(f"警告: 未找到旧配置文件 {config_path}")
        return None

    # 读取并执行 config.py 获取配置
    config_dict = {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 简单解析：提取变量赋值
        for line in content.split('\n'):
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                # 处理字符串值
                if value.startswith('"') and value.endswith('"'):
                    config_dict[key] = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    config_dict[key] = value[1:-1]
                else:
                    config_dict[key] = value

        return config_dict
    except Exception as e:
        print(f"读取旧配置文件时出错: {e}")
        return None


def create_new_config(old_config):
    """根据旧配置创建新的 config.yaml"""
    if not old_config:
        print("没有可迁移的配置")
        return None

    new_config = {
        "global": {
            "proxy": {
                "enabled": bool(old_config.get("GlOBAL_PROXY")),
                "server": old_config.get("GlOBAL_PROXY", "")
            },
            "logging": {
                "level": "INFO",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            }
        },
        "lightmanus": {
            "task_loader": {
                "json_path": old_config.get("JSON_PATH", "task/0101.json")
            },
            "task_decomposer": {
                "api_url": old_config.get("TD_API_URL", ""),
                "api_key": old_config.get("TD_API_KEY", ""),
                "model": old_config.get("TD_MODEL", "qwen-vl-max"),
                "proxy": None
            },
            "task_executor": {
                "api_url": old_config.get("TE_API_URL", ""),
                "api_key": old_config.get("TE_API_KEY", ""),
                "model": old_config.get("TE_MODEL", "qwen-vl-max"),
                "proxy": None
            },
            "answer_validator": {
                "api_url": old_config.get("AV_API_URL", ""),
                "api_key": old_config.get("AV_API_KEY", ""),
                "model": old_config.get("AV_MODEL", "deepseek-v3"),
                "proxy": None
            }
        },
        "jarvis": {
            "enabled": True,
            "adb": {
                "executable_path": "adb"
            },
            "device_providers": {
                "local": {"enabled": True},
                "remote_ip": {"enabled": False},
                "ssh_reverse_tunnel": {"enabled": False},
                "ssh_forward_tunnel": {"enabled": False}
            },
            "agent": {
                "max_steps": 15,
                "retry_on_error": {"enabled": True, "attempts": 3},
                "image_compression": {"enabled": True, "scale_factor": 0.5}
            },
            "llm": {
                "api_mode": "openai",
                "providers": {
                    "openai": {
                        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                        "api_key": old_config.get("TD_API_KEY", ""),  # 共享 API Key
                        "model": "qwen-vl-max",
                        "timeout": 120,
                        "is_vlm": True
                    },
                    "gemini": {
                        "api_key": "",
                        "model": "gemini-1.5-pro-latest",
                        "timeout": 120,
                        "is_vlm": True
                    },
                    "claude": {
                        "api_key": "",
                        "model": "claude-3-opus-20240229",
                        "timeout": 120,
                        "is_vlm": True
                    }
                }
            }
        },
        "mobile_agent_e": {
            "enabled": False,
            "base_path": "src/Agent/Operation_Agent/Mobile-Agent-E",
            "model": {
                "api_url": old_config.get("TD_API_URL", ""),
                "api_key": old_config.get("TD_API_KEY", ""),
                "model_name": old_config.get("MAE_MODEL", "qwen-vl-max")
            },
            "device": {
                "adb_path": "adb",
                "serial": None
            },
            "execution": {
                "max_steps": 15,
                "timeout": 600
            }
        },
        "pc_agent": {
            "enabled": False,
            "base_path": "src/Agent/Operation_Agent/PC-Agent",
            "model": {
                "api_url": old_config.get("TD_API_URL", ""),
                "api_key": old_config.get("TD_API_KEY", ""),
                "model_name": "qwen-vl-max"
            },
            "execution": {
                "max_steps": 15,
                "timeout": 600
            },
            "ocr": {
                "enabled": True,
                "model_path": "src/Agent/Operation_Agent/PC-Agent/OpenOCR"
            }
        }
    }

    return new_config


def main():
    print("="*60)
    print("LightManus 配置迁移工具")
    print("="*60)
    print()

    # 1. 读取旧配置
    print("步骤 1/3: 读取旧的 config.py...")
    old_config = read_old_config()

    if not old_config:
        print("未找到旧配置文件，将创建默认配置")
        old_config = {}

    print(f"  找到 {len(old_config)} 个配置项")
    for key, value in old_config.items():
        if 'KEY' in key:
            print(f"  - {key}: *** (已隐藏)")
        else:
            print(f"  - {key}: {value}")
    print()

    # 2. 创建新配置
    print("步骤 2/3: 生成新的 config.yaml...")
    new_config = create_new_config(old_config)

    if not new_config:
        print("生成配置失败")
        return

    output_path = os.path.join(os.path.dirname(__file__), "config.yaml")

    # 检查是否已存在
    if os.path.exists(output_path):
        print(f"  警告: {output_path} 已存在")
        response = input("  是否覆盖? (y/N): ").strip().lower()
        if response != 'y':
            print("  取消迁移")
            return

        # 备份现有配置
        backup_path = output_path + ".backup"
        import shutil
        shutil.copy2(output_path, backup_path)
        print(f"  已备份现有配置到: {backup_path}")

    # 写入新配置
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(new_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"  ✓ 已生成配置文件: {output_path}")
    print()

    # 3. 完成
    print("步骤 3/3: 迁移完成!")
    print()
    print("接下来的步骤:")
    print("  1. 编辑 config.yaml，填写所有 API Key 和必要的配置")
    print("  2. 运行测试: python -m src.config_loader")
    print("  3. 运行主程序: python run_light_manus.py")
    print()
    print("如需回滚，可使用备份文件:")
    if os.path.exists("config.py"):
        print(f"  - 旧配置: config.py")
    if os.path.exists("config.yaml.backup"):
        print(f"  - 备份: config.yaml.backup")
    print()
    print("="*60)


if __name__ == "__main__":
    main()
