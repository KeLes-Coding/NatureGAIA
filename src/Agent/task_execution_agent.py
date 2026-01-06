# -*- coding: utf-8 -*-
import json
import requests
import os
import re  # 导入 re 以便在 _extract_json_from_text 中使用
from typing import Dict, List, Optional

# 导入依赖项
try:
    # 假设 answer_validation_agent 在同一目录下
    from .answer_validation_agent import AnswerValidationAgent

    print("# 信息：AnswerValidationAgent 导入成功。")
except ImportError:
    AnswerValidationAgent = None  # 设置为 None 以便后续检查
    print("# 警告：无法导入 AnswerValidationAgent，验证功能将不可用。")

from .task_roader import TaskData
from .task_operator_agent import operator, get_answer_from_json


class TaskExecutionAgent:
    """
    封装任务执行流程的 Agent。
    负责按顺序执行分解后的原子任务，进行答案验证（如果可用），
    并根据前一个任务的结果更新后续任务的描述。
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        original_task_data: TaskData,  # 需要传入原始任务数据以获取基准答案
        model: str = None,
        proxy: str = None,
        av_api_url: str = None,
        av_api_key: str = None,
        av_model: str = None,
    ):
        """
        初始化 TaskExecutionAgent。

        :param api_url: LLM API 的 URL。
        :param api_key: API 访问密钥。
        :param original_task_data: 包含原始任务信息和基准答案的 TaskData 对象。
        :param model: 要使用的 LLM 模型名称。
        :param proxy: 代理服务器地址 (可选)。
        :raises ImportError: 如果 TaskData 未成功导入。
        :raises TypeError: 如果 original_task_data 不是有效的 TaskData 对象。
        """
        if not TaskData:
            # 这个检查确保 TaskData 类已成功导入
            raise ImportError(
                "TaskData 类未被成功导入，无法初始化 TaskExecutionAgent。"
            )
        if not isinstance(original_task_data, TaskData):
            raise TypeError(
                "初始化 TaskExecutionAgent 时，必须提供有效的 TaskData 对象给 original_task_data 参数。"
            )

        self.api_url = api_url
        self.headers = {
            "Content-Type": "application/json",  # 标准请求头
            "Authorization": f"Bearer {api_key}",  # API 认证
            "enable_thinking": "true",
        }
        self.model = model  # 使用的模型
        self.proxy = proxy  # 代理设置
        self.current_task_id = 1  # 当前待执行的任务ID，从1开始
        self.task_data = None  # 用于存储从文件加载的、分解后的任务结构 (字典)
        self.current_log_dir = None  # 当前任务执行的日志目录路径
        self.original_task_data: TaskData = original_task_data  # 保存原始任务数据引用

        self.validation_agent = None  # 初始化验证代理为 None
        self.av_api_url = av_api_url  # 验证代理的 API URL
        self.av_api_key = av_api_key  # 验证代理的 API 密钥
        self.av_model = av_model  # 验证代理的模型
        if AnswerValidationAgent:  # 检查 AnswerValidationAgent 是否成功导入
            try:
                # 尝试初始化验证代理
                self.validation_agent = AnswerValidationAgent(
                    api_url=av_api_url, api_key=av_api_key, model=av_model, proxy=proxy
                )
                print("# 信息：AnswerValidationAgent 初始化成功。")
            except Exception as e:
                # 如果初始化失败，打印错误但允许执行代理继续（验证功能将不可用）
                print(
                    f"# 警告：初始化 AnswerValidationAgent 时出错: {e}。验证功能将不可用。"
                )
        # else: # 如果导入时就失败了，这里会是 None

    # --- <<< 新增：独立的 JSON 提取辅助方法 >>> ---
    # 这个方法是为了处理可能返回 JSON 但格式不纯净的 LLM 响应而添加的，
    # 即使当前 TaskExecutionAgent 的主要 LLM 调用 (_generate_updated_description)
    # 预期的是纯文本，保留此方法以备将来扩展或用于其他可能调用。
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

    # --- <<< JSON 提取方法结束 >>> ---

    def execute_task_flow(self, log_directory_path: str) -> bool:
        """
        执行完整的原子任务处理流程。
        包括加载任务、循环执行、验证（如果可用）、更新状态和保存。

        :param log_directory_path: 包含 Task_Split_Original.json 的日志目录路径。
        :return: 如果所有任务成功执行（或在验证失败前完成），返回 True，否则返回 False。
        """
        print(f"\n--- [执行代理内部流程] ---")
        print(f"信息：开始执行任务流，使用的日志目录: {log_directory_path}")

        # 步骤 1: 加载分解后的初始任务结构
        if not self.load_initial_task(log_directory_path):
            print("[执行代理失败] 无法加载初始任务文件。请检查日志目录和文件。")
            return False  # 加载失败则无法继续

        # 步骤 2: 循环执行原子任务
        execution_successful = True  # 标记整体流程是否成功
        while self.has_more_tasks():  # 检查是否还有待执行的任务
            current_task = self.get_current_task()  # 获取当前任务字典
            if not current_task:
                # 通常不应发生，除非 task_data 结构损坏或 current_task_id 逻辑错误
                print(
                    f"# 错误：无法获取任务 ID {self.current_task_id} 的数据。流程中止。"
                )
                execution_successful = False
                break  # 退出循环

            try:
                # 获取任务ID（确保为整数）和描述
                task_id_int = int(current_task.get("atomic_tasks_ID"))
            except (ValueError, TypeError):
                print(
                    f"# 错误：在任务数据中发现无效的任务 ID: {current_task.get('atomic_tasks_ID')}。流程中止。"
                )
                execution_successful = False
                break  # 退出循环

            user_question = current_task.get(
                "atomic_tasks_description", "# 错误：未找到任务描述"
            )

            current_agent = current_task.get("atomic_tasks_agent")

            print(f"\n>>> 当前待执行任务 ID: {task_id_int} <<<")
            print(f"任务描述: {user_question}")

            # 步骤 2a: 获取用户执行结果 (这里是手动输入，未来可替换为工具调用等)
            # TODO: 将这里的 input 替换为实际的工具调用或函数执行
            # 根据任务配置选择使用的 Agent
            # 可以从 current_task 中读取 atomic_tasks_agent 字段，如果没有则使用默认值
            agent_type = current_task.get("atomic_tasks_agent", "mobile_agent_e")

            operator(
                agent_type,  # 使用配置的 agent 类型
                log_directory_path,
                task_id_int,
                "individual",
                user_question,
                task_id_int,
            )
            user_answer = get_answer_from_json(
                f"{log_directory_path}/{task_id_int}/task_answer.json"
            )

            if user_answer is None:
                print(
                    f"# 错误: 未能从 '{log_directory_path}/{task_id_int}/task_answer.json' 获取任务 {task_id_int} 的答案。"
                )
                print(
                    "# 可能原因：Operator 未生成文件、文件 JSON 格式错误或缺少 'answer' 键。"
                )
                print("# 执行流程中止。")
                execution_successful = False  # 标记整体执行失败
                break  # 退出 while 循环

            # user_answer = input(
            #     f"请输入任务 {task_id_int} 的执行结果 (或输入 'exit' 退出): "
            # )
            print(f"任务{task_id_int}的执行结果为：{user_answer}")

            # 步骤 2b: 执行答案验证（如果验证代理可用且找到基准答案）
            validation_result = self._perform_validation(
                task_id_int, user_question, user_answer
            )  # validation_result 是字典或 None

            # 步骤 2c: 更新任务状态，保存中间结果，并根据验证结果决定是否继续
            # update_task_status_and_proceed 会处理状态更新、保存和决定是否前进
            should_continue = self.update_task_status_and_proceed(
                user_answer, validation_result
            )

            if not should_continue:
                # 如果 update_task_status_and_proceed 返回 False，表示流程应停止
                # 这可能是因为验证失败，或者是最后一个任务已完成
                if not self.has_more_tasks():  # 检查是否是因为完成了最后一个任务
                    # 如果 current_task_id 已超出任务总数，说明是正常完成
                    print(f"# 信息：任务 {task_id_int} 是最后一个任务，流程正常结束。")
                    # execution_successful 保持 True (因为是正常完成)
                else:  # 如果还有任务，但流程停止，说明是验证失败或用户退出等异常情况
                    print(f"# 信息：在处理任务 {task_id_int} 后，执行流程停止。")
                    execution_successful = False  # 标记为未完全成功
                break  # 退出循环

        # 步骤 3: 循环结束后进行总结
        print("\n--- 任务执行循环结束 ---")
        if execution_successful and not self.has_more_tasks():
            # 只有当标记为成功 *且* 确实没有更多任务时，才算完全成功
            print("[执行代理成功] 所有原子任务已成功处理完成。")
            # 最终文件应该已在 update_task_status_and_proceed 中最后一个任务完成时保存
            return True
        else:
            # 如果是中途退出或验证失败导致停止
            print("[执行代理失败或中止] 任务流程未完全成功执行。")
            if self.task_data and self.current_log_dir:
                # 尝试保存一个最终的、可能不完整的状态文件
                print("# 尝试保存当前（可能未完成的）最终状态...")
                self._save_final_file()  # 尝试保存最后状态
            return False

    def _perform_validation(
        self, task_id: int, question: str, answer: str
    ) -> Optional[Dict]:
        """
        内部辅助方法：获取当前任务的基准答案，并调用验证代理进行验证。

        :param task_id: 当前原子任务的 ID。
        :param question: 当前原子任务的描述。
        :param answer: 用户或工具对当前任务给出的答案。
        :return: 验证结果字典 (包含 'status': bool, 'description': str) 或 None (如果无法验证)。
        """
        if not self.validation_agent:
            # print(f"# 调试：验证代理 (self.validation_agent) 未初始化或不可用，跳过任务 {task_id} 的验证。") # 可选调试信息
            return None  # 返回 None 表示跳过验证

        if not self.original_task_data:
            print(
                f"# 错误：原始任务数据 (self.original_task_data) 未设置，无法获取任务 {task_id} 的基准答案进行验证。"
            )
            return {
                "status": None,
                "description": "无法获取基准答案 (原始数据丢失)",
            }  # 返回特殊状态

        # 从 original_task_data 中获取对应 task_id 的基准答案
        ground_truth = self.original_task_data.get_answer_by_atomic_id(task_id)

        if ground_truth is not None:
            # 如果找到了基准答案
            print(f"# 信息：找到任务 {task_id} 的基准答案，准备调用验证代理...")
            # print(f"#   基准答案: {str(ground_truth)[:100]}...") # 可选调试信息
            try:
                # 调用验证代理的 validate_answers 方法
                validation_result = self.validation_agent.validate_answers(
                    task_id, question, answer, ground_truth
                )
                print(f"# 验证结果 (任务 {task_id}): {validation_result}")
                return validation_result  # 返回验证结果字典
            except Exception as val_err:
                # 如果调用验证代理时发生异常
                print(f"# 错误：调用验证代理对任务 {task_id} 进行验证时出错: {val_err}")
                # 返回一个表示验证失败的字典
                return {
                    "status": False,
                    "description": f"调用验证代理时发生错误: {val_err}",
                }
        else:
            # 如果在原始数据中没有找到对应 task_id 的基准答案
            print(
                f"# 警告：未在原始任务数据中找到任务 {task_id} 的基准答案，跳过验证。"
            )
            # 返回 None 表示跳过验证
            return None

    def load_initial_task(
        self, log_directory_path: str, input_file: str = "Task_Split_Original.json"
    ) -> bool:
        """
        从指定的日志目录加载由 TaskDecomposer 生成的初始任务文件。

        :param log_directory_path: 包含任务文件的日志目录路径。
        :param input_file: 要加载的任务文件名 (默认为 "Task_Split_Original.json")。
        :return: 如果加载和基本验证成功，返回 True，否则返回 False。
        """
        if not os.path.isdir(log_directory_path):
            print(f"# 错误：提供的日志目录路径无效或不存在: {log_directory_path}")
            return False
        # 再次检查依赖的 original_task_data 是否存在
        if not self.original_task_data:
            print("# 错误：内部状态错误，原始 TaskData 未初始化，无法继续加载。")
            return False

        self.current_log_dir = log_directory_path  # 保存当前日志目录
        input_path = os.path.join(self.current_log_dir, input_file)  # 构建完整文件路径
        print(f"# 信息：尝试从 {input_path} 加载分解后的任务结构...")

        try:
            with open(input_path, "r", encoding="utf-8") as f:
                # 加载 JSON 数据
                self.task_data = json.load(f)

            # 基本结构验证：检查 'atomic_tasks' 是否是列表且不为空
            if not isinstance(self.task_data.get("atomic_tasks"), list):
                print(
                    f"# 错误：加载的任务文件 {input_path} 缺少 'atomic_tasks' 列表或格式错误。"
                )
                self._reset_state_on_load_fail()  # 重置状态
                return False
            # 可以选择性地检查列表是否为空，取决于业务逻辑是否允许空任务列表
            # if not self.task_data.get("atomic_tasks"):
            #     print(f"# 警告：加载的任务文件 {input_path} 的 'atomic_tasks' 列表为空。")
            # return False # 如果不允许空列表，则返回 False

            # 确保每个原子任务都有 answer 和 status 字段，赋予默认值
            for task in self.task_data.get("atomic_tasks", []):
                if isinstance(task, dict):  # 确保是字典
                    if "atomic_tasks_answer" not in task:
                        task["atomic_tasks_answer"] = ""  # 默认空字符串
                    if "atomic_tasks_status" not in task:
                        task["atomic_tasks_status"] = "pending"  # 默认挂起状态
                else:
                    print(
                        f"# 警告：在 {input_path} 的 atomic_tasks 中发现非字典项，已忽略：{task}"
                    )

            self.current_task_id = 1  # 重置当前任务ID计数器
            print(f"# 信息：成功从 {input_path} 加载并初始化任务结构。")
            # print(f"#   任务总数: {len(self.task_data.get('atomic_tasks', []))}") # 可选调试
            return True
        except FileNotFoundError:
            print(f"# 错误：任务文件未找到: {input_path}")
            self._reset_state_on_load_fail()
            return False
        except json.JSONDecodeError as json_err:
            print(f"# 错误：解析任务文件 {input_path} 时发生 JSON 解码错误: {json_err}")
            self._reset_state_on_load_fail()
            return False
        except Exception as e:
            # 捕获其他可能的错误，如权限问题
            print(f"# 错误：加载任务文件 {input_path} 时发生未知错误: {e}")
            self._reset_state_on_load_fail()
            return False

    def _reset_state_on_load_fail(self):
        """内部方法：在加载任务文件失败时重置相关状态。"""
        print("# 信息：重置与加载相关的内部状态。")
        self.task_data = None  # 清空任务数据
        self.current_log_dir = None  # 清空日志目录
        self.current_task_id = 1  # 重置任务ID

    def get_current_task(self) -> Optional[Dict]:
        """
        根据 self.current_task_id 从 self.task_data 中获取当前待执行的任务字典。

        :return: 当前任务的字典 或 None (如果找不到或 task_data 无效)。
        """
        if not self.task_data or not isinstance(
            self.task_data.get("atomic_tasks"), list
        ):
            # print("# 调试：get_current_task: task_data 无效或 atomic_tasks 不是列表。") # 可选调试
            return None  # 没有有效数据则返回 None

        # 遍历任务列表查找匹配 ID 的任务
        for task in self.task_data.get("atomic_tasks", []):
            try:
                # 尝试将任务字典中的 ID 和当前 ID 都转为整数进行比较
                if (
                    isinstance(task, dict)
                    and int(task.get("atomic_tasks_ID")) == self.current_task_id
                ):
                    return task  # 找到匹配的任务，返回其字典
            except (ValueError, TypeError, AttributeError):
                # 如果 ID 转换失败或 task 不是字典，则忽略此项，继续查找
                # print(f"# 调试：get_current_task: 跳过无效任务项 {task}") # 可选调试
                continue
        # 如果循环结束仍未找到匹配的任务
        # print(f"# 调试：get_current_task: 未找到 ID 为 {self.current_task_id} 的任务。") # 可选调试
        return None  # 未找到则返回 None

    def update_task_status_and_proceed(
        self, user_answer: str, validation_result: Optional[Dict]
    ) -> bool:
        """
        核心逻辑：更新当前任务的答案和状态，保存中间文件，
        如果验证通过或跳过，则尝试更新下一个任务的描述，并决定是否继续执行流程。

        :param user_answer: 当前任务的用户/工具执行结果。
        :param validation_result: _perform_validation 返回的验证结果字典或 None。
        :return: 如果流程应该继续执行下一个任务，返回 True，否则返回 False。
        """
        if not self.task_data or not self.current_log_dir:
            print(
                "# 错误：update_task_status_and_proceed: 任务数据或日志目录未初始化。"
            )
            return False  # 状态无效，无法继续

        task_updated = False
        current_task_id_local = self.current_task_id  # 获取当前任务ID
        next_task_exists = False  # 标记是否存在下一个任务

        # 步骤 1: 查找当前任务并更新其答案和状态
        for i, task in enumerate(self.task_data.get("atomic_tasks", [])):
            try:
                if (
                    isinstance(task, dict)
                    and int(task.get("atomic_tasks_ID")) == current_task_id_local
                ):
                    # 找到了当前任务
                    task["atomic_tasks_answer"] = user_answer  # 更新答案

                    # 更新状态，将验证结果或跳过信息存入
                    if validation_result is not None:
                        # 如果有验证结果，直接存入
                        task["atomic_tasks_status"] = validation_result
                    else:
                        # 如果 validation_result 是 None (表示跳过)
                        task["atomic_tasks_status"] = {
                            "status": None,
                            "description": "Validation skipped or no ground truth",
                        }
                    task_updated = True  # 标记已更新
                    print(
                        f"# 信息：任务 {current_task_id_local} 的答案和状态已在内存中更新。"
                    )
                    # 检查是否存在下一个任务 (索引 i+1 是否在列表范围内)
                    if i + 1 < len(self.task_data.get("atomic_tasks", [])):
                        next_task_exists = True
                    break  # 找到并更新后即可退出循环
            except (ValueError, TypeError, AttributeError):
                continue  # 跳过无效的任务项

        if not task_updated:
            print(
                f"# 错误：无法在任务数据中找到 ID 为 {current_task_id_local} 的任务以进行更新。"
            )
            return False  # 更新失败则停止流程

        # 步骤 2: 判断验证是否通过或被跳过
        validation_status = None
        if isinstance(validation_result, dict):
            validation_status = validation_result.get("status")  # 获取 status 字段

        validation_passed = validation_status is True
        validation_skipped = validation_status is None  # None 明确表示跳过或无基准

        # 步骤 3: 根据验证结果决定后续操作
        if validation_passed or validation_skipped:
            # 如果验证通过或跳过验证
            status_msg = "验证通过" if validation_passed else "验证跳过"
            print(f"# 信息：任务 {current_task_id_local} 状态判定: {status_msg}。")
            output_suffix = "" if validation_passed else "_Unvalidated"  # 文件名后缀

            # 步骤 3a: 尝试更新下一个任务的描述 (如果存在下一个任务)
            if next_task_exists:
                print(
                    f"# 信息：尝试基于任务 {current_task_id_local} 的答案更新下一个任务 (ID: {current_task_id_local + 1}) 的描述..."
                )
                self._update_next_task_description()  # 调用更新函数
            # else:
            # print(f"# 信息：任务 {current_task_id_local} 是最后一个任务，无需更新后续描述。") # 可选调试

            # 步骤 3b: 保存当前任务完成后的中间状态文件
            output_file = f"Task_Split_{current_task_id_local}{output_suffix}.json"
            if not self._save_task_data(output_file):
                print(f"# 错误：保存中间状态文件 {output_file} 失败。流程中止。")
                return False  # 保存失败则停止
            print(
                f"# 信息：任务 {current_task_id_local} 完成后的状态已保存到: {output_file}"
            )

            # 步骤 3c: 决定是继续还是结束
            if next_task_exists:
                # 如果存在下一个任务，增加 current_task_id 并返回 True 继续循环
                self.current_task_id += 1
                print(f"# 信息：准备执行下一个任务 ID: {self.current_task_id}")
                return True  # 继续执行流程
            else:
                # 如果这是最后一个任务，标记完成，保存最终文件，并返回 False 停止循环
                print("# 信息：当前是最后一个原子任务，流程即将结束。")
                self.current_task_id += 1  # 增加 ID 以便 has_more_tasks() 返回 False
                self._save_final_file()  # 保存最终的 Task_Split_Final.json
                return False  # 正常结束，停止循环

        else:  # 如果验证失败 (validation_status is False)
            fail_desc = validation_result.get("description", "# 验证失败，无详细描述")
            print(
                f"# 错误：任务 {current_task_id_local} 验证失败: {fail_desc}。流程中止。"
            )
            # 保存标记为失败的状态文件
            output_file = f"Task_Split_{current_task_id_local}_Failed.json"
            self._save_task_data(output_file)  # 尝试保存失败状态
            return False  # 验证失败，停止循环

    # *** 更新下一个任务描述的逻辑 ***
    def _update_next_task_description(self):
        """
        (内部方法) 根据【当前已完成】任务的答案，尝试调用 LLM 更新【下一个待执行】任务的描述。
        仅在找到当前任务答案和下一个任务，并且 LLM 成功生成了不同的描述时才更新。
        """
        if not self.task_data or not self.model:
            # print("# 调试: _update_next_task_description: task_data 或 model 未设置。") # 可选调试
            return  # 基本检查，无法更新

        current_task_answer = None
        next_task_dict = None  # 指向下一个任务字典的引用
        next_task_id_to_find = self.current_task_id + 1  # 要查找的下一个任务的ID

        # 在任务列表中查找当前任务的答案和下一个任务的字典引用
        atomic_tasks = self.task_data.get("atomic_tasks", [])
        for i, task in enumerate(atomic_tasks):
            try:
                if isinstance(task, dict):
                    task_id = int(task.get("atomic_tasks_ID"))
                    # 找到当前任务 (ID 为 self.current_task_id)，获取其答案
                    if task_id == self.current_task_id:
                        current_task_answer = task.get("atomic_tasks_answer")
                        # print(f"# 调试: 找到当前任务 {task_id} 的答案: {str(current_task_answer)[:50]}...") # 可选调试

                    # 找到下一个任务 (ID 为 next_task_id_to_find)，获取其字典引用
                    elif task_id == next_task_id_to_find:
                        next_task_dict = (
                            task  # 获取字典引用，后续修改会直接作用于 self.task_data
                        )
                        # print(f"# 调试: 找到下一个任务 {task_id} 的字典引用。") # 可选调试

            except (ValueError, TypeError, AttributeError):
                continue  # 跳过无效的任务项

        # 如果未能找到当前任务的答案 或 未能找到下一个任务的字典，则无法进行更新
        if current_task_answer is None:
            print(
                f"# 警告：未能找到当前任务 (ID: {self.current_task_id}) 的答案，无法用于更新下一个任务的描述。"
            )
            return
        if next_task_dict is None:
            # print(f"# 信息：未找到需要更新描述的下一个任务 (ID: {next_task_id_to_find})。可能是最后一个任务。") # 可选调试
            return

        # 获取下一个任务的原始描述
        original_description = next_task_dict.get("atomic_tasks_description", "")
        if not original_description:
            print(
                f"# 警告：下一个任务 (ID: {next_task_id_to_find}) 没有原始描述，无法进行更新。"
            )
            return  # 没有原始描述无法更新

        # 调用 LLM 生成更新后的描述，只传入上一个任务的答案
        print(f"# 信息：正在调用 LLM 为任务 {next_task_id_to_find} 生成更新后的描述...")
        updated_description = self._generate_updated_description(
            original_description, current_task_answer  # 传递原始描述和上一个答案
        )

        # 检查生成的描述是否有效(非None)且与原始描述不同
        if (
            updated_description is not None
            and updated_description != original_description
        ):
            print(f"# 信息：任务 {next_task_id_to_find} 的描述已成功更新。")
            # print(f"#   旧描述: {original_description}") # 可选调试
            # print(f"#   新描述: {updated_description}") # 可选调试
            # 直接修改字典引用，这将更新 self.task_data 中的内容
            next_task_dict["atomic_tasks_description"] = updated_description
        else:
            # 处理生成失败或描述未改变的情况
            if updated_description is None:
                print(
                    f"# 警告：为任务 {next_task_id_to_find} 生成更新描述时失败或LLM返回空内容。描述未更新。"
                )
            else:  # updated_description == original_description
                # print(f"# 信息：为任务 {next_task_id_to_find} 生成的描述与原始描述相同。描述未更新。") # 可选调试
                pass  # 描述未变化，无需操作

    # *** 生成更新描述的方法（包含修改后的英文 Prompt）***
    def _generate_updated_description(
        self, original_description: str, previous_answer: str
    ) -> Optional[str]:
        """
        (内部方法) 调用 LLM API，根据上一个任务的答案生成当前任务的更新描述。

        :param original_description: 当前任务的原始描述。
        :param previous_answer: 上一个已完成任务的答案。
        :return: 更新后的任务描述字符串，如果生成失败或API出错则返回 None。
        """
        # --- <<< Prompt in English and Stricter >>> ---
        prompt = f"""Based on the answer from the *immediately preceding* task, please refine the following task description for the *upcoming* task.
Focus on incorporating relevant details or context from the previous answer to make the upcoming task description clearer or more specific, while maintaining its original core objective.

Previous Task's Answer:
{previous_answer}

Original Description for Upcoming Task:
{original_description}

Your goal is to return ONLY the refined task description for the upcoming task.
Do NOT include explanations, introductions, apologies, or any text other than the updated description itself.
For example, if the original description was "Analyze the results" and the previous answer was "Found 3 relevant documents", a good refined description might be "Analyze the 3 relevant documents found". Just return this text.
"""
        # --- <<< End of Prompt >>> ---

        if not self.model:
            print(
                "# 警告：_generate_updated_description: 未配置模型名称，无法调用 API。"
            )
            return None  # 返回 None 表示失败

        try:
            # 准备 API 请求的 payload
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,  # 较低的温度使输出更稳定
                # "max_tokens": 500,  # 限制输出长度，根据需要调整
                # # "stop": ["\n"] # 可以考虑添加停止符，如果 LLM 倾向于添加额外换行
            }
            # 设置代理
            proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None

            # 发送请求
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                # proxies=proxies,
                timeout=360,  # 设置超时
            )
            response.raise_for_status()  # 检查 HTTP 错误

            # --- 尝试从响应中提取干净的文本 ---
            response_text = None
            try:
                # 优先尝试解析 JSON 并获取 content
                response_data = response.json()
                if (
                    "choices" in response_data
                    and isinstance(response_data["choices"], list)
                    and response_data["choices"]
                ):
                    message = response_data["choices"][0].get("message", {})
                    if isinstance(message, dict):
                        response_text = message.get("content")
                # 如果上述结构不匹配，尝试其他可能的字段或直接使用文本
                if response_text is None:
                    # 尝试 .text (作为备选，如果 API 直接返回文本)
                    if response.text:
                        response_text = response.text

            except json.JSONDecodeError:
                # 如果响应不是 JSON，直接使用原始文本
                print(
                    "# 警告：_generate_updated_description: API 响应不是 JSON，将使用原始文本。"
                )
                response_text = response.text
            except Exception as parse_err:
                print(
                    f"# 警告：_generate_updated_description: 解析 API 响应时出错: {parse_err}。将尝试使用原始文本。"
                )
                response_text = response.text  # 出错时也尝试使用原始文本

            # --- 清理提取到的文本 ---
            if response_text:
                # 进行清理，移除首尾空白
                cleaned_text = response_text.strip()
                # 可选：添加更复杂的清理逻辑，如移除特定前缀/后缀
                # if cleaned_text.startswith("Updated description:"):
                #     cleaned_text = cleaned_text[len("Updated description:"):].strip()
                if cleaned_text:  # 确保清理后仍有内容
                    # print(f"# 调试: LLM 返回的更新描述: {cleaned_text}") # 可选调试
                    return cleaned_text
                else:
                    print(
                        "# 警告：_generate_updated_description: LLM 返回的响应内容为空或只有空白。"
                    )
                    return None  # 返回 None 表示生成失败
            else:
                print(
                    "# 错误：_generate_updated_description: 未能从 API 响应中获取任何文本内容。"
                )
                return None  # 返回 None 表示生成失败

        except requests.exceptions.Timeout:
            print(
                f"# 错误：_generate_updated_description: API 请求超时 ({self.api_url})。"
            )
            return None  # 返回 None 表示生成失败
        except requests.exceptions.HTTPError as http_err:
            print(
                f"# 错误：_generate_updated_description: API 请求返回 HTTP 错误: {http_err.response.status_code}"
            )
            try:
                print(
                    f"#   响应体: {http_err.response.text[:200]}..."
                )  # 打印部分响应体帮助调试
            except Exception:
                pass
            return None  # 返回 None 表示生成失败
        except Exception as e:
            # 捕获其他所有错误
            print(
                f"# 错误：_generate_updated_description: 生成更新描述时发生未知错误: {str(e)}"
            )
            return None  # 返回 None 表示生成失败

    def _save_task_data(self, filename: str) -> bool:
        """
        (内部方法) 将当前的 self.task_data 字典保存到指定的文件名。

        :param filename: 要保存在 self.current_log_dir 中的文件名。
        :return: 保存成功返回 True，失败返回 False。
        """
        if not self.task_data or not self.current_log_dir:
            print("# 错误：_save_task_data: 任务数据或日志目录未设置，无法保存。")
            return False

        output_path = os.path.join(self.current_log_dir, filename)  # 构建完整路径
        try:
            # 确保 final_answer 键存在于要保存的数据中 (即使为空)
            if "final_answer" not in self.task_data:
                self.task_data["final_answer"] = ""  # 如果没有则添加空字符串

            # 写入 JSON 文件
            with open(output_path, "w", encoding="utf-8") as f:
                # 使用 indent=2 进行缩进，方便阅读；ensure_ascii=False 支持中文
                json.dump(self.task_data, f, ensure_ascii=False, indent=2)
            # print(f"# 信息：任务数据已保存到: {output_path}") # 可选的状态输出
            return True
        except Exception as e:
            # 捕获写入文件时可能发生的错误
            print(f"# 错误：保存任务数据到 {output_path} 时失败: {e}")
            return False

    def _save_final_file(self) -> bool:
        """
        (内部方法) 在所有任务处理完毕（或流程中止）时，
        根据最后一个成功处理（验证通过或跳过）的任务的答案，
        更新 self.task_data 中的 'final_answer' 字段，并保存为 Task_Split_Final.json。
        """
        if not self.task_data or not self.current_log_dir:
            print(
                "# 错误：_save_final_file: 任务数据或日志目录未设置，无法保存最终文件。"
            )
            return False

        # 获取原子任务列表，如果不存在则设为空列表
        atomic_tasks = self.task_data.get("atomic_tasks", [])
        if not atomic_tasks:
            print(
                "# 警告：_save_final_file: 任务数据中没有原子任务，最终答案将设置为空。"
            )
            self.task_data["final_answer"] = ""  # 没有任务则最终答案为空
            output_file = "Task_Split_Final.json"
            return self._save_task_data(output_file)  # 尝试保存

        # 确定最后一个应该被视为“成功”处理的任务的 ID
        # self.current_task_id 在上一步结束后会指向下一个任务或超出范围
        last_processed_id = self.current_task_id - 1
        final_answer = f"# 错误: 未找到 ID 为 {last_processed_id} 的已处理任务的有效结果。"  # 默认错误信息

        # 从后往前查找最后一个 ID 匹配且状态为“通过”或“跳过”的任务
        last_task_found_and_ok = False
        if last_processed_id >= 1:  # 确保至少有一个任务被尝试处理
            for task in reversed(atomic_tasks):  # 从最后一个任务开始往前找
                try:
                    if isinstance(task, dict):
                        task_id = int(task.get("atomic_tasks_ID"))
                        if task_id == last_processed_id:  # 找到了对应 ID 的任务
                            task_status_dict = task.get("atomic_tasks_status")
                            task_answer = task.get(
                                "atomic_tasks_answer", "# 错误：答案丢失"
                            )

                            # 检查状态是否表示成功或跳过
                            status_is_ok = (
                                isinstance(task_status_dict, dict)
                                and task_status_dict.get("status") is True
                            )
                            status_is_skipped = (
                                isinstance(task_status_dict, dict)
                                and task_status_dict.get("status") is None
                            )

                            if status_is_ok or status_is_skipped:
                                # 如果状态是成功或跳过，使用这个任务的答案作为最终答案
                                final_answer = task_answer
                                last_task_found_and_ok = True
                                print(
                                    f"# 信息：使用任务 {last_processed_id} 的答案作为最终答案 (状态: {'通过' if status_is_ok else '跳过'})。"
                                )
                            else:  # 如果状态是 False (验证失败)
                                fail_desc = (
                                    task_status_dict.get("description", "验证失败")
                                    if isinstance(task_status_dict, dict)
                                    else "验证失败"
                                )
                                final_answer = (
                                    f"# 任务 {last_processed_id} 验证失败: {fail_desc}"
                                )
                                print(
                                    f"# 警告：最后一个处理的任务 {last_processed_id} 验证失败，最终答案将反映此情况。"
                                )
                            break  # 找到了最后一个处理的任务，停止查找
                except (ValueError, TypeError, AttributeError):
                    continue  # 跳过无效的任务项
        else:  # 如果 last_processed_id < 1，说明第一个任务都没开始处理
            final_answer = "# 没有任何任务被成功处理。"
            print("# 警告：没有任何任务被处理，最终答案将反映此情况。")

        # 更新 task_data 中的 final_answer 字段
        self.task_data["final_answer"] = final_answer
        # 定义最终文件名
        output_file = "Task_Split_Final.json"
        # 调用通用的保存方法
        success = self._save_task_data(output_file)
        if success:
            print(
                f"# 信息：最终结果文件已保存: {os.path.join(self.current_log_dir, output_file)}"
            )
        else:
            print(f"# 错误：保存最终结果文件 {output_file} 失败。")
        return success

    def has_more_tasks(self) -> bool:
        """
        检查是否还有未执行的原子任务。
        比较 self.current_task_id 和 self.task_data 中原子任务的总数。

        :return: 如果当前任务 ID 小于或等于任务总数，返回 True，否则返回 False。
        """
        if not self.task_data or not isinstance(
            self.task_data.get("atomic_tasks"), list
        ):
            # 如果没有任务数据或格式不正确，则认为没有更多任务
            return False
        # 获取原子任务列表的长度
        total_tasks = len(self.task_data.get("atomic_tasks", []))
        # 比较当前要执行的任务ID和总任务数
        # print(f"# 调试: has_more_tasks: current_id={self.current_task_id}, total_tasks={total_tasks}") # 可选调试
        return self.current_task_id <= total_tasks


# 注意：这个文件本身不包含可执行的 __main__ 块。
# TaskExecutionAgent 通常由外部脚本（如 run_Jarvis.py）在 TaskDecomposer 成功执行后进行实例化和调用。
