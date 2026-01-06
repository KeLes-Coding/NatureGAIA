import sys
import os
import time
from typing import Optional

# --- 路径设置 ---
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# --- 导入 ---
try:
    from Agent.task_decompose_agent import TaskDecomposer
    from Agent.task_execution_agent import TaskExecutionAgent
    from Agent.task_roader import TaskData, read_task_data_from_json
    from config_loader import ConfigLoader, create_legacy_config_module
except ImportError as e:
    print(f"错误：导入 Agent 模块失败：{e}")
    print("请确保您的项目结构正确，并检查 src/Agent 目录。")
    print(f"当前 Python 搜索路径: {sys.path}")
    exit(1)

# --- 加载配置 ---
try:
    config_loader = ConfigLoader()
except Exception as e:
    print(f"错误：加载配置文件失败：{e}")
    print("请确保项目根目录存在 config.yaml 文件")
    exit(1)


# --- 分解函数 (保持不变) ---
def run_decomposition(
    decomposer: TaskDecomposer, task: str, task_id: str
) -> Optional[str]:
    """运行任务分解并返回日志目录路径"""
    print(f"\n--- [阶段 1: 任务分解] ---")
    print(f"开始分解任务 (ID: {task_id})...")
    log_dir_path = decomposer.decompose(task, task_id)
    if log_dir_path:
        print(f"[分解成功] 日志目录已创建: {log_dir_path}")
    else:
        print("[分解失败] 未能生成任务分解结果。")
    return log_dir_path


# --- 主程序入口 ---
def main():
    """主执行函数，协调分解和执行"""
    print("=" * 50)
    print("--- 开始运行 Jarvis (Refactored V2) ---")
    print("=" * 50)

    # 从配置加载器获取配置
    td_config = config_loader.get_task_decomposer_config()
    te_config = config_loader.get_task_executor_config()
    av_config = config_loader.get_answer_validator_config()
    task_loader_config = config_loader.get_task_loader_config()

    # 1. 加载原始任务数据 (包含基准答案)
    json_path = task_loader_config.get("json_path", "task/0101.json")
    print(f"加载原始任务数据来源: {json_path}")
    original_task_data = read_task_data_from_json(json_path)
    if (
        not original_task_data
        or not original_task_data.Task
        or not original_task_data.Task_ID
    ):
        print("[运行失败] 未能从 JSON 文件加载有效的原始任务数据。")
        return

    initial_task_description = original_task_data.Task
    task_id_str = original_task_data.Task_ID
    print(f"原始任务加载成功: Task ID = {task_id_str}")

    # 2. 初始化并运行任务分解 Agent
    try:
        decomposer = TaskDecomposer(
            td_config.get("api_url", ""),
            td_config.get("api_key", ""),
            td_config.get("model", "qwen-vl-max"),
            td_config.get("proxy", "")
        )
    except AttributeError as e:
        print(f"错误：初始化 TaskDecomposer 失败，配置缺失：{e}")
        return
    # task_time = time.strftime("%Y%m%d-%H%M%S")
    # decomposer = f"{decomposer}/{task_time}"
    log_directory = run_decomposition(decomposer, initial_task_description, task_id_str)

    # 3. 如果分解成功，则初始化并运行任务执行 Agent 的主流程
    if log_directory:
        print(f"\n--- [阶段 2: 任务执行 (由 Agent 内部驱动)] ---")
        try:
            # << 修改：在初始化时传入 original_task_data >>
            executor = TaskExecutionAgent(
                api_url=te_config.get("api_url", ""),
                api_key=te_config.get("api_key", ""),
                original_task_data=original_task_data,  # 传递原始数据
                model=te_config.get("model", "qwen-vl-max"),
                proxy=te_config.get("proxy", ""),
                av_api_url=av_config.get("api_url", ""),
                av_api_key=av_config.get("api_key", ""),
                av_model=av_config.get("model", "deepseek-v3"),
            )
        except AttributeError as e:
            print(f"错误：初始化 TaskExecutionAgent 失败，配置缺失：{e}")
            return
        except ImportError as e:
            print(f"错误：初始化 TaskExecutionAgent 失败，导入依赖项出错：{e}")
            return
        except TypeError as e:
            print(
                f"错误：初始化 TaskExecutionAgent 失败，参数类型错误（可能是 original_task_data 无效）：{e}"
            )
            return

        # << 修改：调用 execute_task_flow 时不再传递 original_task_data >>
        execution_success = executor.execute_task_flow(log_directory)

        # --- 报告最终结果 ---
        print("\n" + "=" * 50)
        if execution_success:
            print("--- Jarvis 任务执行流程成功完成 ---")
            print(
                f"最终结果已保存至日志目录: '{log_directory}' (Task_Split_Final.json)"
            )
        else:
            print("--- Jarvis 任务执行流程失败或中止 ---")
            print(f"请检查日志目录 '{log_directory}' 中的详细日志和中间文件。")
        print("=" * 50)

    else:
        # 分解失败
        print("\n" + "=" * 50)
        print("--- Jarvis 任务分解失败，无法继续执行 ---")
        print("=" * 50)


if __name__ == "__main__":
    # 检查配置和文件存在性
    json_path = config_loader.get("lightmanus.task_loader.json_path", "task/0101.json")
    td_api_key = config_loader.get("lightmanus.task_decomposer.api_key", "")

    if not td_api_key:
        print("错误：API Key 未在 config.yaml 中配置 (lightmanus.task_decomposer.api_key)")
    elif not os.path.exists(json_path):
        print(f"错误：配置文件中指定的 JSON_PATH ('{json_path}') 不存在。")
    else:
        main()
