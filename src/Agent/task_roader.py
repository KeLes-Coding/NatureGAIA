import json

import sys
from pathlib import Path

root_dir = Path(__file__).parent.parent.parent
sys.path.append(str(root_dir))

import config


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
        self.Task_ID = task_id
        self.level = level
        self.atomic_tasks_number = atomic_tasks_number
        self.atomic_tasks_answer = atomic_tasks_answer
        self.final_answer = final_answer

    def __repr__(self):
        return (
            f"TaskData(Task='{self.Task}', Task_ID='{self.Task_ID}', level={self.level}, "
            f"atomic_tasks_number={self.atomic_tasks_number}, "
            f"atomic_tasks_answer={self.atomic_tasks_answer}, "
            f"final_answer='{self.final_answer}')"
        )

    def get_answer_by_atomic_id(self, atomic_id):
        """根据atomic_tasks_ID获取对应的answer"""
        for task in self.atomic_tasks_answer:
            if task["atomic_tasks_ID"] == atomic_id:
                return task["answer"]
        return None  # 如果没有找到匹配的ID，返回None


def read_task_data_from_json(file_path):
    """
    从JSON文件中读取数据并返回TaskData对象

    :param file_path: JSON文件路径
    :return: TaskData对象
    """
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    return TaskData(
        task=data.get("Task"),
        task_id=data.get("Task_ID"),
        level=data.get("level"),
        atomic_tasks_number=data.get("atomic_tasks_number"),
        atomic_tasks_answer=data.get("atomic_tasks_answer"),
        final_answer=data.get("final_answer"),
    )


# 使用示例
if __name__ == "__main__":
    task_data = read_task_data_from_json(config.JSON_PATH)
    print(task_data)

    # 获取atomic_tasks_ID=1的answer
    answer_for_id_1 = task_data.get_answer_by_atomic_id(1)
    print(f"atomic_tasks_ID=1的answer是: {answer_for_id_1}")  # 输出: Jay
