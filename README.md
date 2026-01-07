# NaturalGAIA & LightManus
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**NaturalGAIA: 面向长时序 GUI 任务的可验证基准**  
**LightManus: 动态拓扑规划与分层协作 Agent 框架**

## 📖 简介 (Introduction)

本项目是论文 "NaturalGAIA: A Verifiable Benchmark and Hierarchical Framework for Long-Horizon GUI Tasks" 的官方实现。我们致力于解决当前 GUI Agent 领域中**高保真现实性（High-fidelity Realism）与可验证评估准确性（Verifiable Evaluation Accuracy）**难以兼得的问题。

本项目包含两个核心部分：

### NaturalGAIA (Benchmark)

一个基于真实人类 GUI 交互意图构建的可验证评估数据集。它通过解耦逻辑因果路径与语言叙述，模拟了具有认知非线性和上下文依赖性的自然人类意图。

<div align="center">
<img src="static/BG-1.png" width="50%" alt="NaturalGAIA Dataset Construction Process">

*图 1: NaturalGAIA 数据集构建流程 (Dataset Construction)*
</div>

### LightManus & Jarvis (Framework)

一个分层协作框架。
- **LightManus**: 作为"大脑"，负责动态拓扑规划（Dynamic Topological Planning）和上下文演进管理
- **Jarvis/Operation Agents**: 作为"手"，通过混合视觉-结构感知（Hybrid Visual-Structural Perception）确保在 Android、PC 等多平台上的执行精度

实验表明，该框架在 Weighted Pathway Success Rate (WPSR) 上达到了 **57.0%**，显著优于现有基线。

## 🏗️ 架构设计 (Architecture)

本框架采用分层设计，代码结构与论文逻辑高度一致。下图展示了 LightManus 如何作为大脑进行规划，以及 Jarvis 等 Agent 如何作为手进行执行：

<div align="center">
<img src="static/main_v1_2512125-1.png" width="100%" alt="LightManus Framework Architecture">

*图 2: LightManus & Jarvis 分层协作框架架构图 (Main Architecture)*
</div>

<details>
<summary>点击查看 Mermaid 架构流程图</summary>

```mermaid
graph TD
    User[用户指令] --> LM[LightManus (Task Decomposer)]
    LM -->|原子任务序列| TE[Task Executor Agent]
    
    subgraph "执行层 (Operation Agents)"
        TE -->|路由分发| Jarvis[Jarvis (Android)]
        TE -->|路由分发| MAE[Mobile-Agent-E (移动端视觉)]
        TE -->|路由分发| PC[PC-Agent (Windows/macOS)]
    end
    
    Jarvis -->|执行反馈| TE
    MAE -->|执行反馈| TE
    PC -->|执行反馈| TE
    
    TE -->|最终状态| AV[Answer Validation Agent]
    AV -->|验证结果| Report[评估报告]
```
</details>

### 核心组件

#### Task Decomposer (LightManus)
- **位置**: `src/Agent/task_decompose_agent.py`
- **功能**: 负责将复杂的自然语言指令分解为原子任务（Atomic Tasks），并处理任务间的依赖关系

#### Operation Agents

**Jarvis**
- **位置**: `src/Agent/Operation_Agent/Jarvis`
- **功能**: 基于 ADB 的 Android 设备深度控制，支持 View Hierarchy 分析

**Mobile-Agent-E**
- **位置**: `src/Agent/Operation_Agent/Mobile-Agent-E`
- **功能**: 基于纯视觉大模型的移动端 Agent，适用于复杂 UI 场景

**PC-Agent**
- **位置**: `src/Agent/Operation_Agent/PC-Agent`
- **功能**: 支持 Windows 和 macOS 的桌面自动化操作

#### Answer Validator
- **位置**: `src/Agent/answer_validation_agent.py`
- **功能**: 利用 LLM 对任务执行结果进行语义级和状态级的双重验证，确保基准测试的准确性

## 🚀 快速开始 (Quick Start)

### 1. 环境准备

```bash
# 克隆项目
git clone https://anonymous.4open.science/r/NatureGAIA-721F/
cd NaturalGAIA

# 创建并激活 Conda 环境（推荐）
conda create -n naturalgaia python=3.10
conda activate naturalgaia

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置文件

项目使用 `config.yaml` 进行统一管理。如果需要重置配置，可以从模板恢复：

```bash
# 可选：如果需要重置配置
cp config.template.yaml config.yaml
```

编辑 `config.yaml`，关键配置项说明如下：

```yaml
lightmanus:
  task_loader:
    json_path: "task/0101.json"  # 指定要执行的任务文件

  # 任务分解器 (LightManus Core)
  task_decomposer:
    api_url: "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    api_key: "YOUR_API_KEY"      # 推荐使用 Qwen-VL-Max 或类似高性能模型
    model: "qwen-vl-max"

  # 答案验证器
  answer_validator:
    model: "deepseek-v3"         # 验证模块建议使用推理能力强的模型

# Agent 具体配置
jarvis:
  enabled: true
  adb:
    executable_path: "adb"       # 确保系统环境变量中有 adb
```

### 3. 数据集与任务格式

NaturalGAIA 基准测试任务存储在 `task/` 目录下。标准的数据格式如下（JSON）：

```json
{
  "Task": "使用 Wikipedia 搜索周杰伦，查看他在2000年发行的专辑？然后告诉我这张专辑包含哪些曲目？",
  "Task_ID": "0101",
  "level": 1,
  "atomic_tasks_number": 2,
  "atomic_tasks_answer": [
    {
      "atomic_tasks_ID": 1,
      "answer": "Jay"
    },
    {
      "atomic_tasks_ID": 2,
      "answer": "可爱女人, 完美主义, 星晴, 娘子, 斗牛, 黑色幽默, 伊斯坦堡, 印度老老鹰, 龙卷风, 反方向的钟"
    }
  ],
  "final_answer": "可爱女人, 完美主义, 星晴, 娘子, 斗牛, 黑色幽默, 伊斯坦堡, 印度老老鹰, 龙卷风, 反方向的钟"
}
```

> **注**：`final_answer` 字段包含完整的最终答案，`atomic_tasks_answer` 数组包含每个原子任务的预期答案。

### 4. 运行评估

运行主程序即可启动 LightManus 框架对指定任务的推理与执行：

```bash
python run_light_manus.py
```

如果你希望运行完整的基准测试套件：

```bash
# 运行 benchmark 模式（遍历 task 目录下的所有任务）
python run_light_manus.py --benchmark
```

## 📁 项目结构 (Project Structure)

```
NaturalGAIA/
├── config.yaml                 # 用户配置文件
├── run_light_manus.py          # 程序入口
├── src/
│   ├── config_loader.py        # 配置加载模块
│   └── Agent/
│       ├── task_decompose_agent.py   # [LightManus] 任务规划与分解
│       ├── task_execution_agent.py   # [Executor] 任务调度与执行
│       ├── answer_validation_agent.py# [Validator] 结果验证
│       └── Operation_Agent/          # 底层操作 Agent 集合
│           ├── Jarvis/               # Android 结构化控制
│           ├── Mobile-Agent-E/       # Android 视觉控制
│           └── PC-Agent/             # 桌面端控制
└── task/                       # NaturalGAIA Benchmark 数据集
```

## 📊 性能基准 (Benchmarks)

我们在 NaturalGAIA 数据集上对比了 LightManus 与其他主流 Agent 框架的表现。以下是主要实验结果：

### 主要结果对比

| Method | Level-1 SR | Level-2 SR | Level-3 SR | Overall SR | Overall WPSR | Overall MAT/CR | Overall ATSR |
|--------|------------|------------|------------|------------|--------------|----------------|--------------|
| **LightManus_Jarvis (Gemini-3.0-pro)** | **86.7%** | 30.0% | **30.0%** | **54.3%** | **44.1%** | **73.0%** | **57.0%** |
| **LightManus_Jarvis (Gemini-3.0-flash)** | **86.7%** | 30.0% | **30.0%** | **54.3%** | 40.4% | 68.2% | 46.7% |
| LightManus_Jarvis (GPT-5.2) | 66.7% | **40.0%** | **40.0%** | **51.4%** | 43.7% | 55.7% | 44.3% |
| LightManus_Jarvis (Claude-Sonnet-4.5) | 66.7% | **50.0%** | **40.0%** | **54.3%** | **45.6%** | 67.6% | **53.9%** |
| LightManusGemini-2_Jarvis (.5-pro) | 73.3% | **40.0%** | 20.0% | 48.6% | 38.3% | 68.3% | 52.4% |
| LightManus_Mobile-Agent-e (Gemini-2.5-Pro) | 73.3% | 20.0% | 10.0% | 40.0% | 28.3% | 54.4% | 36.3% |
| Mobile-Agent-e (Gemini-2.5-Pro) | 46.7% | 10.0% | 0.0% | 22.9% | 21.1% | 53.0% | 30.4% |
| PC-Agent (Gemini-2.5-Pro) | 40.0% | 10.0% | 0.0% | 20.0% | 13.1% | 45.5% | 25.7% |

### 性能效率对比

| Agent | Input Tokens | Output Tokens | Total Tokens | Average Steps | Duration (s) |
|-------|--------------|---------------|--------------|---------------|--------------|
| **Jarvis** | 16,904.8 | 2,276.2 | 19,181.0 | 6.9 | **84.1** |
| Mobile-Agent-e | 67,311.4 | 9,154.6 | 76,466.0 | 7.2 | 365.2 |

### 错误分析 (Error Analysis)

下图展示了不同模块在失败案例中的占比分析：

<div align="center">
<img src="static/EA-1.png" width="50%" alt="Error Analysis Chart">

*图 3: 错误分析 (Error Analysis)*
</div>

> **注**：SR表示Success Rate (P@1/4)，WPSR表示Weighted Pathway Success Rate，MAT/CR表示路径准确率，ATSR表示平均任务成功率。粗体表示最佳性能，下划线表示次佳性能。详细实验设置与消融实验结果请参阅论文第 5 章节。

## 🤝 贡献与引用 (Citation)

如果你在研究中使用了 NaturalGAIA 数据集或 LightManus 框架，请引用我们的论文：

```bibtex
@article{naturalgaia2026,
  title={NaturalGAIA: A Verifiable Benchmark and Hierarchical Framework for Long-Horizon GUI Tasks},
  author={Anonymous Authors},
  journal={Under Review at ACL},
  year={2026}
}
```

## 📄 许可证

本项目采用 MIT License 授权。
