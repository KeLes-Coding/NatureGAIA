import json
import requests
import os
from typing import Dict, List
from collections import OrderedDict
from .road_json import TaskData


class OpenAITaskDecomposer:
    def __init__(self, api_key: str, model: str = None, proxy: str = None):
        self.api_url = (
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        )
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "enable_thinking": "true",
        }
        self.model = model
        self.proxy = proxy  # Added proxy attribute
        self.system_prompt = """You are an expert task decomposer. Please strictly follow these rules to process input tasks:
1. Analyze temporal sequence: Identify time-based dependencies in the task (e.g., 'search first, then process results')
2. Resolve references: Handle referring expressions like 'this', 'this person', 'this year', etc.
3. Identify tool dependencies: Specify data sources required for each step (e.g., Wikipedia, Apple Music, etc.)
4. Required output format:
{
    "Task": "Original task",
    "atomic_tasks": [
        {
            "atomic_tasks_ID": auto-increment ID,
            "atomic_tasks_description": "Clear sub-task description including search tools and objectives",
            "atomic_tasks_answer": "",
            "atomic_tasks_status",
        }
    ]
}"""

    def _generate_payload(self, user_input: str) -> Dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_input},
            ],
            "temperature": 0,
            "max_tokens": 2000,
        }

    def decompose(self, complex_task: str) -> Dict:
        try:
            # Set proxy parameters
            proxies = None
            if self.proxy:
                proxies = {
                    "http": self.proxy,
                    "https": self.proxy,
                }

            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=self._generate_payload(complex_task),
                proxies=proxies,  # Added proxy parameter
            )
            response.raise_for_status()

            result = json.loads(response.json()["choices"][0]["message"]["content"])

            # Add a final answer field
            result["final_answer"] = ""

            # Add atomic_tasks_numbers at the top level
            result["atomic_tasks_numbers"] = len(result["atomic_tasks"])

            # Reorder the fields to ensure atomic_tasks_numbers comes before atomic_tasks
            ordered_result = OrderedDict(
                [
                    ("Task", result["Task"]),
                    ("atomic_tasks_numbers", result["atomic_tasks_numbers"]),
                    ("atomic_tasks", result["atomic_tasks"]),
                    ("final_answer", result["final_answer"]),
                ]
            )

            # Result validation
            if not self._validate_output(ordered_result):
                raise ValueError("Output format validation failed")

            # Save the result to JSON file
            self._save_result(ordered_result)

            return ordered_result
        except requests.exceptions.RequestException as e:
            print(f"API request error: {str(e)}")
            return {}
        except json.JSONDecodeError:
            print("Response parsing failed")
            return {}
        except Exception as e:
            print(f"Error saving result: {str(e)}")
            return {}

    def _validate_output(self, output: Dict) -> bool:
        required_keys = ["Task", "atomic_tasks_numbers", "atomic_tasks", "final_answer"]
        if not all(key in output for key in required_keys):
            return False

        task_fields = [
            "atomic_tasks_ID",
            "atomic_tasks_description",
            "atomic_tasks_answer",
            "atomic_tasks_status",
        ]
        return all(
            all(field in task for field in task_fields)
            for task in output["atomic_tasks"]
        )

    def _save_result(self, result: Dict):
        # 获取当前脚本所在目录
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # 创建Task目录（如果不存在）
        task_dir = os.path.join(script_dir, "Task")
        if not os.path.exists(task_dir):
            os.makedirs(task_dir)

        # Define output file path
        output_file = os.path.join(task_dir, "Task_Split_Original.json")

        # Save JSON to file
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


# Usage example
if __name__ == "__main__":
    api_key = "sk-3f16802c73d549d391e7f708cece3ab3"
    proxy = "http://127.0.0.1:7890"  # Proxy address
    model = "qwen-max"

    decomposer = OpenAITaskDecomposer(api_key, model, proxy=proxy)

    complex_task = (
        "使用wiki百科搜索周杰伦，告诉我他在2000年发布了哪张专辑？搜索这张这张专辑，告诉我这张专辑中包含了哪些曲目？"
        "使用APPLE Music搜索查看专辑的第一首歌的作词人是谁？在网易云音乐APP中搜索这位作词人，打开其主页，告诉我他是哪一年出生的？"
        "使用Google搜索这一年的4月4日是哪一家美国科技公司成立？使用 Google Map 搜索这家公司的中国总部位于那一个城市？"
    )

    result = decomposer.decompose(complex_task)
    print(json.dumps(result, ensure_ascii=False, indent=2))
