<div align="center">

# NaturalGAIA & LightManus

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Paper](https://img.shields.io/badge/Paper-ACL%202026-red.svg)](#)
[![Framework](https://img.shields.io/badge/Framework-Hierarchical%20Agent-blueviolet.svg)]()

![LightManus](static/main_v1_2512125-1.png)

> **NaturalGAIA: A Verifiable Benchmark for Long-Horizon GUI Tasks**
> 
> **LightManus: Dynamic Topological Planning & Hierarchical Collaborative Agent Framework**

[🚀 Quick Start](#-quick-start) • [📚 Documentation](#-project-structure) • [📊 Benchmarks](#-benchmarks) • [🌐 中文版](README_CN.md)

</div>

---

## 📖 Introduction

This project is the official implementation of the paper **"NaturalGAIA: A Verifiable Benchmark and Hierarchical Framework for Long-Horizon GUI Tasks"**. We address the fundamental challenge in GUI Agent domain where **High-fidelity Realism** and **Verifiable Evaluation Accuracy** are difficult to achieve simultaneously.

### Core Components

Our solution consists of two main parts:

#### 🌟 NaturalGAIA (Benchmark)

A verifiable evaluation dataset built on real human GUI interaction intentions. It simulates natural human intentions with cognitive nonlinearity and context dependency by decoupling logical causal paths from language narratives.

<div align="center">

![NaturalGAIA Dataset](static/BG-1.png)

*Figure 1: NaturalGAIA Dataset Construction Process*

</div>

#### ⚡ LightManus & Jarvis (Framework)

A hierarchical collaborative framework featuring:

- **LightManus**: Acts as the "brain", responsible for **Dynamic Topological Planning** and **Context Evolution Management**
- **Jarvis/Operation Agents**: Acts as the "hands", ensuring execution accuracy across Android, PC, and other platforms through **Hybrid Visual-Structural Perception**

The framework achieves **57.0%** on Weighted Pathway Success Rate (WPSR), significantly outperforming existing baselines.

---

## 🏗️ Architecture

The framework employs a layered design with code structure closely aligned with the paper's logic. The following diagram shows how LightManus acts as the brain for planning, and how Jarvis and other Agents act as hands for execution:

<div align="center">

![LightManus Architecture](static/main_v1_2512125-1.png)

*Figure 2: LightManus & Jarvis Hierarchical Collaborative Framework*

</div>

<details>
<summary>Click to view Architecture Flow</summary>

**Workflow:**

1. **User Input** → **LightManus (Task Decomposer)**
   - LightManus receives the user's natural language instruction
   - Decomposes complex tasks into atomic task sequences

2. **Task Executor Agent** → **Route Distribution**
   - Distributes atomic tasks to appropriate Operation Agents
   - Supports: Jarvis (Android), Mobile-Agent-E (Mobile Vision), PC-Agent (Windows/macOS)

3. **Operation Agents** → **Execution & Feedback**
   - Each agent executes its assigned tasks
   - Provides execution feedback back to the Task Executor

4. **Task Executor** → **Answer Validation Agent**
   - Collects final execution state
   - Performs dual-level verification (semantic + state-level)

5. **Evaluation Report**
   - Generates comprehensive benchmark results
</details>

### Core Components

#### Task Decomposer (LightManus)
- **Location**: `src/Agent/task_decompose_agent.py`
- **Function**: Decomposes complex natural language instructions into atomic tasks and handles dependencies between tasks

#### Operation Agents

**Jarvis**
- **Location**: `src/Agent/Operation_Agent/Jarvis`
- **Function**: ADB-based deep Android device control with View Hierarchy analysis

**Mobile-Agent-E**
- **Location**: `src/Agent/Operation_Agent/Mobile-Agent-E`
- **Function**: Pure vision language model-based mobile Agent for complex UI scenarios

**PC-Agent**
- **Location**: `src/Agent/Operation_Agent/PC-Agent`
- **Function**: Desktop automation for Windows and macOS

#### Answer Validator
- **Location**: `src/Agent/answer_validation_agent.py`
- **Function**: Uses LLM for dual-level verification (semantic and state-level) of task execution results, ensuring benchmark accuracy

---

## 🚀 Quick Start

### 1. Environment Setup

```bash
# Clone the repository
git clone https://anonymous.4open.science/r/NatureGAIA-721F/
cd NaturalGAIA

# Create and activate Conda environment (recommended)
conda create -n naturalgaia python=3.10
conda activate naturalgaia

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

The project uses `config.yaml` for unified management. To reset configuration from template:

```bash
# Optional: Reset configuration if needed
cp config.template.yaml config.yaml
```

Key configuration items in `config.yaml`:

```yaml
lightmanus:
  task_loader:
    json_path: "task/0101.json"  # Specify task file to execute

  # Task Decomposer (LightManus Core)
  task_decomposer:
    api_url: "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    api_key: "YOUR_API_KEY"      # Recommended: Qwen-VL-Max or similar high-performance model
    model: "qwen-vl-max"

  # Answer Validator
  answer_validator:
    model: "deepseek-v3"         # Verification module suggests using models with strong reasoning

# Agent-specific configuration
jarvis:
  enabled: true
  adb:
    executable_path: "adb"       # Ensure adb is in system environment variables
```

### 3. Dataset & Task Format

NaturalGAIA benchmark tasks are stored in the `task/` directory. Standard JSON format:

```json
{
  "Task": "Use Wikipedia to search for Jay Chou, check the album he released in 2000? Then tell me what tracks this album contains?",
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

> **Note**: The `final_answer` field contains the complete final answer, and the `atomic_tasks_answer` array contains expected answers for each atomic task.

### 4. Run Evaluation

Start the main program to launch the LightManus framework for inference and execution on specified tasks:

```bash
python run_light_manus.py
```

To run the complete benchmark suite:

```bash
# Run in benchmark mode (iterates through all tasks in task directory)
python run_light_manus.py --benchmark
```

---

## 📁 Project Structure

```
NaturalGAIA/
├── config.yaml                 # User configuration file
├── run_light_manus.py          # Program entry point
├── src/
│   ├── config_loader.py        # Configuration loading module
│   └── Agent/
│       ├── task_decompose_agent.py   # [LightManus] Task planning & decomposition
│       ├── task_execution_agent.py   # [Executor] Task scheduling & execution
│       ├── answer_validation_agent.py# [Validator] Result verification
│       └── Operation_Agent/          # Underlying operation Agent collection
│           ├── Jarvis/               # Android structured control
│           ├── Mobile-Agent-E/       # Android vision control
│           └── PC-Agent/             # Desktop control
└── task/                       # NaturalGAIA Benchmark dataset
```

---

## 📊 Benchmarks

We compared LightManus with other mainstream Agent frameworks on the NaturalGAIA dataset. The following are the main experimental results:

### Main Results Comparison

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

### Performance Efficiency Comparison

| Agent | Input Tokens | Output Tokens | Total Tokens | Average Steps | Duration (s) |
|-------|--------------|---------------|--------------|---------------|--------------|
| **Jarvis** | 16,904.8 | 2,276.2 | 19,181.0 | 6.9 | **84.1** |
| Mobile-Agent-e | 67,311.4 | 9,154.6 | 76,466.0 | 7.2 | 365.2 |

### Error Analysis

The following chart shows the proportion analysis of different modules in failure cases:

<div align="center">

![Error Analysis](static/EA-1.png)

*Figure 3: Error Analysis*

</div>

> **Note**: SR = Success Rate (P@1/4), WPSR = Weighted Pathway Success Rate, MAT/CR = Path Accuracy Rate, ATSR = Average Task Success Rate. Bold indicates best performance, underline indicates second-best performance. For detailed experimental settings and ablation study results, please refer to Section 5 of the paper.

---

## 🎯 Key Features

- ✅ **Dynamic Topological Planning**: Intelligent task decomposition and planning
- ✅ **Hierarchical Collaboration**: Separation of planning (brain) and execution (hands)
- ✅ **Multi-Platform Support**: Android, Windows, macOS
- ✅ **Verifiable Evaluation**: Dual-level verification for accuracy
- ✅ **High Performance**: 57.0% WPSR on NaturalGAIA benchmark
- ✅ **Efficient Token Usage**: 2.7x fewer tokens than baseline

---

## 🤝 Citation

If you use the NaturalGAIA dataset or LightManus framework in your research, please cite our paper:

```bibtex
@article{naturalgaia2026,
  title={NaturalGAIA: A Verifiable Benchmark and Hierarchical Framework for Long-Horizon GUI Tasks},
  author={Anonymous Authors},
  journal={Under Review at ACL},
  year={2026}
}
```

---

## 📄 License

This project is licensed under the MIT License.

---

<div align="center">

**[🌐 中文版本](README_CN.md)** | **[🚀 Quick Start](#-quick-start)** | **[📊 Benchmarks](#-benchmarks)** | **[🔬 Paper](#-citation)**

Made with ❤️ by the NaturalGAIA Team

</div>
