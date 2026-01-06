import json
import re
import time
import requests
import os
from typing import Dict, List, Optional  # 引入 Optional 用于类型提示
from collections import OrderedDict

import sys
import os

project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)  # 假设根目录在 Agent 上两级
sys.path.insert(0, project_root)

from src.Agent.task_roader import TaskData, read_task_data_from_json

# from .task_roader import TaskData, read_task_data_from_json
import config


# --- TaskData 类定义 ---
class TaskData:
    def __init__(
        self,
        task=None,
        task_id=None,
        level=None,
        atomic_tasks_number=None,
        atomic_tasks_answer=None,
        final_answer=None,
    ):
        self.Task = task
        self.Task_ID = task_id  # 对新路径至关重要
        self.level = level
        self.atomic_tasks_number = atomic_tasks_number
        self.atomic_tasks_answer = atomic_tasks_answer
        self.final_answer = final_answer

    def __repr__(self):
        return (
            f"TaskData(Task='{self.Task}', Task_ID='{self.Task_ID}', level={self.level}, "
            f"atomic_tasks_number={self.atomic_tasks_number}, "
            # 在 __repr__ 中避免打印可能很长的答案
            f"atomic_tasks_answer=..., "
            f"final_answer='{self.final_answer}')"
        )

    def get_answer_by_atomic_id(self, atomic_id):
        """根据atomic_tasks_ID获取对应的answer"""
        if self.atomic_tasks_answer:  # 检查列表是否存在
            for task in self.atomic_tasks_answer:
                if task.get("atomic_tasks_ID") == atomic_id:  # 使用 .get() 以确保安全
                    return task.get("answer")
        return None  # 如果没有找到匹配的ID或列表为空，返回None


def load_agent_list(file_path="agent_list.json"):
    """
    Reads the agent list from a JSON file.

    Args:
      file_path (str): The path to the JSON file.
                       Defaults to "agent_list.json".

    Returns:
      list: A list of agent dictionaries if the file is read successfully.
            Returns None if the file is not found or contains invalid JSON.
    """
    try:
        # Open the file in read mode with utf-8 encoding
        with open(file_path, "r", encoding="utf-8") as f:
            # Load the JSON data from the file
            agent_data = json.load(f)
            return agent_data
    except FileNotFoundError:
        # Handle the case where the file does not exist
        print(f"Error: File not found at {file_path}")
        return None
    except json.JSONDecodeError:
        # Handle the case where the file contains invalid JSON
        print(f"Error: Could not decode JSON from {file_path}")
        return None
    except Exception as e:
        # Handle any other potential errors during file reading or JSON parsing
        print(f"An unexpected error occurred: {e}")
        return None


# --- read_task_data_from_json 函数保持不变 ---
def read_task_data_from_json(file_path) -> Optional[TaskData]:  # 添加返回类型提示
    """
    从JSON文件中读取数据并返回TaskData对象

    :param file_path: JSON文件路径
    :return: TaskData对象 或 None（如果失败）
    """
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        return TaskData(
            task=data.get("Task"),
            task_id=data.get("Task_ID"),  # 确保 Task_ID 被读取
            level=data.get("level"),
            atomic_tasks_number=data.get("atomic_tasks_number"),
            atomic_tasks_answer=data.get("atomic_tasks_answer"),
            final_answer=data.get("final_answer"),
        )
    except FileNotFoundError:
        print(f"错误：在 {file_path} 未找到 JSON 文件")
        return None
    except json.JSONDecodeError:
        print(f"错误：无法从 {file_path} 解码 JSON")
        return None
    except Exception as e:  # 捕获其他可能的读取错误
        print(f"读取或解析文件 {file_path} 时发生错误: {e}")
        return None


# --- TaskDecomposer 类（包含修改） ---
class TaskDecomposer:
    def __init__(self, api_url, api_key: str, model: str = None, proxy: str = None):
        self.api_url = api_url
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "enable_thinking": "true",
        }
        self.model = (
            model if model else "default_model"
        )  # 确保 self.model 有值，用于路径
        self.proxy = proxy
        self.agent_list = load_agent_list()  # 加载 agent_list.json
        # 注意：这是一个发送给LLM的指令字符串，保持英文以确保LLM理解
        self.system_prompt = f"""You are an expert task decomposer and agent selector. Your ONLY output MUST be a valid JSON object.
Strictly follow these rules:
1. Analyze the user's request (provided below the agent list) to break it down into sequential, atomic sub-tasks.
2. For EACH atomic sub-task, analyze its requirements (e.g., needs web search, file access, specific tool, OS interaction).
3. Look CAREFULLY at the "Available Agents" list provided in the user message. This list contains the ONLY agents you can choose from.
4. For EACH atomic sub-task, select the SINGLE MOST SUITABLE agent from the "Available Agents" list based on the sub-task's requirements and the agent's capabilities (indicated by its name and device type).
5. The "atomic_tasks_agent" field in your output MUST EXACTLY MATCH one of the "Name" values from the "Available Agents" list.
6. The "atomic_tasks_device" field in your output MUST EXACTLY MATCH the "Device" value corresponding to the selected agent's name from the "Available Agents" list.
7. Required output format: Your entire response MUST conform strictly to the following JSON structure. Do NOT include ANY text before the opening '{' or after the closing '}'. Do NOT use markdown formatting like ```json.
8. The agent list is as follows:{self.agent_list}\n
"""
        self.system_prompt += """
{
    "Task": "Original task description provided by the user",
    "atomic_tasks": [
        {
            "atomic_tasks_ID": <auto-incrementing integer ID starting from 1>,
            "atomic_tasks_description": "Clear sub-task description including required tools/sources and objectives",
            "atomic_tasks_answer": "", // Leave empty
            "atomic_tasks_status": "pending", // Set to pending
            "atomic_tasks_agent": "<EXACT Name of the selected agent from the Available Agents list>",
            "atomic_tasks_device": "<EXACT Operating device of the selected agent from the Available Agents list>"
        }
        // ... more atomic tasks if needed
    ]
}

Example Scenario:
User message contains:
Available Agents:
- Name: mobile_agent_e, Device: android
- Name: pc_agent_win, Device: windows

Please decompose the following task: Find the author of 'Pride and Prejudice' and save the result to a file named 'author.txt' on the desktop.

Example Output JSON (MUST be EXACTLY this format, using names/devices from the list above):
{
    "Task": "Find the author of 'Pride and Prejudice' and save the result to a file named 'author.txt' on the desktop.",
    "atomic_tasks": [
        {
            "atomic_tasks_ID": 1,
            "atomic_tasks_description": "Search the web to find the author of the book 'Pride and Prejudice'.",
            "atomic_tasks_answer": "",
            "atomic_tasks_status": "pending",
            "atomic_tasks_agent": "pc_agent_win", // Selected from the list as capable of search on PC
            "atomic_tasks_device": "windows" // Corresponding device from the list
        },
        {
            "atomic_tasks_ID": 2,
            "atomic_tasks_description": "Save the author's name found in step 1 to a file named 'author.txt' on the desktop.",
            "atomic_tasks_answer": "",
            "atomic_tasks_status": "pending",
            "atomic_tasks_agent": "mobile_agent_e", // Selected from the list as best for file operations
            "atomic_tasks_device": "android" // Corresponding device from the list
        }
    ]
}

Output ONLY the JSON object. No introductory phrases, no explanations, no apologies, no markdown code fences."""

    def _generate_payload(self, user_input: str) -> Dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_input},
            ],
            "temperature": 0,
            # "max_tokens": 2000,
        }

    # --- 辅助方法: 从文本中提取JSON ---
    def _extract_json_from_text(self, raw_text: str) -> Optional[str]:
        """
        尝试从可能包含噪声的文本中提取JSON对象字符串。
        搜索第一个'{'和最后一个'}'来界定JSON块。
        处理常见的Markdown代码围栏 (```json ... ```)。

        :param raw_text: 可能包含JSON和其他文本的原始字符串。
        :return: 提取的JSON字符串，如果找不到合理的JSON块则返回None。
        """
        if not raw_text:
            print("提取警告：输入的原始文本为空。")
            return None

        # 对常见的Markdown代码围栏进行简单检查并移除
        # 使用 re.DOTALL 使 '.' 匹配换行符
        match = re.search(r"```json\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
        if match:
            print("信息：检测到并移除了 Markdown JSON 代码围栏。")
            raw_text = match.group(1)  # 直接获取括号内的内容
        else:
            # 如果没有 ```json ... ```，仍然尝试移除可能存在的 ```
            raw_text = raw_text.replace("```", "")

        raw_text = raw_text.strip()  # 移除处理后的首尾空白

        # 查找第一个左花括号
        first_brace = raw_text.find("{")
        if first_brace == -1:
            print("提取错误：在响应中未找到起始花括号 '{'。")
            return None

        # 查找最后一个右花括号
        last_brace = raw_text.rfind("}")
        if last_brace == -1:
            print("提取错误：在响应中未找到结束花括号 '}'。")
            return None

        if last_brace < first_brace:
            print("提取错误：结束花括号 '}' 出现在起始花括号 '{' 之前。")
            return None

        # 提取潜在的JSON字符串
        potential_json = raw_text[first_brace : last_brace + 1]

        print(f"信息：尝试解析提取出的JSON块...")
        # print(f"---\n{potential_json}\n---") # 取消注释以查看提取的具体内容
        return potential_json

    # 修改 decompose 方法以接受 task_id 并返回路径或 None
    def decompose(self, complex_task: str, task_id: str) -> Optional[str]:
        """
        调用LLM API分解复杂任务，进行健壮的JSON提取和处理，
        将结果保存到文件，并返回保存结果的目录路径。

        :param complex_task: 要分解的复杂任务描述 (str)
        :param task_id: 任务的唯一标识符 (str)，用于生成日志路径
        :return: 保存结果的目录路径 (str) 或 None (如果发生错误)
        """
        if not task_id:
            print("错误：任务ID (task_id) 不能为空，无法进行分解和保存。")
            return None
        if not complex_task:
            print("错误：任务描述 (complex_task) 不能为空。")
            return None

        print(f"开始分解任务 ID: {task_id} 使用模型: {self.model}")
        try:
            # 设置代理（如果提供了）
            proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
            if proxies:
                print(f"信息：使用代理: {self.proxy}")

            # 发送 POST 请求到 API
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=self._generate_payload(complex_task),
                # proxies=proxies,
                timeout=360,  # 设置请求超时时间（秒）
            )
            # 检查HTTP响应状态码，如果不是 2xx 则抛出异常
            response.raise_for_status()
            print(f"信息：API 请求成功，状态码: {response.status_code}")

            # --- 健壮的JSON提取和解析逻辑 ---
            raw_content = None
            potential_json_str = None
            result_data = None

            try:
                # 首先尝试按标准JSON结构解析整个响应体
                response_json = response.json()
                # 根据常见API格式，尝试获取核心内容
                # (这部分可能需要根据你使用的具体API响应结构调整)
                if (
                    "choices" in response_json
                    and isinstance(response_json["choices"], list)
                    and response_json["choices"]
                ):
                    message = response_json["choices"][0].get("message")
                    if message and isinstance(message, dict):
                        raw_content = message.get("content")
                # 如果上述结构不匹配，尝试直接从响应体获取 'content' 或类似字段
                if raw_content is None:
                    raw_content = response_json.get("content")  # 备选方案
                # 如果还是没有，可能整个响应就是内容
                if raw_content is None:
                    raw_content = response.text  # 最坏情况，使用全部原始文本

            except json.JSONDecodeError:
                # 如果整个响应体都不是有效的JSON，直接使用原始文本
                print("警告：API响应不是有效的JSON格式。将尝试从原始文本中提取。")
                raw_content = response.text

            if not raw_content:
                print("错误：未能从API响应中获取任何有效内容。")
                return None

            # 调用辅助方法尝试提取JSON块
            potential_json_str = self._extract_json_from_text(raw_content)

            if not potential_json_str:
                print("错误：未能从LLM响应内容中提取出潜在的JSON块。")
                print(
                    f"接收到的原始内容:\n---\n{raw_content}\n---"
                )  # 打印原始响应帮助调试
                return None

            # 尝试最终解析提取出的JSON字符串
            try:
                result_data = json.loads(
                    potential_json_str, object_pairs_hook=OrderedDict
                )  # 使用OrderedDict保持顺序
                print("信息：成功解析提取出的JSON块。")
            except json.JSONDecodeError as final_parse_error:
                print(f"错误：最终解析提取出的JSON块失败: {final_parse_error}")
                print(f"提取出的块是:\n---\n{potential_json_str}\n---")
                return None
            # --- JSON提取和解析逻辑结束 ---

            # --- 处理和标准化解析后的结果 ---
            if not isinstance(result_data, dict):
                print(f"错误：最终解析结果不是一个字典。类型: {type(result_data)}")
                print(f"解析的数据: {result_data}")
                return None

            # 确保关键字段存在，并进行必要的清理或修正
            if "atomic_tasks" not in result_data or not isinstance(
                result_data.get("atomic_tasks"), list
            ):
                print(
                    "警告：LLM响应中缺少 'atomic_tasks' 键或其值不是列表。将设置为空列表。"
                )
                result_data["atomic_tasks"] = []

            # 添加/确保结果字典中包含任务元数据
            result_data["Task_ID"] = task_id
            result_data["Task"] = result_data.get(
                "Task", complex_task
            )  # 如果LLM没返回Task，用原始输入
            if "final_answer" not in result_data:  # 确保有 final_answer 字段
                result_data["final_answer"] = ""
            result_data["atomic_tasks_numbers"] = len(
                result_data.get("atomic_tasks", [])
            )

            # 清理和标准化 atomic_tasks 列表中的每个任务
            valid_atomic_tasks = []
            expected_keys = {
                "atomic_tasks_ID",
                "atomic_tasks_description",
                "atomic_tasks_answer",
                "atomic_tasks_status",
                "atomic_tasks_agent",
                "atomic_tasks_device",
            }

            # Create a set of valid agent names for quick lookup during validation
            valid_agent_names = {
                agent.get("agent_name")
                for agent in self.agent_list
                if agent.get("agent_name")
            }
            # Create a mapping from agent name to device for validation
            agent_device_map = {
                agent.get("agent_name"): agent.get("operating_device")
                for agent in self.agent_list
                if agent.get("agent_name")
            }

            for i, task_item in enumerate(result_data.get("atomic_tasks", [])):
                if isinstance(task_item, dict):
                    # 确保包含所有预期的键，并设置默认值
                    if "atomic_tasks_ID" not in task_item:
                        task_item["atomic_tasks_ID"] = i + 1  # 如果缺失，尝试自动编号
                        print(f"警告: 原子任务 {i+1} 缺少 ID，已自动设置为 {i+1}。")
                    if "atomic_tasks_description" not in task_item:
                        task_item["atomic_tasks_description"] = ""
                        print(
                            f"警告: 原子任务 ID {task_item['atomic_tasks_ID']} 缺少描述。"
                        )
                    if "atomic_tasks_answer" not in task_item:
                        task_item["atomic_tasks_answer"] = ""
                    if "atomic_tasks_status" not in task_item:
                        task_item["atomic_tasks_status"] = "pending"

                    selected_agent = task_item.get("atomic_tasks_agent")
                    selected_device = task_item.get("atomic_tasks_device")

                    if not selected_agent or not isinstance(selected_agent, str):
                        task_item["atomic_tasks_agent"] = "Not Selected"
                        print(
                            f"Warning: Atomic task ID {task_item.get('atomic_tasks_ID')} missing or invalid agent selection. Set to 'Not Selected'."
                        )
                        selected_agent = (
                            "Not Selected"  # Update local var for device check
                        )

                    if not selected_device or not isinstance(selected_device, str):
                        task_item["atomic_tasks_device"] = "Unknown"
                        print(
                            f"Warning: Atomic task ID {task_item.get('atomic_tasks_ID')} missing or invalid device info. Set to 'Unknown'."
                        )
                        selected_device = "Unknown"  # Update local var

                    # **Strict Validation against agent_list**
                    if self.agent_list:  # Only validate if we have an agent list
                        if (
                            selected_agent != "Not Selected"
                            and selected_agent not in valid_agent_names
                        ):
                            print(
                                f"Validation ERROR: Agent '{selected_agent}' selected for task ID {task_item.get('atomic_tasks_ID')} is NOT in the provided agent list: {list(valid_agent_names)}. Correcting to 'Not Selected'."
                            )
                            task_item["atomic_tasks_agent"] = "Not Selected"
                            task_item["atomic_tasks_device"] = (
                                "Unknown"  # Reset device too if agent is invalid
                            )
                        elif selected_agent != "Not Selected":
                            # Agent name is valid, now check if the device matches
                            expected_device = agent_device_map.get(selected_agent)
                            if selected_device != expected_device:
                                print(
                                    f"Validation WARNING: Device '{selected_device}' for agent '{selected_agent}' (task ID {task_item.get('atomic_tasks_ID')}) does NOT match the expected device '{expected_device}' from the agent list. Keeping LLM provided value for now, but this might indicate an issue."
                                )
                                # Option: Force correction:
                                # print(f"Validation WARNING: ... Correcting device to '{expected_device}'.")
                                # task_item["atomic_tasks_device"] = expected_device
                    elif selected_agent == "Not Selected":
                        # If agent list was empty, ensure device is also marked Unknown
                        task_item["atomic_tasks_device"] = "Unknown"

                    # 可以选择只保留预期的键
                    # cleaned_task_item = {k: task_item.get(k) for k in expected_keys if k in task_item}
                    # valid_atomic_tasks.append(cleaned_task_item)
                    valid_atomic_tasks.append(task_item)  # 这里保留所有键

                else:
                    print(
                        f"警告：在 atomic_tasks 列表中发现索引 {i} 处的非字典项: {task_item}。已跳过。"
                    )

            # 使用清理和标准化后的列表更新结果
            result_data["atomic_tasks"] = valid_atomic_tasks
            result_data["atomic_tasks_numbers"] = len(
                valid_atomic_tasks
            )  # 更新原子任务数量

            # 为了保证输出JSON文件的字段顺序，再次使用OrderedDict构建最终结果
            final_ordered_result = OrderedDict(
                [
                    ("Task", result_data.get("Task")),
                    ("Task_ID", result_data["Task_ID"]),
                    ("atomic_tasks_numbers", result_data["atomic_tasks_numbers"]),
                    ("atomic_tasks", result_data.get("atomic_tasks", [])),
                    ("final_answer", result_data.get("final_answer")),
                ]
            )
            # --- 结果处理和标准化结束 ---

            # 可选：保存前再次验证最终结果的结构
            if not self._validate_output(final_ordered_result):
                print("错误：最终处理后的输出未能通过格式验证。结果将不会被保存。")
                return None  # 验证失败则不保存

            # 调用内部方法保存结果到文件
            save_directory_path = self._save_result(final_ordered_result, task_id)

            # 返回保存文件的目录路径
            return save_directory_path

        # --- 异常处理 ---
        except requests.exceptions.Timeout:
            print(f"错误：API 请求超时 ({self.api_url})。")
            return None
        except requests.exceptions.HTTPError as http_err:
            # 更具体地处理HTTP错误，例如打印状态码和响应体
            print(f"错误：API 请求返回 HTTP 错误: {http_err.response.status_code}")
            try:
                print(f"响应内容: {http_err.response.text}")
            except Exception:
                pass
            return None
        except requests.exceptions.RequestException as req_err:
            # 处理其他请求相关错误（如连接错误）
            print(f"错误：API 请求失败: {req_err}")
            return None
        except Exception as e:
            # 捕获所有其他在分解过程中可能发生的意外错误
            print(f"错误：在 decompose 方法中发生未预料的错误: {str(e)}")
            import traceback

            traceback.print_exc()  # 打印完整的错误堆栈信息，便于调试
            return None

    def _validate_output(self, output: Dict) -> bool:
        """验证输出字典是否符合预期格式"""
        required_keys = [
            "Task",
            "Task_ID",
            "atomic_tasks_numbers",
            "atomic_tasks",
            "final_answer",
        ]
        if not all(key in output for key in required_keys):
            print(
                f"验证错误：缺少顶层键。需要：{required_keys}, 找到：{list(output.keys())}"
            )
            return False
        if not isinstance(output["atomic_tasks"], list):
            print("验证错误：'atomic_tasks' 不是列表。")
            return False
        task_fields = [
            "atomic_tasks_ID",
            "atomic_tasks_description",
            "atomic_tasks_answer",
            "atomic_tasks_status",
            "atomic_tasks_agent",
            "atomic_tasks_device",
        ]
        for i, task in enumerate(output["atomic_tasks"]):
            if not isinstance(task, dict):
                print(f"验证错误：索引 {i} 处的 atomic_task 不是字典。")
                return False
            if not all(field in task for field in task_fields):
                print(
                    f"验证错误：索引 {i} 处的 atomic_task 缺少键。需要：{task_fields}, 找到：{list(task.keys())}"
                )
                return False
        return True

    # 修改 _save_result 以使用新的路径结构并返回路径或 None
    def _save_result(self, result: Dict, task_id: str) -> Optional[str]:
        """将结果字典保存到 Log/{模型名称}/{任务ID}/ 目录下的 JSON 文件中，并返回目录路径"""
        try:
            project_root = os.getcwd()  # 确定项目根目录
            safe_model_name = "".join(
                c for c in self.model if c.isalnum() or c in ("-", "_")
            )
            safe_task_id = "".join(
                c for c in str(task_id) if c.isalnum() or c in ("-", "_")
            )

            if not safe_model_name or not safe_task_id:
                raise ValueError(
                    f"无效的模型名称 ('{self.model}') 或任务 ID ('{task_id}') 用于创建目录。"
                )

            log_dir = os.path.join(project_root, "Log", safe_model_name, safe_task_id)
            task_time = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
            log_dir = os.path.join(log_dir, task_time)  # 添加时间戳到目录
            os.makedirs(log_dir, exist_ok=True)  # 创建目录
            output_file = os.path.join(log_dir, "Task_Split_Original.json")

            # 将 JSON 保存到文件
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=4)
            print(f"结果成功保存到：{output_file}")
            return log_dir  # 成功保存后返回目录路径

        except OSError as e:
            print(f"创建目录或写入文件时出错：{str(e)}")
            return None  # 保存失败返回 None
        except Exception as e:
            print(f"保存结果时出错：{str(e)}")
            return None  # 保存失败返回 None


# --- task_splitter 函数已修改，返回路径或 None ---
def task_splitter(taskdata: TaskData) -> Optional[str]:
    """
    分解来自 TaskData 的任务并保存结果。
    返回保存结果的目录路径，如果失败则返回 None。
    要求 taskdata 具有有效的 Task 和 Task_ID 属性。
    """
    if not taskdata or not isinstance(taskdata, TaskData):
        print("错误：提供了无效的 TaskData 对象。")
        return None

    if not taskdata.Task:
        print("错误：TaskData 中缺少任务描述。")
        return None

    if not taskdata.Task_ID:
        print("错误：TaskData 中缺少 Task_ID。无法将结果保存到特定路径。")
        return None

    # 初始化任务分解器
    decomposer = TaskDecomposer(
        config.TD_API_URL, config.TD_API_KEY, config.TD_MODEL, config.GlOBAL_PROXY
    )

    # 从 taskdata 获取任务和任务ID
    task = taskdata.Task
    task_id = taskdata.Task_ID

    print(f"开始分解任务 ID：{task_id} - '{task[:50]}...'")

    # 使用任务和任务ID调用 decompose，并获取返回的路径
    log_path = decomposer.decompose(task, task_id)

    if log_path:
        print(f"任务分解完成，日志目录：{log_path}")
    else:
        print(f"任务分解失败，任务 ID：{task_id}")

    return log_path  # 返回获取到的路径或 None


# --- 用法示例已修改 ---
if __name__ == "__main__":
    # 1. 直接使用 TaskDecomposer 的示例（用于测试）
    print("--- 直接测试 TaskDecomposer ---")
    # 首先确保 config.JSON_PATH 有效，以便加载任务数据
    if (
        hasattr(config, "JSON_PATH")
        and config.JSON_PATH
        and os.path.exists(config.JSON_PATH)
    ):
        task_data = read_task_data_from_json(config.JSON_PATH)
        if task_data and task_data.Task and task_data.Task_ID:
            complex_task = task_data.Task
            task_id = task_data.Task_ID

            decomposer = TaskDecomposer(
                config.TD_API_URL,
                config.TD_API_KEY,
                config.TD_MODEL,
                config.GlOBAL_PROXY,
            )
            # 使用任务和任务 ID 调用 decompose 并获取返回路径
            returned_path_direct = decomposer.decompose(complex_task, task_id)

            if returned_path_direct:
                print(f"==> Decompose 直接测试成功，日志目录: {returned_path_direct}")
            else:
                print(f"==> Decompose 直接测试失败。")
        else:
            print("错误：无法从 JSON 文件加载有效的任务或任务ID，无法进行直接测试。")
    else:
        print(
            f"错误：config.JSON_PATH ('{config.JSON_PATH}') 未定义或文件不存在，无法进行直接测试。"
        )

    # 2. 使用 task_splitter 并从 JSON 加载数据的示例
    print("\n--- 使用 task_splitter 和 JSON 进行测试 ---")
    try:
        # 确保 config.JSON_PATH 已定义并指向您的输入任务 JSON 文件
        if (
            hasattr(config, "JSON_PATH")
            and config.JSON_PATH
            and os.path.exists(config.JSON_PATH)
        ):
            task_data_from_file = read_task_data_from_json(config.JSON_PATH)
            if task_data_from_file:
                # 调用 task_splitter 并获取返回路径
                returned_path_splitter = task_splitter(task_data_from_file)
                if returned_path_splitter:
                    print(
                        f"==> Task splitter 测试成功，日志目录: {returned_path_splitter}"
                    )
                else:
                    print(f"==> Task splitter 测试失败。")
            else:
                print(f"无法从 {config.JSON_PATH} 加载 TaskData")
        else:
            print(
                f"config.JSON_PATH ('{config.JSON_PATH}') 未定义或文件不存在。跳过 task_splitter 示例。"
            )

    except Exception as e:
        print(f"运行 task_splitter 示例时发生错误：{e}")
    # agent_list = load_agent_list()
    # print(agent_list)
