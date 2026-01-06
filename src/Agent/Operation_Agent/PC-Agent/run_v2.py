import os
import time
import copy
import torch
import shutil
from PIL import Image, ImageDraw
import json  # <<< ADDED: Import the json library

# Assuming these imports are correct relative to your project structure
from PCAgent_v1.api import inference_chat
from PCAgent_v1.text_localization import ocr
from PCAgent_v1.icon_localization import det
from PCAgent_v1.prompt import (
    get_action_prompt,
    get_reflect_prompt,
    get_memory_prompt,
    get_process_prompt,
)
from PCAgent_v1.chat import (
    init_action_chat,
    init_reflect_chat,
    init_memory_chat,
    add_response,
)
from PCAgent_v1.merge_strategy import (
    merge_boxes_and_texts,
    merge_all_icon_boxes,
    merge_boxes_and_texts_new,
)
import config  # Assuming config.py exists with necessary variables

# <<< REMOVED Placeholder functions and Config class >>>

from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks
from modelscope import (
    snapshot_download,
    AutoModelForCausalLM,
    AutoTokenizer,
    GenerationConfig,
)

from dashscope import MultiModalConversation
import dashscope
import concurrent

from pynput.mouse import Button, Controller
import argparse
import pyautogui
import pyperclip


import re
import traceback


def contains_chinese(text):
    if not isinstance(text, str):  # Add check if text is string
        return False
    chinese_pattern = re.compile(r"[\u4e00-\u9fff]+")
    match = chinese_pattern.search(text)
    return match is not None


import random
from PIL import ImageFont


def cmyk_to_rgb(c, m, y, k):
    r = 255 * (1.0 - c / 255) * (1.0 - k / 255)
    g = 255 * (1.0 - m / 255) * (1.0 - k / 255)
    b = 255 * (1.0 - y / 255) * (1.0 - k / 255)
    return int(r), int(g), int(b)


def draw_coordinates_boxes_on_image(
    image_path, coordinates, output_image_path, font_path
):
    """Draws bounding boxes with numbers on an image."""
    try:
        image = Image.open(image_path)
        width, height = image.size
        draw = ImageDraw.Draw(image)
        total_boxes = len(coordinates)
        colors = [
            (
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            )
            for _ in range(total_boxes)
        ]

        for i, coord in enumerate(coordinates):
            # Ensure coordinates are valid numbers
            if not all(isinstance(c, (int, float)) for c in coord) or len(coord) != 4:
                print(f"Warning: Skipping invalid coordinate data: {coord}")
                continue

            c, m, y, k = colors[i]
            color = cmyk_to_rgb(c, m, y, k)

            # Ensure coordinates are within image bounds and valid rectangle
            x1, y1, x2, y2 = map(int, coord)
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(width, x2)
            y2 = min(height, y2)
            if x1 >= x2 or y1 >= y2:
                print(
                    f"Warning: Skipping invalid box dimensions: ({x1},{y1})-({x2},{y2})"
                )
                continue

            draw.rectangle(
                [x1, y1, x2, y2], outline=color, width=max(1, int(height * 0.0025))
            )

            try:
                font = ImageFont.truetype(
                    font_path, max(10, int(height * 0.012))
                )  # Ensure minimum font size
            except IOError:
                print(
                    f"Warning: Font file not found at {font_path}. Using default font."
                )
                font = ImageFont.load_default()  # Use default font as fallback

            text_x = x1 + max(1, int(height * 0.0025))
            text_y = max(
                0, y1 - max(10, int(height * 0.013))
            )  # Adjust based on font size
            draw.text((text_x, text_y), str(i + 1), fill=color, font=font)

        image = image.convert("RGB")
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
        image.save(output_image_path)
        print(f"Saved annotated image to: {output_image_path}")
    except FileNotFoundError:
        print(f"Error: Input image file not found at {image_path}")
    except Exception as e:
        print(f"Error drawing boxes on image {image_path}: {e}")
        print(traceback.format_exc())


parser = argparse.ArgumentParser(description="PC Agent")
parser.add_argument("--instruction", type=str, default="Open Google Chrome.")
parser.add_argument("--icon_caption", type=int, default=0)  # 0: w/o icon_caption
parser.add_argument(
    "--location_info", type=str, default="center"
)  # center or bbox or icon_centor; icon_center: only icon center
parser.add_argument("--use_som", type=int, default=1)  # for action
parser.add_argument(
    "--draw_text_box", type=int, default=0, help="whether to draw text boxes in som."
)
parser.add_argument("--font_path", type=str, default="C:/Windows/Fonts/arial.ttf")
parser.add_argument("--pc_type", type=str, default="windows")  # windows or mac
parser.add_argument("--api_url", type=str, default="", help="GPT-4o api url.")
parser.add_argument("--api_token", type=str, help="Your GPT-4o api token.")
parser.add_argument(
    "--qwen_api", type=str, default="", help="Input your Qwen-VL api if icon_caption=1."
)
parser.add_argument("--add_info", type=str, default="")
parser.add_argument("--disable_reflection", action="store_true")
# <<< MODIFIED: Argument description slightly changed >>>
parser.add_argument(
    "--log_dir",
    type=str,
    default="./execution_logs",
    help="Base directory for logs. A subdirectory will be created based on atomic_tasks_numbers.",
)
# <<< ADDED: Argument for atomic task number >>>
parser.add_argument(
    "--atomic_tasks_numbers",
    type=int,
    default=1,
    help="Identifier for the specific atomic task run. Used to create a subdirectory within log_dir.",
)


args = parser.parse_args()

# <<< MODIFIED: Define base directories based on log_dir AND atomic_tasks_numbers >>>
base_log_dir = args.log_dir
atomic_task_id = str(args.atomic_tasks_numbers)
# This is the main directory for this specific task run
atomic_task_dir_path = os.path.join(base_log_dir, atomic_task_id)

# Define subdirectories within the specific task directory
screenshot_dir = os.path.join(atomic_task_dir_path, "screenshots")
temp_dir = os.path.join(atomic_task_dir_path, "temp")

# <<< MODIFIED: Create the main task directory and subdirectories >>>
# Create the main directory for this atomic task
os.makedirs(atomic_task_dir_path, exist_ok=True)
# Create subdirectories
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(temp_dir, exist_ok=True)
print(f"Task files will be stored in: {atomic_task_dir_path}")
# <<< END MODIFIED SECTION >>>


if args.pc_type == "mac":
    ctrl_key = "command"
    search_key = ["command", "space"]
    ratio = 2
    # Update default font path for Mac if necessary, or keep Windows default
    # args.font_path = "/System/Library/Fonts/Helvetica.ttc" # Example for Mac
else:  # Assuming Windows
    ctrl_key = "ctrl"
    search_key = ["win", "s"]
    ratio = 1
    # Keep the default Windows font path or adjust if needed
    # args.font_path = "C:/Windows/Fonts/arial.ttf" # Explicitly setting default

# Ensure font path exists or handle fallback
if not os.path.exists(args.font_path):
    print(
        f"Warning: Specified font path '{args.font_path}' not found. Check the path or OS type. Falling back."
    )
    # Optionally set a known fallback or let draw function handle it
    # args.font_path = "..." # A known safe path or None

vl_model_version = config.vl_model_name
llm_model_version = config.llm_model_name


class TaskSummarizer:
    """
    An AI assistant class that summarizes the completion status of a PC agent task
    based on the user instruction, the agent's final thought, and the final screenshot.

    It calls a multimodal LLM to generate a summary JSON response containing English keys
    "answer" and "description", strictly using the provided inputs.
    """

    def __init__(self, api_url: str, api_token: str, model_version: str):
        """
        Initializes the Task Summarizer.

        Args:
            api_url (str): The URL for the LLM API.
            api_token (str): The token for the LLM API.
            model_version (str): The LLM model version to use (e.g., 'gpt-4o', 'qwen-vl-max').
        """
        self.api_url = api_url
        self.api_token = api_token
        self.model_version = model_version
        print(f"TaskSummarizer initialized with model: {self.model_version}")

    def _init_chat_summarize(self) -> list:
        """
        Initializes the chat history with an English system prompt.
        The prompt instructs the model to respond *only* in the specified English JSON format.

        Returns:
            list: The initial chat history list containing the system prompt.
        """
        chat_history = []
        # --- NEW English System Prompt demanding JSON output ---
        system_prompt = """You are an AI assistant specialized in analyzing PC screenshots, the user's original instruction, and the agent's final thought ('final_thought'). Your goal is to accurately summarize the task completion status based *exclusively* on the provided information, generating a JSON object containing an "answer" and a "description".

**--- Task: Analyze inputs and generate the specified JSON object ---**
Carefully analyze the final screenshot, the user's original instruction, and the agent's final thought to populate the JSON response according to these strict rules.

**--- Strict output specification (MUST FOLLOW) ---**
1.  **JSON format only**:
    * Must output a pure JSON object without any additional packaging (like ```json markdown).
    * Do not include comments or descriptive text outside the JSON structure.
    * All JSON strings must use double quotes `"`.

2.  **Your response format MUST look exactly like this**:
    {
        "answer": "Direct summary of task completion status, synthesized using only input information.",
        "description": "Three-part English explanation based only on input information: 1) Analysis of the final screenshot; 2) Analysis of completion degree based on the user instruction; 3) Conclusion derivation."
    }

3.  **Data source restrictions**:
    * All answers and descriptions must be based **strictly** on the provided user instruction, final thought, and final screenshot.
    * If there is insufficient information to determine the status, set "answer" to "Insufficient information to summarize."
    * **Strictly prohibit** supplementing with any external knowledge (even if you think information should exist).

**--- Validation Examples ---**
◆ Correct example:
{
    "answer": "Successfully created a new document in Word and wrote a brief introduction about Alibaba, but it has not been saved yet.",
    "description": "1) The final screenshot shows an open Word document containing text related to 'Alibaba introduction', but the save button is not active or there is no save dialog box. | 2) The user instruction was to create a Word document, write an introduction, and save it. The screenshot indicates the first two steps are done. | 3) The conclusion is that the task is mostly completed, but the saving step is not reflected in the screenshot."
}


◆ Incorrect example:
```json // Code block identifier is prohibited in the actual output
{
    'answer': 'Task failed', // Single quotes are prohibited
    "description": "Based on common sense, the user probably forgot to click save..." // External knowledge and speculation are prohibited
}
```
"""
        # Assuming add_response or the API call can handle this format
        chat_history.append(["system", [{"type": "text", "text": system_prompt}]])
        return chat_history

    def _parse_model_output(self, raw_output: str) -> dict:
        """
        Parses the raw output string from the AI model.
        Expects it to be a valid JSON string matching the template defined in the system prompt,
        containing English keys 'answer' and 'description'.

        Args:
            raw_output (str): The raw text output from the AI model, expected to be a JSON string.

        Returns:
            dict: A dictionary containing 'answer' and 'description'. Returns a dictionary with error info if parsing fails or format is incorrect.
        """
        print(f"--- Attempting to parse model output ---")
        print(f"Raw output received:\n{raw_output}")
        print(f"--- End of raw output ---")

        # Attempt to clean potential Markdown code block markers
        cleaned_output = raw_output.strip()
        if cleaned_output.startswith("```json"):
            cleaned_output = cleaned_output[7:]
        if cleaned_output.endswith("```"):
            cleaned_output = cleaned_output[:-3]
        cleaned_output = cleaned_output.strip()

        try:
            # Attempt to parse the cleaned string as JSON
            data = json.loads(cleaned_output)

            # Validate if the result is a dictionary and contains the expected English keys
            if isinstance(data, dict):
                # Use .get() for safety, providing default error messages if keys are missing
                answer = data.get(
                    "answer",
                    "Error: JSON response from model is missing the 'answer' key.",
                )
                description = data.get(
                    "description",
                    "Error: JSON response from model is missing the 'description' key.",
                )

                # Optional stricter check: ensure keys actually exist
                if "answer" not in data:
                    answer = "Error: 'answer' field not found in JSON response."
                if "description" not in data:
                    description = (
                        "Error: 'description' field not found in JSON response."
                    )

                # Return the dictionary with English keys
                return {"answer": answer, "description": description}
            else:
                # The string was valid JSON, but not the expected dictionary format
                print(f"--- JSON parsing error: Expected a dict, got {type(data)} ---")
                return {
                    "answer": "Error: Model returned valid JSON, but not the expected dictionary format.",
                    "description": f"Received type: {type(data)}, Cleaned raw data: {cleaned_output}",
                }

        except json.JSONDecodeError as e:
            # JSON parsing failed
            print(f"--- JSON parsing failed ---")
            print(f"Error details: {e}")
            print(f"Cleaned output before parsing: {cleaned_output}")
            return {
                "answer": "Error: Model did not return a valid JSON string.",
                "description": f"Error parsing JSON. Raw output: {raw_output}",  # Return raw output for debugging
            }
        except Exception as e:
            # Catch other potential unexpected errors during parsing
            print(f"--- Unexpected parsing error ---")
            print(f"Error details: {e}")
            print(traceback.format_exc())  # Print detailed stack trace
            return {
                "answer": f"Error: An unexpected error occurred while parsing model output.",
                "description": f"Error type: {type(e).__name__}, Error message: {e}, Raw output: {raw_output}",
            }

    def summarize_task(
        self,
        instruction: str,
        final_thought: str,
        screenshot_path: str,
        temperature: float = 0.0,  # Lower temperature tends towards more deterministic output
    ) -> dict:
        """
        Processes the user instruction, agent's final thought, and final screenshot
        to generate a task summary by calling the LLM API.

        Args:
            instruction (str): The original task instruction from the user.
            final_thought (str): The agent's last 'thought' before deciding to 'Stop'.
            screenshot_path (str): The file path to the screenshot of the final state.
            temperature (float): Controls the randomness of the LLM's generated response, defaults to 0.0.

        Returns:
            dict: A dictionary containing English keys 'answer' and 'description' summarizing task completion. Returns error info if something goes wrong.
        """
        # Check if the screenshot file exists
        if not os.path.exists(screenshot_path):
            print(f"Error: Screenshot file not found at {screenshot_path}")
            return {
                "answer": "Error: Input error",
                "description": f"Specified screenshot file path not found: {screenshot_path}",
            }

        # Initialize chat history with the English system prompt
        chat_history = self._init_chat_summarize()

        # Construct the prompt text for the user turn
        user_prompt_text = f"User's original instruction:\n{instruction}\n\n"
        user_prompt_text += f"Agent's final thought:\n{final_thought}\n\n"
        user_prompt_text += "Based on the text information above and the provided final screenshot, generate the required JSON response strictly following the instructions."
        user_prompt_text += "You must output a pure JSON object without any additional packaging (like ```json markdown)."
        user_prompt_text += """
Your response format are as follows:
{
        "answer": "Direct summary of task completion status, synthesized using only input information.",
        "description": "Three-part English explanation based only on input information: 1) Analysis of the final screenshot; 2) Analysis of completion degree based on the user instruction; 3) Conclusion derivation."
    }
"""

        # Add the user text and image path to the chat history
        # Note: Requires `add_response` function to correctly handle a list of image paths
        # Format might need adjustment based on the actual implementation of `add_response`
        try:
            # Call add_response to format the user input
            chat_history_with_user_input = add_response(
                role="user",
                prompt=user_prompt_text,
                chat_history=chat_history,
                image=[screenshot_path],  # Pass the list of image paths
            )
            print("--- User prompt and image added to chat history ---")
        except Exception as e:
            print(f"Error adding user response to chat history: {e}")
            print(traceback.format_exc())
            return {
                "answer": "Error: Internal error",
                "description": f"Error preparing API request: {e}",
            }

        # Call the AI model API
        print(f"--- Calling LLM API ({self.model_version}) ---")
        try:
            # Use the imported inference_chat function for the API call
            raw_output = inference_chat(
                chat=chat_history_with_user_input,  # Pass the complete history including system and user input
                model=self.model_version,
                api_url=self.api_url,
                token=self.api_token,
                # temperature=temperature # Pass temperature if API supports it
            )
            print(f"--- LLM API call successful ---")
        except Exception as e:
            # Handle errors during the API call
            print(f"Error calling inference_chat API: {e}")
            print(traceback.format_exc())
            return {
                "answer": "Error: API call failed",
                "description": f"Error calling LLM: {e}",
            }

        # Parse the raw output from the model (expected to be JSON)
        parsed_output = self._parse_model_output(raw_output)

        return parsed_output


def get_screenshot(output_path):
    """Takes a screenshot and saves it to the specified path."""
    try:
        screenshot = pyautogui.screenshot()
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        screenshot.save(output_path)
        print(f"Screenshot saved to: {output_path}")
    except Exception as e:
        print(f"Error taking or saving screenshot: {e}")
    return


def open_app(name):
    print("Action: open %s" % name)
    pyautogui.keyDown(search_key[0])
    pyautogui.keyDown(search_key[1])
    pyautogui.keyUp(search_key[1])
    pyautogui.keyUp(search_key[0])
    time.sleep(0.5)  # Short delay for search box to appear
    if contains_chinese(name):
        pyperclip.copy(name)
        pyautogui.keyDown(ctrl_key)
        pyautogui.keyDown("v")
        pyautogui.keyUp("v")
        pyautogui.keyUp(ctrl_key)
    else:
        pyautogui.typewrite(name, interval=0.05)  # Add slight delay between keys
    time.sleep(1)  # Wait for search results
    pyautogui.press("enter")


def tap(x, y, count=1):
    x, y = x // ratio, y // ratio
    print("Action: click (%d, %d) %d times" % (x, y, count))
    mouse = Controller()
    try:
        pyautogui.moveTo(x, y, duration=0.2)  # Smoother move
        mouse.click(Button.left, count=count)
    except Exception as e:
        print(f"Error during mouse click at ({x}, {y}): {e}")
    return


def shortcut(key1, key2):
    if key1 == "command" and args.pc_type != "mac":
        key1 = "ctrl"
    print("Action: shortcut %s + %s" % (key1, key2))
    try:
        pyautogui.keyDown(key1)
        pyautogui.keyDown(key2)
        pyautogui.keyUp(key2)
        pyautogui.keyUp(key1)
    except Exception as e:
        print(f"Error performing shortcut {key1}+{key2}: {e}")
    return


def presskey(key):
    print("Action: press %s" % key)
    try:
        pyautogui.press(key)
    except Exception as e:
        print(f"Error pressing key {key}: {e}")


def tap_type_enter(x, y, text):
    x, y = x // ratio, y // ratio
    print("Action: click (%d, %d), enter '%s' and press Enter" % (x, y, text))
    try:
        pyautogui.click(x=x, y=y)
        time.sleep(0.2)  # Wait for focus
        if contains_chinese(text):
            pyperclip.copy(text)
            pyautogui.keyDown(ctrl_key)
            pyautogui.keyDown("v")
            pyautogui.keyUp("v")
            pyautogui.keyUp(ctrl_key)
        else:
            pyautogui.typewrite(text, interval=0.05)  # Add slight delay
        time.sleep(0.5)  # Wait before pressing enter
        pyautogui.press("enter")
    except Exception as e:
        print(f"Error during tap_type_enter: {e}")
    return


####################################### Edit your Setting #########################################

if args.instruction != "default":
    instruction = args.instruction
else:
    # Your default instruction
    instruction = "Create a new doc on Word, write a brief introduction of Alibaba, and save the document."
    # instruction = "Help me download the pdf version of the 'Mobile Agent v2' paper on Chrome."

# Your GPT-4o API URL - Use config or args
API_url = args.api_url if args.api_url else config.url

# Your GPT-4o API Token - Use config or args
token = args.api_token if args.api_token else config.token

# Choose between "api" and "local". api: use the qwen api. local: use the local qwen checkpoint
caption_call_method = "api"  # Make this an arg? For now, hardcoded.

# Choose between "qwen-vl-plus" and "qwen-vl-max" if use api method. Choose between "qwen-vl-chat" and "qwen-vl-chat-int4" if use local method.
caption_model = "qwen-vl-max"  # Make this an arg? For now, hardcoded.

# If you choose the api caption call method, input your Qwen api here
qwen_api = args.qwen_api  # Already an arg

# You can add operational knowledge to help Agent operate more accurately.
if args.add_info == "":
    add_info = """
    When searching in the browser, click on the search bar at the top.
    The input field in WeChat is near the send button.
    When downloading files in the browser, it's preferred to use keyboard shortcuts.
    """
else:
    add_info = args.add_info

# Reflection Setting: If you want to improve the operating speed, you can disable the reflection agent. This may reduce the success rate.
reflection_switch = True if not args.disable_reflection else False

# Memory Setting: If you want to improve the operating speed, you can disable the memory unit. This may reduce the success rate.
memory_switch = False  # default: False
###################################################################################################


def get_all_files_in_folder(folder_path):
    """Gets a list of all file names in a given folder."""
    file_list = []
    if not os.path.isdir(folder_path):
        print(f"Warning: Folder not found: {folder_path}")
        return []
    try:
        for file_name in os.listdir(folder_path):
            # Optional: check if it's actually a file
            if os.path.isfile(os.path.join(folder_path, file_name)):
                file_list.append(file_name)
    except Exception as e:
        print(f"Error reading folder {folder_path}: {e}")
    return file_list


def draw_coordinates_on_image(image_path, coordinates, output_image_path):
    """Draws red dots at specified coordinates on an image."""
    try:
        image = Image.open(image_path)
        draw = ImageDraw.Draw(image)
        point_size = 5  # Smaller point size
        for coord in coordinates:
            if (
                not isinstance(coord, (list, tuple))
                or len(coord) != 2
                or not all(isinstance(c, (int, float)) for c in coord)
            ):
                print(
                    f"Warning: Skipping invalid coordinate for drawing point: {coord}"
                )
                continue
            x, y = map(int, coord)
            # Ensure coordinates are within bounds
            x = max(point_size, min(image.width - point_size, x))
            y = max(point_size, min(image.height - point_size, y))
            draw.ellipse(
                (
                    x - point_size,
                    y - point_size,
                    x + point_size,
                    y + point_size,
                ),
                fill="red",
            )
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
        image.save(output_image_path)
        print(f"Saved dot-annotated image to: {output_image_path}")
    except FileNotFoundError:
        print(f"Error: Input image file not found at {image_path}")
    except Exception as e:
        print(f"Error drawing coordinates on image {image_path}: {e}")


def draw_rectangles_on_image(image_path, coordinates, output_image_path):
    """Draws red rectangles on an image."""
    try:
        image = Image.open(image_path)
        draw = ImageDraw.Draw(image)
        width, height = image.size
        for coord in coordinates:
            # Validate coordinates
            if (
                not isinstance(coord, (list, tuple))
                or len(coord) != 4
                or not all(isinstance(c, (int, float)) for c in coord)
            ):
                print(
                    f"Warning: Skipping invalid coordinate for drawing rectangle: {coord}"
                )
                continue

            x1, y1, x2, y2 = map(int, coord)
            # Ensure coordinates are within image bounds and valid rectangle
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(width, x2)
            y2 = min(height, y2)
            if x1 >= x2 or y1 >= y2:
                print(
                    f"Warning: Skipping invalid rectangle dimensions: ({x1},{y1})-({x2},{y2})"
                )
                continue

            draw.rectangle([x1, y1, x2, y2], outline="red", width=2)
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
        image.save(output_image_path)
        print(f"Saved rectangle-annotated image to: {output_image_path}")
    except FileNotFoundError:
        print(f"Error: Input image file not found at {image_path}")
    except Exception as e:
        print(f"Error drawing rectangles on image {image_path}: {e}")


def crop(image_path, box, output_dir, i):
    """Crops a region from an image and saves it."""
    try:
        image = Image.open(image_path)
        # Validate box
        if (
            not isinstance(box, (list, tuple))
            or len(box) != 4
            or not all(isinstance(c, (int, float)) for c in box)
        ):
            print(f"Warning: Invalid box data for cropping: {box}")
            return
        x1, y1, x2, y2 = map(int, box)

        # Basic validation for box dimensions
        if x1 >= x2 - 5 or y1 >= y2 - 5:  # Allow slightly smaller crops
            print(
                f"Warning: Skipping crop due to small dimensions: Box {i} ({x1},{y1})-({x2},{y2})"
            )
            return

        # Ensure coordinates are within image bounds
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(image.width, x2)
        y2 = min(image.height, y2)
        if x1 >= x2 or y1 >= y2:  # Check again after clamping
            print(
                f"Warning: Skipping crop due to invalid dimensions after clamping: Box {i} ({x1},{y1})-({x2},{y2})"
            )
            return

        cropped_image = image.crop((x1, y1, x2, y2))
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        output_filename = os.path.join(output_dir, f"{i}.png")
        cropped_image.save(output_filename)
        # print(f"Saved cropped image {i} to: {output_filename}") # Reduce verbosity
    except FileNotFoundError:
        print(f"Error: Input image file not found at {image_path} for cropping.")
    except Exception as e:
        print(f"Error cropping image {image_path} for box {i}: {e}")


def generate_local(tokenizer, model, image_file, query):
    """Generates text description for an image using a local model."""
    try:
        query_formatted = tokenizer.from_list_format(
            [
                {"image": image_file},
                {"text": query},
            ]
        )
        response, _ = model.chat(tokenizer, query=query_formatted, history=None)
        return response
    except Exception as e:
        print(f"Error generating local caption for {image_file}: {e}")
        return "Error generating caption."


def process_image(image_path, query, qwen_api_key, caption_model_name):
    """Processes a single image using the Qwen API."""
    if not qwen_api_key:
        print("Error: Qwen API key not provided.")
        return "API key missing."
    dashscope.api_key = qwen_api_key
    # Ensure correct file URI format
    if not image_path.startswith("file://"):
        image_uri = "file://" + os.path.abspath(image_path)  # Use absolute path
    else:
        image_uri = image_path

    messages = [
        {
            "role": "user",
            "content": [
                {"image": image_uri},
                {"text": query},
            ],
        }
    ]
    try:
        response = MultiModalConversation.call(
            model=caption_model_name, messages=messages
        )
        # Robust parsing of response
        content = (
            response.get("output", {})
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", [{}])[0]
            .get("text", "No text content found.")
        )
        return content
    except Exception as e:
        print(f"Error calling Qwen API for {image_path}: {e}")
        # print(f"Qwen API Response: {response}") # Debugging
        return "Error during API call."


def generate_api(images, query, qwen_api_key, caption_model_name):
    """Generates descriptions for multiple images concurrently using the Qwen API."""
    icon_map = {}
    if not qwen_api_key:
        print("Error: Qwen API key not provided for generate_api.")
        # Return empty map or map with errors
        for i in range(len(images)):
            icon_map[i + 1] = "API key missing."
        return icon_map

    # Use ThreadPoolExecutor for concurrent API calls
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=5
    ) as executor:  # Limit workers
        # Map future to its original index (1-based)
        future_to_index = {
            executor.submit(
                process_image, image_path, query, qwen_api_key, caption_model_name
            ): i
            + 1
            for i, image_path in enumerate(images)
        }

        for future in concurrent.futures.as_completed(future_to_index):
            index = future_to_index[future]
            try:
                response = future.result()
                icon_map[index] = response
            except Exception as e:
                print(f"Error processing image index {index}: {e}")
                icon_map[index] = "Error processing image."

    return icon_map


def split_image_into_4(input_image_path, output_dir, output_prefix):
    """Splits an image into 4 quadrants and saves them."""
    try:
        img = Image.open(input_image_path)
        width, height = img.size

        # Prevent splitting if image is too small
        if width < 2 or height < 2:
            print(f"Warning: Image {input_image_path} too small to split.")
            return []  # Return empty list if cannot split

        sub_width = width // 2
        sub_height = height // 2

        # Define the 4 quadrants
        quadrants = [
            (0, 0, sub_width, sub_height),  # Top-left
            (sub_width, 0, width, sub_height),  # Top-right
            (0, sub_height, sub_width, height),  # Bottom-left
            (sub_width, sub_height, width, height),  # Bottom-right
        ]

        output_paths = []
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        for i, box in enumerate(quadrants):
            # Ensure box dimensions are valid before cropping
            x1, y1, x2, y2 = box
            if x1 >= x2 or y1 >= y2:
                print(
                    f"Warning: Skipping invalid quadrant {i+1} for image {input_image_path}"
                )
                continue

            sub_img = img.crop(box)
            output_filename = os.path.join(
                output_dir, f"{output_prefix}_part_{i+1}.png"
            )
            sub_img.save(output_filename)
            output_paths.append(output_filename)
            # print(f"Saved split image part {i+1} to: {output_filename}") # Reduce verbosity

        return output_paths  # Return list of created file paths

    except FileNotFoundError:
        print(f"Error: Input image file not found at {input_image_path} for splitting.")
        return []
    except Exception as e:
        print(f"Error splitting image {input_image_path}: {e}")
        return []


# --- OCR and Icon Detection Parallel Functions (Placeholders) ---
# These would ideally use multiprocessing or threading if the underlying
# models/pipelines support it safely and efficiently.
# For simplicity, the main loop currently runs them sequentially per quadrant.
def ocr_parallel(
    img_path,
    ocr_detection,
    ocr_recognition,
    offset_x,
    offset_y,
    total_w,
    total_h,
    padding,
    i,
):
    """Placeholder for parallel OCR processing on an image quadrant."""
    # print(f"Processing OCR for quadrant {i+1} at ({offset_x},{offset_y})") # Reduce verbosity
    sub_text, sub_coordinates = ocr(img_path, ocr_detection, ocr_recognition)
    adjusted_coordinates = []
    for coord in sub_coordinates:
        # Adjust coordinates relative to the full image
        new_coord = [
            int(max(0, offset_x + coord[0] - padding)),
            int(max(0, offset_y + coord[1] - padding)),
            int(min(total_w, offset_x + coord[2] + padding)),
            int(min(total_h, offset_y + coord[3] + padding)),
        ]
        adjusted_coordinates.append(new_coord)

    # Merge within the quadrant's adjusted coordinates
    sub_text_merge, sub_coordinates_merge = merge_boxes_and_texts_new(
        sub_text, adjusted_coordinates
    )
    # print(f"Parallel OCR end for quadrant {i+1}") # Reduce verbosity
    return sub_text_merge, sub_coordinates_merge


def icon_parallel(
    img_path,
    det_func,
    groundingdino_model,
    offset_x,
    offset_y,
    total_w,
    total_h,
    padding,
    i,
):
    """Placeholder for parallel Icon detection processing on an image quadrant."""
    # print(f"Processing Icon Detection for quadrant {i+1} at ({offset_x},{offset_y})") # Reduce verbosity
    sub_coordinates = det_func(
        img_path, "icon", groundingdino_model
    )  # Assuming det is passed
    adjusted_coordinates = []
    for coord in sub_coordinates:
        # Adjust coordinates relative to the full image
        new_coord = [
            int(max(0, offset_x + coord[0] - padding)),
            int(max(0, offset_y + coord[1] - padding)),
            int(min(total_w, offset_x + coord[2] + padding)),
            int(min(total_h, offset_y + coord[3] + padding)),
        ]
        adjusted_coordinates.append(new_coord)

    # Merge within the quadrant's adjusted coordinates
    sub_coordinates_merge = merge_all_icon_boxes(adjusted_coordinates)
    # print(f"Parallel Icon Detection end for quadrant {i+1}") # Reduce verbosity
    return sub_coordinates_merge


# --- End Placeholders ---


def get_perception_infos(
    screenshot_file, screenshot_som_file, font_path, screenshot_base_dir, temp_files_dir
):
    """
    Captures screenshot, performs OCR and icon detection (potentially in parallel),
    annotates image, and returns structured perception info.

    Args:
        screenshot_file (str): Path to save the main screenshot.
        screenshot_som_file (str): Path to save the annotated screenshot.
        font_path (str): Path to the font file for annotations.
        screenshot_base_dir (str): Base directory for saving screenshot parts.
        temp_files_dir (str): Directory for temporary files like cropped icons.

    Returns:
        tuple: (perception_infos, width, height) or (None, None, None) on error.
    """
    print("--- Getting Perception Infos ---")
    try:
        get_screenshot(screenshot_file)  # Save screenshot to the correct path
        if not os.path.exists(screenshot_file):
            print("Error: Screenshot failed to save.")
            return None, None, None

        total_width, total_height = Image.open(screenshot_file).size
        print(f"Screenshot dimensions: {total_width}x{total_height}")

        # Define paths for split images within the screenshot directory
        split_image_prefix = os.path.splitext(os.path.basename(screenshot_file))[
            0
        ]  # e.g., "screenshot"
        img_list = split_image_into_4(
            screenshot_file, screenshot_base_dir, split_image_prefix
        )

        if not img_list:
            print("Error: Failed to split screenshot into parts.")
            # Fallback: process the whole image? Or return error?
            # For now, return error. Could add fallback later.
            return None, None, None

        # Define offsets for each quadrant
        img_x_list = [0, total_width / 2, 0, total_width / 2]
        img_y_list = [0, 0, total_height / 2, total_height / 2]

        all_texts = []
        all_text_coordinates = []
        all_icon_coordinates = []
        padding = total_height * 0.0025  # Padding based on height

        # --- Sequential Processing per Quadrant (Replace with parallel calls if implemented) ---
        print("Starting sequential OCR and Icon Detection per quadrant...")
        for i, img_path in enumerate(img_list):
            # print(f"Processing quadrant {i+1}: {img_path}") # Reduce verbosity
            offset_x, offset_y = img_x_list[i], img_y_list[i]

            # --- OCR ---
            try:
                sub_text, sub_coordinates = ocr_parallel(
                    img_path,
                    ocr_detection,
                    ocr_recognition,
                    offset_x,
                    offset_y,
                    total_width,
                    total_height,
                    padding,
                    i,
                )
                all_texts.extend(sub_text)
                all_text_coordinates.extend(sub_coordinates)
                # print(f"Quadrant {i+1} OCR done.") # Reduce verbosity
            except Exception as e:
                print(f"Error during OCR for quadrant {i+1} ({img_path}): {e}")

            # --- Icon Detection ---
            try:
                sub_icon_coords = icon_parallel(
                    img_path,
                    det,
                    groundingdino_model,
                    offset_x,
                    offset_y,
                    total_width,
                    total_height,
                    padding,
                    i,
                )
                all_icon_coordinates.extend(sub_icon_coords)
                # print(f"Quadrant {i+1} Icon Detection done.") # Reduce verbosity
            except Exception as e:
                print(
                    f"Error during Icon Detection for quadrant {i+1} ({img_path}): {e}"
                )

        # --- Merge results from all quadrants ---
        print("Merging results from all quadrants...")
        # Merge text results globally
        merged_text, merged_text_coordinates = merge_boxes_and_texts(
            all_texts, all_text_coordinates
        )
        # Merge icon results globally
        merged_icon_coordinates = merge_all_icon_boxes(all_icon_coordinates)
        print(
            f"Found {len(merged_text)} merged text boxes and {len(merged_icon_coordinates)} merged icon boxes."
        )

        # --- Draw Annotations ---
        print("Drawing annotations...")
        if args.draw_text_box == 1:
            rec_list = merged_text_coordinates + merged_icon_coordinates
            draw_coordinates_boxes_on_image(
                screenshot_file, copy.deepcopy(rec_list), screenshot_som_file, font_path
            )
        else:
            draw_coordinates_boxes_on_image(
                screenshot_file,
                copy.deepcopy(merged_icon_coordinates),
                screenshot_som_file,
                font_path,
            )
        print("Annotations drawn.")

        # --- Format Perception Info ---
        print("Formatting perception info...")
        mark_number = 0
        perception_infos = []

        # Add text info
        for i in range(len(merged_text_coordinates)):
            mark_number += (
                1  # Increment for every element if drawing all boxes or just icons
            )
            text_content = (
                merged_text[i] if i < len(merged_text) else "Text N/A"
            )  # Safety check
            coord_content = merged_text_coordinates[i]

            if args.use_som == 1 and args.draw_text_box == 1:
                perception_info = {
                    "text": f"mark number: {mark_number} text: {text_content}",
                    "coordinates": coord_content,
                }
            else:
                perception_info = {
                    "text": f"text: {text_content}",
                    "coordinates": coord_content,
                }
            perception_infos.append(perception_info)

        # Add icon info
        icon_start_mark_number = mark_number  # Where icon numbering starts
        for i in range(len(merged_icon_coordinates)):
            if (
                args.use_som == 1
            ):  # Only increment mark number if SOM is used (regardless of draw_text_box)
                mark_number += 1
                current_mark = mark_number
                perception_info = {
                    "text": f"mark number: {current_mark} icon",  # Text includes mark number
                    "coordinates": merged_icon_coordinates[i],
                    "is_icon": True,  # Add flag for easier processing later
                    "original_index": i,  # Keep track of original icon index if needed
                }
            else:
                perception_info = {
                    "text": "icon",  # Text does not include mark number if SOM not used
                    "coordinates": merged_icon_coordinates[i],
                    "is_icon": True,
                    "original_index": i,
                }
            perception_infos.append(perception_info)

        # --- Icon Captioning (if enabled) ---
        if args.icon_caption == 1:
            print("Starting icon captioning...")
            # Ensure temp directory is clean before cropping
            if os.path.exists(temp_files_dir):
                shutil.rmtree(temp_files_dir)
            os.makedirs(temp_files_dir)

            icon_perception_indices = (
                []
            )  # Store indices in perception_infos that are icons
            icon_boxes_to_crop = []

            # Iterate through perception_infos to find icons and their original boxes
            for idx, info in enumerate(perception_infos):
                if info.get("is_icon"):
                    # Find the corresponding original coordinate before potential centering
                    original_icon_index = info.get("original_index")
                    if original_icon_index is not None and original_icon_index < len(
                        merged_icon_coordinates
                    ):
                        icon_box = merged_icon_coordinates[original_icon_index]
                        icon_boxes_to_crop.append(icon_box)
                        icon_perception_indices.append(
                            idx
                        )  # Store the index within perception_infos
                        # Crop the icon using its original index for filename uniqueness
                        crop(
                            screenshot_file, icon_box, temp_files_dir, idx
                        )  # Use perception_info index for filename
                    else:
                        print(
                            f"Warning: Could not find original coordinate for icon at index {idx}"
                        )

            # Get cropped image files (filenames are based on perception_infos index)
            cropped_images_files = get_all_files_in_folder(temp_files_dir)
            if cropped_images_files:
                # Sort files based on the numeric part of the filename (perception_infos index)
                cropped_images_files.sort(key=lambda x: int(os.path.splitext(x)[0]))
                # Create full paths
                cropped_image_paths = [
                    os.path.join(temp_files_dir, f) for f in cropped_images_files
                ]
                # Extract the original perception_infos indices from filenames
                current_icon_indices = [
                    int(os.path.splitext(f)[0]) for f in cropped_images_files
                ]

                icon_map = {}  # Maps 1-based index of *processed* icons to description
                prompt = "This image is an icon from a computer screen. Please briefly describe the shape and color of this icon in one sentence."

                if caption_call_method == "local":
                    print("Generating icon captions locally...")
                    # Ensure model and tokenizer are loaded if using local method
                    if "model" not in locals() or "tokenizer" not in locals():
                        print("Error: Local caption model/tokenizer not loaded.")
                    else:
                        for i, img_path in enumerate(cropped_image_paths):
                            try:
                                icon_width, icon_height = Image.open(img_path).size
                                # Filter out potentially large background crops
                                if (
                                    icon_height > 0.8 * total_height
                                    or icon_width * icon_height
                                    > 0.2 * total_width * total_height
                                ):
                                    des = "Cropped area too large, likely background."
                                else:
                                    des = generate_local(
                                        tokenizer, model, img_path, prompt
                                    )
                            except Exception as e:
                                print(
                                    f"Error processing local caption for {img_path}: {e}"
                                )
                                des = "Error generating local caption."
                            icon_map[i + 1] = des  # Map 1-based index to description
                elif caption_call_method == "api":
                    print("Generating icon captions via API...")
                    if not qwen_api:
                        print("Warning: Qwen API key not provided for icon captioning.")
                        # Fill map with error messages
                        for i in range(len(cropped_image_paths)):
                            icon_map[i + 1] = "API key missing for captioning."
                    else:
                        # Call API concurrently
                        icon_map = generate_api(
                            cropped_image_paths, prompt, qwen_api, caption_model
                        )
                else:
                    print(f"Error: Invalid caption_call_method: {caption_call_method}")

                # Update perception_infos with captions
                print("Updating perception info with captions...")
                processed_icon_count = 0
                for i, perception_idx in enumerate(
                    current_icon_indices
                ):  # Iterate using the indices from filenames
                    caption_result = icon_map.get(
                        i + 1
                    )  # Get caption using 1-based index
                    if perception_idx < len(perception_infos) and caption_result:
                        # Append caption, handling potential errors
                        if (
                            "Error" not in caption_result
                            and "API key missing" not in caption_result
                            and "No text content found" not in caption_result
                        ):
                            perception_infos[perception_idx][
                                "text"
                            ] += f": {caption_result}"
                            processed_icon_count += 1
                        else:
                            # Optionally add error note or keep original text
                            perception_infos[perception_idx][
                                "text"
                            ] += f": [Captioning Failed: {caption_result}]"
                    else:
                        print(
                            f"Warning: Mismatch or missing caption for icon index {perception_idx}"
                        )

                print(f"Successfully added captions for {processed_icon_count} icons.")

        # --- Adjust Coordinates Based on location_info ---
        print(
            f"Adjusting coordinates based on location_info: '{args.location_info}'..."
        )
        if args.location_info == "center":
            for i in range(len(perception_infos)):
                coord = perception_infos[i]["coordinates"]
                # Check if it's already a center point (list of 2) or a box (list of 4)
                if isinstance(coord, (list, tuple)) and len(coord) == 4:
                    perception_infos[i]["coordinates"] = [
                        int((coord[0] + coord[2]) / 2),
                        int((coord[1] + coord[3]) / 2),
                    ]
        elif args.location_info == "icon_center":
            for i in range(len(perception_infos)):
                # Check if it's an icon and has a bounding box
                if (
                    perception_infos[i].get("is_icon")
                    and isinstance(perception_infos[i]["coordinates"], (list, tuple))
                    and len(perception_infos[i]["coordinates"]) == 4
                ):
                    coord = perception_infos[i]["coordinates"]
                    perception_infos[i]["coordinates"] = [
                        int((coord[0] + coord[2]) / 2),
                        int((coord[1] + coord[3]) / 2),
                    ]
        elif args.location_info == "bbox":
            pass  # Keep bounding boxes as they are
        else:
            print(
                f"Warning: Unknown location_info '{args.location_info}'. Keeping original coordinates."
            )

        print("--- Perception Info Generation Complete ---")
        return perception_infos, total_width, total_height

    except Exception as e:
        print(f"Error in get_perception_infos: {e}")
        print(traceback.format_exc())
        return None, None, None


### Load caption model ###
# Conditional loading based on caption_call_method
if args.icon_caption == 1 and caption_call_method == "local":
    print("Loading local caption model...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    torch.manual_seed(1234)
    try:
        if caption_model == "qwen-vl-chat":
            model_dir_name = "qwen/Qwen-VL-Chat"
            revision = "v1.1.0"
            model_dir = snapshot_download(model_dir_name, revision=revision)
            model = AutoModelForCausalLM.from_pretrained(
                model_dir,
                device_map="auto",
                trust_remote_code=True,  # Use auto device map
            ).eval()
            tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
            model.generation_config = GenerationConfig.from_pretrained(
                model_dir, trust_remote_code=True
            )
            print(f"Loaded {model_dir_name} model and tokenizer.")
        elif caption_model == "qwen-vl-chat-int4":
            model_dir_name = "qwen/Qwen-VL-Chat-Int4"
            revision = "v1.0.0"
            qwen_dir = snapshot_download(model_dir_name, revision=revision)
            model = AutoModelForCausalLM.from_pretrained(
                qwen_dir,
                device_map="auto",
                trust_remote_code=True,
                use_safetensors=True,  # Use auto device map
            ).eval()
            tokenizer = AutoTokenizer.from_pretrained(qwen_dir, trust_remote_code=True)
            model.generation_config = GenerationConfig.from_pretrained(
                qwen_dir, trust_remote_code=True, do_sample=False
            )
            print(f"Loaded {model_dir_name} model and tokenizer.")
        else:
            print(
                f'Error: If using local caption method, choose caption model from "qwen-vl-chat" or "qwen-vl-chat-int4". Got: {caption_model}'
            )
            # Decide how to handle: exit or disable captioning?
            args.icon_caption = 0  # Disable captioning if model load fails
            print("Disabling icon captioning due to model load error.")
            # exit(1)
    except Exception as e:
        print(f"Error loading local caption model '{caption_model}': {e}")
        args.icon_caption = 0  # Disable captioning on error
        print("Disabling icon captioning due to model load error.")
elif args.icon_caption == 1 and caption_call_method == "api":
    print("Using API for icon captioning. Ensure Qwen API key is set via --qwen_api.")
    if not args.qwen_api:
        print(
            "Warning: --qwen_api key is not provided. API captioning will likely fail."
        )
    pass  # No local model loading needed
elif args.icon_caption == 1:
    print(
        f"Error: Invalid caption_call_method: '{caption_call_method}'. Must be 'local' or 'api'."
    )
    args.icon_caption = 0  # Disable captioning
    print("Disabling icon captioning due to invalid method.")


### Load ocr and icon detection model ###
# These should be loaded regardless of captioning settings
try:
    print("Loading OCR and GroundingDINO models...")
    # GroundingDINO
    groundingdino_dir = snapshot_download(
        "AI-ModelScope/GroundingDINO", revision="v1.0.0"
    )
    # Ensure device is set correctly for the pipeline if needed, e.g., device=0 for GPU
    groundingdino_model = pipeline(
        "grounding-dino-task", model=groundingdino_dir
    )  # Add device='cuda:0' if GPU needed
    print("GroundingDINO model loaded.")

    # OCR Detection
    ocr_detection = pipeline(
        Tasks.ocr_detection,
        model="damo/cv_resnet18_ocr-detection-line-level_damo",  # Add device='cuda:0' if GPU needed
    )
    print("OCR Detection model loaded.")

    # OCR Recognition
    ocr_recognition = pipeline(
        Tasks.ocr_recognition,
        model="damo/cv_convnextTiny_ocr-recognition-document_damo",  # Add device='cuda:0' if GPU needed
    )
    print("OCR Recognition model loaded.")
    print("OCR and GroundingDINO models loaded successfully.")
except Exception as e:
    print(f"Fatal Error: Failed to load OCR or GroundingDINO models: {e}")
    print(traceback.format_exc())
    exit(1)  # Exit if core perception models fail to load


# --- Initialize Histories and State ---
thought_history = []
summary_history = []
action_history = []
reflection_thought = ""
summary = ""
action = ""
completed_requirements = ""
memory = ""
insight = ""  # Seems unused, maybe remove?
error_flag = False
task_completed_successfully = False  # Flag to track successful completion via "Stop"

# --- Clean/Prepare Temp Directory ---
# temp_dir is now defined within the atomic_task_dir_path
if os.path.exists(temp_dir):
    try:
        shutil.rmtree(temp_dir)
        # print(f"Cleaned temporary directory: {temp_dir}") # Reduce verbosity
    except Exception as e:
        print(f"Warning: Could not remove temp directory {temp_dir}: {e}")
try:
    os.makedirs(temp_dir, exist_ok=True)
    # print(f"Ensured temporary directory exists: {temp_dir}") # Reduce verbosity
except Exception as e:
    print(f"Error creating temp directory {temp_dir}: {e}")
    # Decide if this is fatal
    # exit(1)


# --- Main Execution Loop ---
iter = 0
max_iters = 20  # Add a max iteration limit to prevent infinite loops
while iter < max_iters:
    iter += 1
    print(f"\n{'='*30} Iteration {iter} {'='*30}")

    # Define screenshot paths for this iteration using screenshot_dir (now inside atomic_task_dir_path)
    screenshot_file = os.path.join(screenshot_dir, f"screenshot_iter_{iter}.png")
    screenshot_som_file = os.path.join(
        screenshot_dir, f"screenshot_som_iter_{iter}.png"
    )

    # --- Perception Step ---
    print("--- Step: Perception ---")
    perception_infos, width, height = get_perception_infos(
        screenshot_file,
        screenshot_som_file,
        args.font_path,
        screenshot_dir,  # Pass the correct screenshot dir
        temp_dir,  # Pass the correct temp dir
    )

    # Clean temp dir after perception infos are generated and captions (if any) are done
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
            os.makedirs(temp_dir)  # Recreate for next iteration if needed
        except Exception as e:
            print(
                f"Warning: Could not clean temp directory {temp_dir} after perception: {e}"
            )

    if perception_infos is None:
        print("Error: Failed to get perception info. Stopping execution.")
        break  # Exit loop if perception fails

    # --- Action Step ---
    print("--- Step: Action Planning ---")
    prompt_action = get_action_prompt(
        instruction,
        perception_infos,
        width,
        height,
        thought_history,
        summary_history,
        action_history,
        summary,  # Previous summary
        action,  # Previous action
        reflection_thought,  # Previous reflection
        add_info,
        error_flag,
        completed_requirements,
        memory,
        args.use_som,
        args.icon_caption,
        args.location_info,
    )
    chat_action = init_action_chat()
    image_paths_for_action = [screenshot_file]
    if args.use_som == 1 and os.path.exists(
        screenshot_som_file
    ):  # Check if SOM file exists
        image_paths_for_action.append(screenshot_som_file)

    chat_action = add_response(
        "user", prompt_action, chat_action, image_paths_for_action
    )

    try:
        output_action = inference_chat(chat_action, vl_model_version, API_url, token)
    except Exception as e:
        print(f"Error during action inference call: {e}")
        print(traceback.format_exc())
        # Decide how to handle: retry, stop, etc. For now, stop.
        break

    # --- Parse Action Output ---
    try:
        thought = (
            output_action.split("### Thought ###")[-1]
            .split("### Action ###")[0]
            .strip()
        )
        action = (
            output_action.split("### Action ###")[-1]
            .split("### Operation ###")[0]
            .strip()
        )
        summary = output_action.split(  # This is the agent's summary of its own action/state, not the final task summary
            "### Operation ###"
        )[
            -1
        ].strip()
    except IndexError:
        print("Error: Could not parse Thought/Action/Operation from model output:")
        print(output_action)
        action = "Stop"  # Default to Stop on parsing error
        thought = "Error parsing output."
        summary = "Error parsing output."
        error_flag = True  # Mark error

    chat_action = add_response(
        "assistant", output_action, chat_action
    )  # Add assistant response to history

    status_header = f" Decision (Iter {iter}) "
    print(f"\n{'#'*20}{status_header}{'#'*20}")
    print(f"Thought: {thought}")
    print(f"Action: {action}")
    print(f"Operation Summary: {summary}")
    print(f"{'#'*(40 + len(status_header))}\n")

    # --- Execute Action ---
    print("--- Step: Action Execution ---")
    action_executed = False
    if "Stop" in action:
        print("Action: Stop received. Ending task.")
        task_completed_successfully = True  # Set flag on successful stop
        action_executed = True
        break  # Exit the main loop

    elif "Double Tap" in action:
        try:
            coordinate = re.search(r"\((.*?)\)", action).group(1).split(",")
            x, y = int(coordinate[0].strip()), int(coordinate[1].strip())
            tap(x, y, 2)
            action_executed = True
        except Exception as e:
            print(f"Error parsing/executing Double Tap: {e}")
    elif "Triple Tap" in action:
        try:
            coordinate = re.search(r"\((.*?)\)", action).group(1).split(",")
            x, y = int(coordinate[0].strip()), int(coordinate[1].strip())
            tap(x, y, 3)
            action_executed = True
        except Exception as e:
            print(f"Error parsing/executing Triple Tap: {e}")
    elif "Tap" in action:  # Must be checked after Double/Triple
        try:
            coordinate = re.search(r"\((.*?)\)", action).group(1).split(",")
            x, y = int(coordinate[0].strip()), int(coordinate[1].strip())
            tap(x, y, 1)
            action_executed = True
        except Exception as e:
            print(f"Error parsing/executing Tap: {e}")
    elif "Shortcut" in action:
        try:
            keys = re.search(r"\((.*?)\)", action).group(1).split(",")
            key1, key2 = keys[0].strip().lower(), keys[1].strip().lower()
            shortcut(key1, key2)
            action_executed = True
        except Exception as e:
            print(f"Error parsing/executing Shortcut: {e}")
    elif "Press" in action:
        try:
            key = re.search(r"\((.*?)\)", action).group(1).strip()
            presskey(key)
            action_executed = True
        except Exception as e:
            print(f"Error parsing/executing Press: {e}")
    elif "Open App" in action:
        try:
            app = re.search(r"\((.*?)\)", action).group(1).strip()
            open_app(app)
            action_executed = True
        except Exception as e:
            print(f"Error parsing/executing Open App: {e}")
    elif "Type" in action:
        try:
            coords_match = re.search(r"\((.*?)\)", action)
            text_match = re.search(r"\[(.*?)\]", action) or re.search(
                r"\"(.*?)\"", action
            )  # Handle both [] and ""
            if coords_match and text_match:
                coordinate = coords_match.group(1).split(",")
                x, y = int(coordinate[0].strip()), int(coordinate[1].strip())
                text_to_type = text_match.group(1).strip()
                tap_type_enter(x, y, text_to_type)
                action_executed = True
            else:
                print("Error: Could not parse coordinates or text for Type action.")
        except Exception as e:
            print(f"Error parsing/executing Type: {e}")
    else:
        print(f"Warning: Unrecognized action: {action}. Treating as error.")
        error_flag = True  # Set error flag if action is unknown

    if not action_executed and not error_flag:
        print(
            "Warning: Action specified but not executed due to parsing error or unknown type."
        )
        error_flag = True  # Treat failure to execute as an error state

    # --- Wait for UI to Update ---
    print("Waiting for UI to update...")
    time.sleep(3)  # Increased wait time slightly

    # --- Memory Step (Optional) ---
    if memory_switch:
        print("--- Step: Memory Update ---")
        # Assuming 'insight' should come from reflection or action phase?
        # If 'insight' isn't updated, memory prompt might be static.
        # For now, using the last 'thought' as potential insight.
        current_insight = thought
        prompt_memory = get_memory_prompt(current_insight)
        # Memory uses the *action* chat history potentially
        chat_memory = add_response(
            "user", prompt_memory, chat_action
        )  # Append to action chat
        try:
            output_memory = inference_chat(
                chat_memory, vl_model_version, API_url, token
            )
            # chat_memory = add_response("assistant", output_memory, chat_memory) # Add response
            status_header = f" Memory (Iter {iter}) "
            print(f"\n{'#'*20}{status_header}{'#'*20}")
            print(output_memory)
            print(f"{'#'*(40 + len(status_header))}\n")

            # Extract important content for memory
            try:
                extracted_memory = (
                    output_memory.split("### Important content ###")[-1]
                    .split("\n\n")[0]  # Take first paragraph after marker
                    .strip()
                )
                if (
                    "None" not in extracted_memory and extracted_memory
                ):  # Check if not None and not empty
                    if extracted_memory not in memory:  # Avoid duplicates
                        memory += extracted_memory + "\n"
                        print(f"Added to memory: {extracted_memory}")
                    else:
                        print("Memory content already exists.")
                else:
                    print("No new important content identified for memory.")
            except IndexError:
                print("Could not parse important content from memory output.")

        except Exception as e:
            print(f"Error during memory inference call: {e}")
            print(traceback.format_exc())
        # Update chat_action history if memory was added to it
        # chat_action = chat_memory # Persist memory Q&A in action history? Or keep separate?

    # --- Prepare for Next Iteration / Reflection ---
    # Store current state before getting new perception
    last_perception_infos = copy.deepcopy(perception_infos)
    last_screenshot_file = os.path.join(
        screenshot_dir, f"screenshot_iter_{iter}_prev.png"
    )  # Rename previous
    last_screenshot_som_file = os.path.join(
        screenshot_dir, f"screenshot_som_iter_{iter}_prev.png"
    )

    try:
        if os.path.exists(screenshot_file):
            os.rename(screenshot_file, last_screenshot_file)
        if args.use_som == 1 and os.path.exists(screenshot_som_file):
            os.rename(screenshot_som_file, last_screenshot_som_file)
    except OSError as e:
        print(f"Warning: Could not rename previous screenshot files: {e}")

    # --- Reflection Step (Optional) ---
    if reflection_switch:
        print("--- Step: Reflection ---")
        # Need the *next* state screenshot for reflection
        next_screenshot_file = os.path.join(
            screenshot_dir, f"screenshot_iter_{iter+1}_pre.png"
        )  # Temp name for reflection screenshot
        get_screenshot(next_screenshot_file)  # Take screenshot *after* action

        if not os.path.exists(next_screenshot_file):
            print(
                "Error: Failed to get screenshot for reflection. Skipping reflection."
            )
            reflection_thought = "Skipped due to missing screenshot."
            # Decide how to proceed: treat as error? Continue without reflection?
            # For now, continue but potentially set error flag or use default logic below.
            error_flag = True  # Assume error if reflection fails critically
        else:
            # Reflection needs perception info from *before* and *after* the action
            # We have last_perception_infos (before action)
            # We need perception_infos for the state *after* the action (next_screenshot_file)
            print("Getting perception info for reflection (post-action state)...")
            # Need a temporary SOM file path for this reflection perception
            reflection_som_file = os.path.join(
                screenshot_dir, f"screenshot_som_iter_{iter+1}_reflection.png"
            )
            reflection_perception_infos, _, _ = get_perception_infos(
                next_screenshot_file,
                reflection_som_file,
                args.font_path,
                screenshot_dir,  # Pass correct screenshot dir
                temp_dir,  # Pass correct temp dir
            )
            # Clean temp dir after reflection perception
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    os.makedirs(temp_dir)
                except Exception as e:
                    print(
                        f"Warning: Could not clean temp directory {temp_dir} after reflection perception: {e}"
                    )

            if reflection_perception_infos is None:
                print(
                    "Error: Failed to get post-action perception info for reflection. Skipping."
                )
                reflection_thought = "Skipped due to missing post-action perception."
                error_flag = True
            else:
                prompt_reflect = get_reflect_prompt(
                    instruction,
                    last_perception_infos,  # State before action
                    reflection_perception_infos,  # State after action
                    width,  # Use width/height from previous state? Or recalculate? Assume previous.
                    height,
                    summary,  # Agent's summary of the action taken
                    action,  # The action taken
                    add_info,
                )
                chat_reflect = init_reflect_chat()
                # Reflection uses screenshots from before (last) and after (next) the action
                reflect_image_paths = []
                if os.path.exists(last_screenshot_file):
                    reflect_image_paths.append(last_screenshot_file)
                if os.path.exists(next_screenshot_file):
                    reflect_image_paths.append(next_screenshot_file)
                # Optionally add SOM images if they exist and are useful for reflection
                # if os.path.exists(last_screenshot_som_file): reflect_image_paths.append(last_screenshot_som_file)
                # if os.path.exists(reflection_som_file): reflect_image_paths.append(reflection_som_file)

                if len(reflect_image_paths) < 2:
                    print(
                        "Warning: Missing screenshots for reflection prompt. Reflection might be inaccurate."
                    )

                chat_reflect = add_response(
                    "user",
                    prompt_reflect,
                    chat_reflect,
                    reflect_image_paths,
                )

                try:
                    output_reflect = inference_chat(
                        chat_reflect, vl_model_version, API_url, token
                    )
                    reflection_thought = (
                        output_reflect.split("### Thought ###")[-1]
                        .split("### Answer ###")[0]
                        .strip()
                    )
                    reflect_answer = output_reflect.split("### Answer ###")[
                        -1
                    ].strip()  # A, B, or C
                    # chat_reflect = add_response("assistant", output_reflect, chat_reflect) # Add response
                    status_header = f" Reflection (Iter {iter}) "
                    print(f"\n{'#'*20}{status_header}{'#'*20}")
                    print(f"Reflection Thought: {reflection_thought}")
                    print(f"Reflection Answer: {reflect_answer}")
                    print(f"{'#'*(40 + len(status_header))}\n")

                    # --- Planning Step (Triggered based on Reflection) ---
                    # Planning happens *after* reflection determines success/failure
                    if "A" in reflect_answer:  # Action successful
                        print("--- Step: Planning (Post-Reflection - Success) ---")
                        thought_history.append(thought)  # Add successful thought/action
                        summary_history.append(summary)
                        action_history.append(action)
                        error_flag = False  # Clear error flag on success

                        prompt_planning = get_process_prompt(
                            instruction,
                            thought_history,
                            summary_history,
                            action_history,
                            completed_requirements,  # Pass current completed state
                            add_info,
                        )
                        chat_planning = (
                            init_memory_chat()
                        )  # Use memory chat setup for planning?
                        chat_planning = add_response(
                            "user", prompt_planning, chat_planning
                        )
                        try:
                            output_planning = inference_chat(
                                chat_planning,
                                llm_model_version,
                                API_url,
                                token,  # Use LLM for planning
                            )
                            # chat_planning = add_response("assistant", output_planning, chat_planning)
                            status_header = f" Planning (Iter {iter}) "
                            print(f"\n{'#'*20}{status_header}{'#'*20}")
                            print(output_planning)
                            print(f"{'#'*(40 + len(status_header))}\n")
                            # Update completed requirements based on planning output
                            try:
                                completed_requirements = output_planning.split(
                                    "### Completed contents ###"
                                )[-1].strip()
                                print(
                                    f"Updated Completed Requirements: {completed_requirements}"
                                )
                            except IndexError:
                                print(
                                    "Could not parse completed requirements from planning output."
                                )
                        except Exception as e:
                            print(f"Error during planning inference call: {e}")
                            # How to handle planning failure? Maybe try again or stop?

                    elif (
                        "B" in reflect_answer or "C" in reflect_answer
                    ):  # Action failed or needs retry
                        print(
                            "--- Step: Planning (Post-Reflection - Failure/Retry) ---"
                        )
                        print(
                            f"Reflection indicates issue ({reflect_answer}). Previous action might be reverted or retried."
                        )
                        error_flag = True
                        # Do not add the failed action to history? Or add with error?
                        # Current logic doesn't add failed actions to history used for planning.
                        # Consider if planning needs info about the failure.
                        # Maybe press 'esc' to cancel dialogs?
                        # presskey('esc') # Optional: try to escape potential error states
                        # Planning might still run to reassess based on the error
                        prompt_planning = get_process_prompt(
                            instruction,
                            thought_history,  # History without the failed action
                            summary_history,
                            action_history,
                            completed_requirements,
                            add_info,
                        )
                        # ... (rest of planning logic as above) ...
                        # For now, just set error flag and let next iteration's Action handle it.
                        print("Error flag set. Next iteration will reconsider action.")

                    else:
                        print(
                            f"Warning: Unrecognized reflection answer: {reflect_answer}. Assuming success."
                        )
                        # Default to success logic if answer is unclear
                        thought_history.append(thought)
                        summary_history.append(summary)
                        action_history.append(action)
                        error_flag = False
                        # ... (planning logic for success case) ...

                except Exception as e:
                    print(f"Error during reflection inference call: {e}")
                    print(traceback.format_exc())
                    error_flag = True  # Assume error if reflection fails
                    reflection_thought = "Reflection failed due to API error."

            # Clean up reflection-specific screenshots
            # try:
            #     if os.path.exists(next_screenshot_file): os.remove(next_screenshot_file)
            #     if os.path.exists(reflection_som_file): os.remove(reflection_som_file)
            # except OSError as e:
            #     print(f"Warning: Could not remove reflection screenshots: {e}")

    else:  # --- Planning Step (No Reflection) ---
        # If reflection is off, always assume action was 'successful' for history purposes
        # and run planning to update completed requirements.
        print("--- Step: Planning (No Reflection) ---")
        thought_history.append(thought)
        summary_history.append(summary)
        action_history.append(action)
        error_flag = False  # Assume success if no reflection

        prompt_planning = get_process_prompt(
            instruction,
            thought_history,
            summary_history,
            action_history,
            completed_requirements,
            add_info,
        )
        chat_planning = init_memory_chat()
        chat_planning = add_response("user", prompt_planning, chat_planning)
        try:
            output_planning = inference_chat(
                chat_planning, llm_model_version, API_url, token
            )
            # chat_planning = add_response("assistant", output_planning, chat_planning)
            status_header = f" Planning (Iter {iter}) "
            print(f"\n{'#'*20}{status_header}{'#'*20}")
            print(output_planning)
            print(f"{'#'*(40 + len(status_header))}\n")
            try:
                completed_requirements = output_planning.split(
                    "### Completed contents ###"
                )[-1].strip()
                print(f"Updated Completed Requirements: {completed_requirements}")
            except IndexError:
                print("Could not parse completed requirements from planning output.")
        except Exception as e:
            print(f"Error during planning inference call (no reflection): {e}")

    # Clean up the renamed previous screenshots from this iteration
    try:
        if os.path.exists(last_screenshot_file):
            os.remove(last_screenshot_file)
        if os.path.exists(last_screenshot_som_file):
            os.remove(last_screenshot_som_file)
    except OSError as e:
        print(f"Warning: Could not remove renamed previous screenshots: {e}")

# --- End of Main Loop ---

if iter >= max_iters:
    print(f"\nExecution stopped: Reached maximum iteration limit ({max_iters}).")

# <<< MODIFIED: Section to output result as JSON upon successful completion >>>
# This section now uses the `atomic_task_dir_path` defined earlier.
if task_completed_successfully:
    print(
        "\n"
        + "=" * 30
        + " Task Completed Successfully - Generating Summary "
        + "=" * 30
    )
    # --- Initialize and use TaskSummarizer ---
    summarizer_api_url = API_url  # Use the same API URL
    summarizer_api_token = token  # Use the same token
    summarizer_model_version = vl_model_version  # Use the same VL model for summary

    summarizer = TaskSummarizer(
        api_url=summarizer_api_url,
        api_token=summarizer_api_token,
        model_version=summarizer_model_version,
    )

    # Prepare inputs for summarization
    # The last successful screenshot path needs to be determined correctly.
    # It should be the screenshot *before* the "Stop" action was decided.
    # If reflection was on, it might be `last_screenshot_file`. If off, it's `screenshot_file` from the final loop.
    # Let's assume `screenshot_file` holds the path from the last successful perception step before Stop.
    final_screenshot_path = (
        screenshot_file
        if "screenshot_file" in locals() and os.path.exists(screenshot_file)
        else None
    )
    # If reflection was used, the state *before* reflection might be more accurate:
    if (
        reflection_switch
        and "last_screenshot_file" in locals()
        and os.path.exists(last_screenshot_file)
    ):
        final_screenshot_path = last_screenshot_file

    # Get the final thought that led to the "Stop" action
    final_agent_thought = (
        thought if "thought" in locals() else "Final thought not recorded"
    )

    if final_screenshot_path:
        print(
            f"Summarization inputs: Instruction='{instruction[:50]}...', Final Thought='{final_agent_thought[:50]}...', Screenshot='{final_screenshot_path}'"
        )

        # Call the summarizer
        summary_result = summarizer.summarize_task(
            instruction=instruction,
            final_thought=final_agent_thought,
            screenshot_path=final_screenshot_path,
        )

        # Print the LLM summary
        print("\n" + "-" * 25 + " LLM Generated Task Summary (JSON) " + "-" * 25)
        try:
            print(json.dumps(summary_result, indent=4, ensure_ascii=False))
        except Exception as e:
            print(f"Error printing summary result: {e}")
            print("Raw summary result dictionary:", summary_result)
        print("-" * (50 + len(" LLM Generated Task Summary (JSON) ")))

    else:
        print("Warning: Could not determine final screenshot path for summary.")
        summary_result = {
            "answer": "Error: Final screenshot missing",
            "description": "Could not generate summary because the final screenshot path was not found.",
        }

    # --- Construct the final execution log ---
    print("\n" + "=" * 30 + " Preparing Final Execution Log " + "=" * 30)
    final_execution_log = {
        "status": "success",
        "instruction": instruction,
        "llm_summary": summary_result,  # Contains {"answer": ..., "description": ...}
        "completed_requirements": completed_requirements,
        "action_history": action_history,
        "thought_history": thought_history,
        "summary_history": summary_history,  # Agent's step summaries
        "memory": memory,
        "iterations": iter - 1,  # Record how many iterations ran before stop
    }

    # --- Save the final execution log to JSON file in atomic_task_dir_path ---
    # <<< MODIFIED: Save log file inside the atomic task directory >>>
    log_file_path = os.path.join(atomic_task_dir_path, "task_log_success.json")

    try:
        # Ensure the atomic task directory exists (should already exist from start)
        os.makedirs(atomic_task_dir_path, exist_ok=True)
        with open(log_file_path, "w", encoding="utf-8") as f:
            json.dump(final_execution_log, f, indent=4, ensure_ascii=False)
        print(f"\n--- Final execution log successfully saved to: {log_file_path} ---")
    except Exception as e:
        print(
            f"\n--- Error writing final success execution log to file {log_file_path}: {e} ---"
        )
        print(traceback.format_exc())

    # --- Save task_answer.json ---
    print("\n" + "=" * 30 + " Saving Task Answer JSON " + "=" * 30)
    # Define the path for task_answer.json (already correct based on atomic_task_dir_path)
    answer_file_path = os.path.join(atomic_task_dir_path, "task_answer.json")

    # Prepare the data for task_answer.json
    task_answer_data = {
        "atomic_tasks_ID": args.atomic_tasks_numbers,
        # Use .get() for safety in case summary_result had errors
        "answer": summary_result.get("answer", "Error: Answer not found in summary"),
        "description": summary_result.get(
            "description", "Error: Description not found in summary"
        ),
    }

    try:
        # Ensure the atomic task subdirectory exists (should already exist)
        os.makedirs(atomic_task_dir_path, exist_ok=True)
        # Write the task_answer.json file
        with open(answer_file_path, "w", encoding="utf-8") as f:
            json.dump(task_answer_data, f, indent=4, ensure_ascii=False)
        print(f"--- Task answer successfully saved to: {answer_file_path} ---")
    except Exception as e:
        print(
            f"\n--- Error writing task answer JSON to file {answer_file_path}: {e} ---"
        )
        print(traceback.format_exc())
    # <<< END MODIFIED SECTION >>>


else:
    # Task did not complete normally (error or max iterations)
    print("\n" + "=" * 30 + " Task Did Not Complete Successfully " + "=" * 30)
    # Save a failure log
    # <<< MODIFIED: Save failure log file inside the atomic task directory >>>
    fail_log_path = os.path.join(atomic_task_dir_path, "task_log_failure.json")
    try:
        # Ensure the atomic task directory exists
        os.makedirs(atomic_task_dir_path, exist_ok=True)
        failure_log_data = {
            "status": "failed_or_stopped_unexpectedly",
            "reason": (
                "Reached max iterations"
                if iter >= max_iters
                else "Stopped due to error or unrecognized action"
            ),
            "iterations_completed": iter if iter < max_iters else max_iters,
            "instruction": instruction,
            "last_action": action if "action" in locals() else "N/A",
            "last_thought": thought if "thought" in locals() else "N/A",
            "completed_requirements": (
                completed_requirements
                if "completed_requirements" in locals()
                else "N/A"
            ),
            "action_history": action_history if "action_history" in locals() else [],
            "thought_history": thought_history if "thought_history" in locals() else [],
            "summary_history": summary_history if "summary_history" in locals() else [],
            "memory": memory if "memory" in locals() else "",
            "error_flag_final": error_flag,
        }
        with open(fail_log_path, "w", encoding="utf-8") as f:
            json.dump(failure_log_data, f, indent=4, ensure_ascii=False)
        print(f"\n--- Task failure/unexpected stop state saved to: {fail_log_path} ---")
    except Exception as e:
        print(f"\n--- Error saving failure log: {e} ---")
        print(traceback.format_exc())

# Optional: Clean up temp directory at the very end
# try:
#     if os.path.exists(temp_dir):
#         shutil.rmtree(temp_dir)
#         print(f"Final cleanup of temporary directory: {temp_dir}")
# except Exception as e:
#     print(f"Warning: Could not perform final cleanup of {temp_dir}: {e}")

print("\n--- Script Execution Finished ---")
# <<< END MODIFIED SECTION >>>
