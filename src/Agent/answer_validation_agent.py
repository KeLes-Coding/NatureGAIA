import requests
import json
import os
import time


class AnswerValidationAgent:
    """
    # 使用大语言模型 (LLM) 验证用户答案和参考答案是否表达相同核心内容的代理。
    """

    def __init__(
        self, api_url: str, api_key: str, model: str = None, proxy: str = None
    ):
        """
        # 初始化 AnswerValidationAgent。

        Args:
            api_url (str): LLM API 的 URL。
            api_key (str): 用于 API 身份验证的密钥。
            model (str, optional): 要使用的 LLM 模型名称。 Defaults to None.
            proxy (str, optional): 用于 API 请求的代理服务器 URL (例如 "http://127.0.0.1:7890")。 Defaults to None.

        Raises:
            ValueError: 如果未提供 api_key。
        """
        if not api_key:
            raise ValueError("# 必须提供 API 密钥 (api_key)。")
        self.api_url = api_url
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "enable_thinking": "true",
        }
        self.model = model
        self.proxy = proxy
        # 可选：用于处理速率限制的计数器和时间戳
        # self.request_count = 0
        # self.last_request_time = time.time()

    def _create_validation_prompt(
        self, user_question: str, user_answer: str, ground_truth: str
    ) -> str:
        """# 为 LLM 创建详细的验证提示。"""
        # 注意：根据请求扩展了要忽略和考虑的事项列表
        prompt = f"""Analyze if the User Answer provides an equivalent answer to the User Question compared to the Reference Answer. Focus on semantic meaning and core information relevant to the question.

User Question: [{user_question}]
User Answer: [{user_answer}]
Reference Answer: [{ground_truth}]

Ignore superficial differences UNLESS they change the core meaning in the context of the question:
- Case differences (e.g., "beijing" vs "Beijing")
- Punctuation differences (e.g., "Beijing." vs "Beijing")
- Minor formatting (e.g., whitespace, newlines)
- Presence/absence of units if unambiguous (e.g., "1975" vs "1975 AD", "$50" vs "50 dollars")
- Common synonyms or equivalent phrasings (e.g., "Shanghai City" vs "Shanghai", "largest city" vs "most populous city")
- Simplified vs. Traditional Chinese characters (e.g., "周杰伦" vs "周杰倫")
- Minor typos that don't create ambiguity (e.g., "Beijin" vs "Beijing")
- Language differences if the meaning is identical (e.g., "Microsoft" vs. "微软公司", "Paris" vs "巴黎")
- Abbreviations/Acronyms vs. full names if commonly understood (e.g., "NASA" vs. "National Aeronautics and Space Administration", "UN" vs "United Nations")
- Name variations if they refer to the same entity (e.g., "Bill Gates" vs "William Henry Gates III", "J.K. Rowling" vs. "Joanne Rowling") - *use caution if the question requires a specific formal name*.
- Presence of extra descriptive text in one answer if the core requested information is present and matches (e.g., User Answer: "Paris, the capital of France" vs. Reference Answer: "Paris" for the question "What is the capital of France?")

Strictly check for differences in:
- Numerical values (e.g., "1975" vs "1976")
- Key entities (names, places, organizations) when they refer to different things (e.g., "阿里巴巴" vs "腾讯", "London" vs "Paris")
- Core facts or claims being asserted.
- Answers that address different aspects of the question if the reference answer is specific.

Based on this analysis, determine if the User Answer is semantically equivalent to the Reference Answer *as an answer to the User Question*.

Return ONLY a valid JSON object in the following format, with no other text before or after it:
{{
  "status": boolean,
  "description": "A concise explanation of why the status is true or false, referencing the comparison points."
}}

Example Output for a match:
{{
  "status": true,
  "description": "Both answers correctly identify Beijing, ignoring minor variations like city/municipality designation."
}}

Example Output for a mismatch:
{{
  "status": false,
  "description": "User answer provides '1976' while the reference answer is '1975', a factual difference."
}}

Provide your JSON output now:"""
        return prompt

    def validate_answers(
        self,
        atomic_tasks_ID: int,
        user_question: str,
        user_answer: str,
        ground_truth: str,
    ) -> dict:
        """
        # 在用户问题的背景下，使用 LLM 验证 user_answer 和 ground_truth 是否表达相同核心内容。

        Args:
            atomic_tasks_ID (int): # 原子任务的 ID。
            user_question (str): # 用户提出的问题。
            user_answer (str): # 用户提供的答案。
            ground_truth (str): # 标准的正确答案。

        Returns:
            dict: # 一个包含 'atomic_tasks_ID', 'status' (布尔值),
                  # 和 'description' (字符串) 的字典。失败时返回默认的错误结构。
        """
        validation_prompt = self._create_validation_prompt(
            user_question, user_answer, ground_truth
        )

        default_error_response = {
            "atomic_tasks_ID": atomic_tasks_ID,
            "status": False,
            "description": "# 验证因内部错误失败。",  # Default description, will be overwritten
        }

        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": validation_prompt}],
                "temperature": 0,
                # "max_tokens": 400,  # <<< 增加了 max_tokens
            }

            proxies = None
            if self.proxy:
                proxies = {
                    "http": self.proxy,
                    "https": self.proxy,
                }

            timeout_seconds = 60

            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                # proxies=proxies,
                timeout=timeout_seconds,
            )
            response.raise_for_status()

            # --- 调试：打印完整的原始响应 ---
            print(f"DEBUG: Full raw response text: {response.text}")
            # --- 调试结束 ---

            response_text = ""
            finish_reason = "N/A"
            response_data = None  # 初始化 response_data

            # --- 解析 API 响应结构 ---
            try:
                response_data = response.json()
                # --- 调试：打印 finish_reason ---
                finish_reason = response_data.get("choices", [{}])[0].get(
                    "finish_reason", "N/A"
                )
                print(f"DEBUG: API finish_reason: {finish_reason}")
                # --- 调试结束 ---

                if "choices" in response_data and len(response_data["choices"]) > 0:
                    message = response_data["choices"][0].get("message", {})
                    response_text = message.get("content", "").strip()
                    if not response_text:
                        response_text = (
                            response_data["choices"][0].get("text", "").strip()
                        )  # 备用方案

                elif response.text:  # 如果 choices 结构不存在或为空，尝试直接用文本
                    response_text = response.text.strip()
                else:
                    raise ValueError("# 未能从API响应中提取有效内容")

            except (json.JSONDecodeError, ValueError, KeyError) as e:
                print(f"# 解析 API 响应结构时出错: {e}")
                print(f"# 原始响应状态码: {response.status_code}")
                print(f"# 原始响应文本 (前 500 字符): {response.text[:500]}")
                default_error_response["description"] = (
                    "# 验证失败：无法解析 API 响应结构。"
                )
                return default_error_response

            # --- 调试：打印提取出的 response_text ---
            print(f"DEBUG: Extracted response_text: {repr(response_text)}")
            # --- 调试结束 ---

            # --- 解析 LLM 生成的内容为 JSON ---
            try:
                json_start = response_text.find("{")
                json_end = response_text.rfind("}") + 1
                potential_json = ""  # 初始化 potential_json

                if json_start != -1 and json_end > json_start:
                    potential_json = response_text[json_start:json_end]
                    # --- 调试：打印尝试解析的 JSON 字符串 ---
                    print(
                        f"DEBUG: Attempting to parse potential_json: {repr(potential_json)}"
                    )
                    # --- 调试结束 ---
                    result_json = json.loads(potential_json)
                    # --- 调试：打印成功解析的 JSON ---
                    print(f"DEBUG: JSON parsing successful: {result_json}")
                    # --- 调试结束 ---
                else:
                    raise json.JSONDecodeError(
                        "# 在响应文本中未找到 JSON 对象。", response_text, 0
                    )

                # --- 验证 JSON 结构 ---
                if (
                    "status" in result_json
                    and isinstance(result_json["status"], bool)
                    and "description" in result_json
                    and isinstance(result_json["description"], str)
                ):
                    return {
                        "atomic_tasks_ID": atomic_tasks_ID,
                        "status": result_json["status"],
                        "description": result_json["description"].strip(),
                    }
                else:
                    print(f"# 验证错误：LLM 响应 JSON 缺少必需键或类型错误。")
                    print(
                        f"# 解析出的 JSON: {result_json}"
                    )  # 打印导致错误的已解析 JSON
                    default_error_response["description"] = (
                        "# 验证失败：LLM 响应格式错误。"
                    )
                    return default_error_response

            except json.JSONDecodeError as e:
                # --- 调试：打印 JSON 解析失败信息 ---
                print(f"DEBUG: JSON parsing failed: {e}")
                # --- 调试结束 ---
                print(f"# 验证错误：无法将 LLM 的内容解析为 JSON。错误：{e}")
                print(
                    f"# LLM 返回的原始文本 (前 500 字符): {response_text[:500]}"
                )  # 保持打印原始文本片段
                default_error_response["description"] = (
                    "# 验证失败：来自 LLM 的 JSON 响应无效。"
                )
                return default_error_response

        except requests.exceptions.Timeout:
            print(f"# 验证请求失败：在 {timeout_seconds} 秒后超时。")
            default_error_response["description"] = "# 验证失败：API 请求超时。"
            return default_error_response
        except requests.exceptions.RequestException as e:
            print(f"# 验证请求失败：{str(e)}")
            default_error_response["description"] = f"# 验证失败：网络错误 {str(e)}"
            return default_error_response
        except Exception as e:
            print(f"# 验证过程中发生意外错误: {str(e)}")
            default_error_response["description"] = f"# 验证失败：发生意外错误 {str(e)}"
            return default_error_response


# --- 使用示例 ---
if __name__ == "__main__":
    # 重要提示：请替换为你的实际 API 密钥或从环境变量加载
    api_key = "sk-3f16802c73d549d391e7f708cece3ab3"

    # 初始化验证代理
    validation_agent = AnswerValidationAgent(
        api_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        api_key=api_key,
        model="qwen-max",
        proxy="http://127.0.0.1:7890",  # 如果需要代理
    )

    # 测试用例
    test_cases = [
        {
            "id": 1,
            "question": "中国的首都是哪里？",
            "user_ans": "北京",
            "ground_truth": "北京市",
            "expected_status": True,
        },
        {
            "id": 2,
            "question": "美国独立宣言是哪一年签署的？",
            "user_ans": "1776",
            "ground_truth": "1776年",
            "expected_status": True,
        },
        {
            "id": 3,
            "question": "哪个公司开发了 Windows 操作系统？",
            "user_ans": "微软公司",
            "ground_truth": "Microsoft",
            "expected_status": True,
        },
        {
            "id": 4,
            "question": "谁演唱了歌曲《七里香》？",
            "user_ans": "周杰伦",
            "ground_truth": "周杰倫",
            "expected_status": True,
        },
        {
            "id": 5,
            "question": "中国的首都是哪里？",
            "user_ans": "北津",
            "ground_truth": "北京",
            "expected_status": True,
        },
        {
            "id": 6,
            "question": "中国人口最多的城市是哪个？",
            "user_ans": "上海",
            "ground_truth": "江苏省",
            "expected_status": False,
        },
        {
            "id": 7,
            "question": "第二次世界大战是哪年结束的？",
            "user_ans": "1946",
            "ground_truth": "1945",
            "expected_status": False,
        },
        {
            "id": 8,
            "question": "哪个科技巨头拥有微信？",
            "user_ans": "阿里巴巴",
            "ground_truth": "腾讯",
            "expected_status": False,
        },
        {
            "id": 9,
            "question": "水的化学符号是什么？",
            "user_ans": "H2O",
            "ground_truth": "$H_2O$",
            "expected_status": True,
        },
        {
            "id": 10,
            "question": "谁写了《哈利·波特》？",
            "user_ans": "J. K. 罗琳",
            "ground_truth": "Joanne Rowling",
            "expected_status": True,
        },
        {
            "id": 11,
            "question": "美国的太空机构叫什么？",
            "user_ans": "NASA",
            "ground_truth": "美国国家航空航天局",
            "expected_status": True,
        },
        {
            "id": 12,
            "question": "法国的首都是哪里？",
            "user_ans": "巴黎是法国的首都和人口最多的城市。",
            "ground_truth": "巴黎",
            "expected_status": True,
        },
        {
            "id": 13,
            "question": "法国的首都是哪里？",
            "user_ans": "里昂",
            "ground_truth": "巴黎",
            "expected_status": False,
        },
    ]

    print(
        f"Using Model: {validation_agent.model if validation_agent.model else '未指定'}"
    )
    print("-" * 80)

    for i, test in enumerate(test_cases):
        print(f"Running Test Case {test['id']}...")
        print(f"  Question: {test['question']}")
        print(f"  User Answer: '{test['user_ans']}'")
        print(f"  Reference Answer: '{test['ground_truth']}'")

        if api_key == "DUMMY_API_KEY_FOR_DEMO":
            print("  # 警告：使用模拟 API Key，跳过实际 API 调用。")
            result_json = {
                "atomic_tasks_ID": test["id"],
                "status": False,
                "description": "# 使用了模拟 API Key，无法进行实际验证。",
            }
        else:
            result_json = validation_agent.validate_answers(
                atomic_tasks_ID=test["id"],
                user_question=test["question"],
                user_answer=test["user_ans"],
                ground_truth=test["ground_truth"],
            )

        print(f"  LLM Response JSON:")  # Changed label slightly for clarity
        print(json.dumps(result_json, indent=2, ensure_ascii=False))

        status_match = result_json.get("status") == test["expected_status"]
        print(
            f"  Expected Status: {test['expected_status']} | Actual Status: {result_json.get('status')} | Test Result: {'Pass' if status_match else 'Fail'}"
        )
        print("-" * 80)
