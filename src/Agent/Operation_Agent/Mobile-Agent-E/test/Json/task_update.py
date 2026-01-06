import json
import requests
import os
from typing import Dict, List


class TaskExecutionAgent:
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
        self.proxy = proxy
        self.current_task_id = 1
        self.task_data = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.task_dir = os.path.join(self.script_dir, "Task")

        # Create Task directory if it doesn't exist
        if not os.path.exists(self.task_dir):
            os.makedirs(self.task_dir)

    def load_initial_task(self, input_file: str = "Task_Split_Original.json") -> bool:
        """Load the initial task decomposition file"""
        input_path = os.path.join(self.task_dir, input_file)
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                self.task_data = json.load(f)
            self.current_task_id = 1
            return True
        except FileNotFoundError:
            print(f"Error: Input file {input_file} not found in Task directory")
            return False
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON format in {input_file}")
            return False

    def get_current_task(self) -> Dict:
        """Get the current task to be executed"""
        if not self.task_data:
            return {}

        for task in self.task_data["atomic_tasks"]:
            if task["atomic_tasks_ID"] == self.current_task_id:
                return task
        return {}

    def update_task_answer(self, answer: str) -> bool:
        """Update the current task with its answer and prepare the next version"""
        if not self.task_data:
            return False

        # Update the current task's answer
        for task in self.task_data["atomic_tasks"]:
            if task["atomic_tasks_ID"] == self.current_task_id:
                task["atomic_tasks_answer"] = answer
                break

        # Update descriptions of subsequent tasks based on the answer
        self._update_subsequent_tasks()

        # Save the updated version
        output_file = f"Task_Split_{self.current_task_id}.json"
        self._save_task_data(output_file)

        # Move to next task
        self.current_task_id += 1

        # Check if all tasks are completed and save final file
        if not self.has_more_tasks():
            self._save_final_file()

        return True

    def _update_subsequent_tasks(self):
        """Update descriptions of subsequent tasks based on current answers"""
        if not self.task_data:
            return

        # Collect all answers up to current task
        answers = {}
        for task in self.task_data["atomic_tasks"]:
            if task["atomic_tasks_ID"] <= self.current_task_id:
                answers[task["atomic_tasks_ID"]] = task["atomic_tasks_answer"]

        # Update subsequent tasks' descriptions
        for task in self.task_data["atomic_tasks"]:
            if task["atomic_tasks_ID"] > self.current_task_id:
                # Generate updated description using API
                updated_description = self._generate_updated_description(
                    task["atomic_tasks_description"], answers
                )
                if updated_description:
                    task["atomic_tasks_description"] = updated_description

    def _generate_updated_description(
        self, original_description: str, answers: Dict
    ) -> str:
        """Use API to generate an updated task description based on previous answers"""
        prompt = f"""Please update the following task description by incorporating information from previous answers:
        
Original task description: {original_description}

Previous answers: {json.dumps(answers, ensure_ascii=False)}

Return only the updated task description, nothing else."""

        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 500,
            }

            proxies = None
            if self.proxy:
                proxies = {
                    "http": self.proxy,
                    "https": self.proxy,
                }

            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                proxies=proxies,
            )
            response.raise_for_status()

            return response.json()["choices"][0]["message"]["content"].strip()

        except Exception as e:
            print(f"Error generating updated description: {str(e)}")
            return original_description

    def _save_task_data(self, filename: str):
        """Save the current task data to a JSON file"""
        output_path = os.path.join(self.task_dir, filename)
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(self.task_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving task data: {str(e)}")

    def _save_final_file(self):
        """Save the final task data with the final_answer field"""
        if not self.task_data or "atomic_tasks" not in self.task_data:
            return

        # Get the last task's answer
        last_task = max(
            self.task_data["atomic_tasks"], key=lambda x: x["atomic_tasks_ID"]
        )
        final_answer = last_task["atomic_tasks_answer"]

        # Create final data structure
        final_data = {
            "Task": self.task_data["Task"],
            "atomic_tasks": self.task_data["atomic_tasks"],
            "final_answer": final_answer,
        }

        output_file = "Task_Split_Final.json"
        output_path = os.path.join(self.task_dir, output_file)

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving final task data: {str(e)}")

    def has_more_tasks(self) -> bool:
        """Check if there are more tasks to process"""
        if not self.task_data:
            return False
        return self.current_task_id <= len(self.task_data["atomic_tasks"])


class AnswerValidationAgent:
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
        self.proxy = proxy

    def validate_answers(self, user_answer: str, ground_truth: str) -> bool:
        """
        Validate if two answers express the same core content using LLM
        Returns:
        bool: True for core content match, False otherwise
        """
        # TODO: prompt仍需补充修改（加入问题 + 中英文匹配、人名简写匹配、不完整人名姓名匹配）
        validation_prompt = f"""Strictly analyze if these two answers express the same core content. Ignore:
        - Case differences ("beijing" vs "Beijing")
        - Punctuation differences ("Beijing." vs "Beijing")
        - Unit differences ("1975" vs "1975 AD")
        - Synonym substitutions ("Shanghai City" vs "Shanghai")
        - Simplified/Traditional Chinese differences
        - Minor typos ("Beijin" vs "Beijing")
        
        Strictly check:
        - Numerical accuracy ("1975" vs "1976" = different)
        - Key entities accuracy (exact match for names, organizations)
        
        User Answer: [{user_answer}]
        Reference Answer: [{ground_truth}]
        
        Return ONLY a single word: True or False"""

        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": validation_prompt}],
                "temperature": 0,
                "max_tokens": 5,
            }

            proxies = None
            if self.proxy:
                proxies = {
                    "http": self.proxy,
                    "https": self.proxy,
                }

            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                proxies=proxies,
                timeout=10,
            )
            response.raise_for_status()

            # Parse response
            result = response.json()["choices"][0]["message"]["content"].strip().lower()

            # Error-tolerant parsing
            if "true" in result:
                return True
            elif "false" in result:
                return False
            else:
                print(f"Unparseable validation result: {result}")
                return False

        except requests.exceptions.RequestException as e:
            print(f"Validation request failed: {str(e)}")
            return False
        except KeyError as e:
            print(f"Response parsing error: Missing key {str(e)}")
            return False


# Usage example
if __name__ == "__main__":
    # Initialize validation agent (using same API configuration)
    validation_agent = AnswerValidationAgent(
        api_key="sk-3f16802c73d549d391e7f708cece3ab3",
        model="qwen-max",
        proxy="http://127.0.0.1:7890",
    )

    # Test cases
    test_cases = [
        ("北京", "北京市", True),  # Chinese city name vs formal name
        ("1975", "1975年", True),  # Year with/without unit
        ("微软公司", "Microsoft", True),  # Chinese vs English company name
        ("周杰伦", "周杰倫", True),  # Simplified vs Traditional Chinese
        ("Beijin", "Beijing", True),  # Common typo
        ("上海", "江苏省", False),  # Different locations
        ("1975", "1976", False),  # Different numbers
        ("阿里巴巴", "腾讯", False),  # Different companies
    ]

    for user_ans, true_ans, expected in test_cases:
        result = validation_agent.validate_answers(user_ans, true_ans)
        print(f"User answer: '{user_ans}' vs Reference answer: '{true_ans}'")
        print(
            f"Expected: {expected} | Actual: {result} | Validation {'Pass' if result == expected else 'Fail'}"
        )
        print("-" * 60)

# # Usage example
# if __name__ == "__main__":
#     api_key = "sk-3f16802c73d549d391e7f708cece3ab3"
#     proxy = "http://127.0.0.1:7890"
#     model = "qwen-max"

#     agent = TaskExecutionAgent(api_key, model, proxy=proxy)

#     # Load the initial task decomposition
#     if not agent.load_initial_task():
#         exit(1)

#     # Example of processing tasks one by one with simulated answers
#     while agent.has_more_tasks():
#         current_task = agent.get_current_task()
#         print(f"\nCurrent Task ID: {current_task['atomic_tasks_ID']}")
#         print(f"Description: {current_task['atomic_tasks_description']}")

#         # In a real scenario, you would execute the task and get the answer
#         # Here we simulate user input
#         answer = input("Enter the answer for this task: ")

#         # Update the task with the answer
#         if not agent.update_task_answer(answer):
#             print("Failed to update task answer")
#             break

#         print(f"Task {current_task['atomic_tasks_ID']} completed and saved.")

#     print("\nAll tasks processed!")
