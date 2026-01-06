# LightManus

<div align="center">

**一个强大的多 Agent 任务执行框架**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

## 📖 简介

LightManus 是一个智能任务执行框架，能够自动分解复杂任务并使用多种 AI Agent 完成执行。框架集成了任务分解、任务执行、答案验证等完整流程，支持移动端和桌面端设备的自动化操作。

### 核心特性

- 🤖 **智能任务分解**：自动将复杂任务分解为可执行的原子任务
- 🔄 **多 Agent 支持**：集成 Jarvis、Mobile-Agent-E、PC-Agent 等多种 Agent
- ✅ **自动答案验证**：使用 LLM 验证任务执行结果的准确性
- 📊 **完整轨迹记录**：详细记录每个步骤的执行过程
- ⚙️ **统一配置管理**：使用 YAML 配置文件管理所有组件
- 🔌 **灵活扩展**：易于添加新的 Agent 类型和功能

## 🏗️ 架构设计

```
LightManus
├── 任务分解层 (TaskDecomposer)
│   └── 将复杂任务分解为原子任务序列
│
├── 任务执行层 (TaskExecutionAgent)
│   ├── 任务调度
│   ├── Agent 路由
│   └── 结果收集
│
├── Agent 执行层 (Operation Agents)
│   ├── Jarvis Agent          # Android 设备控制
│   ├── Mobile-Agent-E        # 移动端自动化
│   └── PC-Agent              # 桌面端自动化
│
└── 验证层 (AnswerValidationAgent)
    └── 验证任务执行结果的准确性
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <your-repo-url>
cd LightManus

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置设置

编辑项目根目录的 `config.yaml` 文件：

```yaml
lightmanus:
  task_loader:
    json_path: "task/0101.json"

  task_decomposer:
    api_url: "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    api_key: "YOUR_API_KEY"  # 填入你的 API Key
    model: "qwen-vl-max"

  task_executor:
    api_url: "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    api_key: "YOUR_API_KEY"
    model: "qwen-vl-max"

  answer_validator:
    api_url: "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    api_key: "YOUR_API_KEY"
    model: "deepseek-v3"

jarvis:
  enabled: true
  adb:
    executable_path: "adb"
  llm:
    providers:
      openai:
        api_key: "YOUR_API_KEY"
        model: "qwen-vl-max"
```

**配置说明**：
- `api_key`: 填入你的 LLM API Key（推荐使用阿里云通义千问）
- `model`: 选择要使用的模型名称
- 更多配置选项请参考 `config.yaml` 中的详细注释

### 3. 准备任务数据

创建任务 JSON 文件（例如 `task/0101.json`）：

```json
{
  "Task": "打开计算器，计算123乘以456，告诉我答案",
  "Task_ID": "0101",
  "Answer": "56088",
  "atomic_tasks": [
    {
      "atomic_tasks_ID": 1,
      "atomic_tasks_answer": "56088",
      "atomic_tasks_description": "打开计算器，计算123乘以456"
    }
  ]
}
```

### 4. 运行程序

```bash
python run_light_manus.py
```

## 📁 项目结构

```
LightManus/
├── config.yaml              # 统一配置文件
├── run_light_manus.py       # 主程序入口
├── requirements.txt         # Python 依赖
│
├── src/
│   ├── config_loader.py     # 配置加载器
│   │
│   └── Agent/
│       ├── task_decompose_agent.py      # 任务分解 Agent
│       ├── task_execution_agent.py      # 任务执行 Agent
│       ├── answer_validation_agent.py   # 答案验证 Agent
│       ├── task_roader.py               # 任务数据加载
│       └── task_operator_agent.py       # Agent 调度器
│
├── src/Agent/Operation_Agent/
│   ├── Jarvis_V2/              # Jarvis Agent
│   │   ├── jarvis/
│   │   │   ├── agent.py        # Agent 核心逻辑
│   │   │   ├── modules/
│   │   │   │   ├── observer.py  # 设备观察
│   │   │   │   └── actuator.py  # 设备操作
│   │   │   └── llm/
│   │   └── run_wrapper.py      # 包装脚本
│   │
│   ├── Mobile-Agent-E/         # 移动端 Agent
│   └── PC-Agent/               # 桌面端 Agent
│
└── task/                       # 任务数据目录
    └── 0101.json
```

## 🤖 支持的 Agent

### 1. Jarvis Agent

**适用场景**：Android 设备自动化操作

**特性**：
- 通过 ADB 控制 Android 设备
- 支持 UI 元素识别和交互
- 实时屏幕分析和决策
- 支持多种设备连接方式（USB、网络、SSH隧道）

**设备要求**：
- Android 设备或模拟器
- 已启用 USB 调试
- 已安装 ADB 工具

**配置示例**：
```json
{
  "atomic_tasks_agent": "jarvis_agent",
  "atomic_tasks_description": "打开计算器，计算123乘以456"
}
```

### 2. Mobile-Agent-E

**适用场景**：移动端应用自动化

**特性**：
- 支持移动应用截图分析
- 基于 OCR 的 UI 理解
- 适合复杂移动应用操作

### 3. PC-Agent

**适用场景**：Windows 桌面自动化

**特性**：
- 桌面应用操作
- OCR 识别
- 鼠标键盘模拟

## ⚙️ 配置详解

### 配置文件结构

```yaml
# 全局配置
global:
  proxy:
    enabled: false
    server: "http://127.0.0.1:7890"
  logging:
    level: "INFO"

# LightManus 框架配置
lightmanus:
  task_loader:
    json_path: "task/0101.json"

  task_decomposer:
    api_url: "..."
    api_key: "..."
    model: "qwen-vl-max"

  task_executor:
    api_url: "..."
    api_key: "..."
    model: "qwen-vl-max"

  answer_validator:
    api_url: "..."
    api_key: "..."
    model: "deepseek-v3"

# Jarvis Agent 配置
jarvis:
  enabled: true
  adb:
    executable_path: "adb"
  device_providers:
    local:
      enabled: true
    remote_ip:
      enabled: false
      remotes:
        - host: "192.168.1.100:5555"
  agent:
    max_steps: 15
    retry_on_error:
      enabled: true
      attempts: 3
  llm:
    api_mode: "openai"
    providers:
      openai:
        api_key: "..."
        model: "qwen-vl-max"
```

### 环境变量（可选）

```bash
export TD_API_KEY="your-task-decomposer-key"
export TE_API_KEY="your-task-executor-key"
export AV_API_KEY="your-validator-key"
```

## 🔧 使用示例

### 示例 1: 简单计算任务

**任务**：打开计算器计算 123 × 456

```bash
# 1. 创建任务文件 task/calc.json
{
  "Task": "打开计算器，计算123乘以456",
  "Task_ID": "calc001",
  "Answer": "56088"
}

# 2. 更新 config.yaml 中的 json_path
# 3. 运行
python run_light_manus.py
```

### 示例 2: 信息查询任务

**任务**：在维基百科搜索周杰伦

```json
{
  "Task": "打开维基百科，搜索周杰伦，告诉我他2000年发布的专辑",
  "Task_ID": "wiki001",
  "Answer": "周杰伦"
}
```

### 示例 3: 混合 Agent 任务

```json
{
  "Task": "先在手机上打开计算器，然后在电脑上记录结果",
  "Task_ID": "mixed001",
  "atomic_tasks": [
    {
      "atomic_tasks_ID": 1,
      "atomic_tasks_agent": "jarvis_agent",
      "atomic_tasks_description": "在手机上打开计算器计算100+200"
    },
    {
      "atomic_tasks_ID": 2,
      "atomic_tasks_agent": "pc_agent_win",
      "atomic_tasks_description": "在电脑上记录计算结果"
    }
  ]
}
```

## 🔍 故障排查

### 常见问题

**Q1: 提示 "API Key 未配置"**

```bash
# 检查配置文件
python -m src.config_loader

# 确保 config.yaml 中所有 api_key 字段已填写
```

**Q2: Jarvis 找不到设备**

```bash
# 检查 ADB 连接
adb devices

# 确保 config.yaml 中配置正确
jarvis:
  adb:
    executable_path: "adb"  # 或完整路径
  device_providers:
    local:
      enabled: true
```

**Q3: 任务分解失败**

- 检查 LLM API 是否可用
- 确认 API Key 有效
- 查看日志文件了解详细错误

**Q4: Agent 执行超时**

```yaml
# 在 config.yaml 中增加超时时间
jarvis:
  agent:
    max_steps: 20  # 增加最大步数
```

### 日志查看

执行日志保存在：
```
Log/
└── {model-name}/
    └── {date}/
        └── {task-id}/
            ├── Task_Split_Original.json     # 分解结果
            ├── Task_Split_Final.json        # 最终结果
            └── {atomic-task-id}/
                └── task_answer.json          # 原子任务答案
```

## 📚 进阶使用

### 自定义 Agent

参考 `src/Agent/task_operator_agent.py` 添加新的 Agent：

```python
def call_your_agent(instruction, log_dir, task_id):
    """实现你的 Agent 调用逻辑"""
    pass

def operator(agent, ...):
    if agent == "your_agent":
        call_your_agent(instruction, log_dir, task_id)
```

### 多环境配置

```bash
# 开发环境
cp config.yaml config.dev.yaml

# 生产环境
cp config.yaml config.prod.yaml

# 使用特定配置
config.load_config("config.prod.yaml")
```

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出建议！

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

本项目集成了以下优秀的开源项目：

- [MobileAgent](https://github.com/X-PLUG/MobileAgent) - 移动端和桌面端 AI Agent
- [Jarvis](https://github.com/xlang-ai/Jarvis) - Android 设备控制框架
- 通义千问 (Qwen) - 阿里云大语言模型

## 📧 联系方式

- 项目主页：[GitHub Repository]
- 问题反馈：[Issues]
- 讨论交流：[Discussions]

---

<div align="center">

**如果觉得这个项目有帮助，请给个 ⭐️ Star 支持一下！**

Made with ❤️ by LightManus Team

</div>
