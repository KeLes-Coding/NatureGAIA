import os
import sys
import subprocess
import threading
import time
import traceback


def call_pc_agent(
    instruction: str,
    log_dir: str,
    atomic_tasks_numbers: int,
    run_script_name: str = "run_v2.py",  # 允许指定不同的脚本名称
):
    """
    调用 PC Agent 的 run_v2.py 脚本 (或指定脚本)，并尝试实时打印其合并后的输出。

    Args:
        instruction (str): --instruction 参数的值 (用户指令)。
        log_dir (str): --log_dir 参数的值 (日志目录路径)。
        atomic_tasks_numbers (int): --atomic_tasks_numbers 参数的值 (原子任务编号)。
        run_script_name (str, optional): 要执行的脚本文件名。默认为 "run_v2.py"。

    Returns:
        int: 子进程的退出码。

    Raises:
        FileNotFoundError: 如果 run_v2.py (或指定脚本) 未找到。
        subprocess.CalledProcessError: 如果脚本执行返回非零退出码。
        Exception: 其他潜在错误。
    """
    process = None  # 初始化 process 为 None 以便在 finally 块中使用
    output_lines = []  # 存储合并后的输出行

    try:
        # --- 路径计算和命令准备 ---
        # 假设 run_v2.py 与调用此函数的脚本在同一目录下
        current_script_path = os.path.abspath(__file__)
        current_script_dir = os.path.dirname(current_script_path)
        target_script_path = os.path.join(current_script_dir, run_script_name)
        target_script_dir = current_script_dir  # 工作目录设为脚本所在目录

        if not os.path.isfile(target_script_path):
            raise FileNotFoundError(f"目标脚本未找到: {target_script_path}")

        # 确保 log_dir 是绝对路径
        log_dir_abs = os.path.abspath(log_dir)
        print(f"使用日志目录: {log_dir_abs}")

        # 构建命令列表
        command = [
            sys.executable,  # 使用当前 Python 解释器
            target_script_path,
            "--instruction",
            instruction,
            "--log_dir",
            log_dir_abs,
            "--atomic_tasks_numbers",
            str(atomic_tasks_numbers),  # 参数需要字符串类型
            # 可以根据需要添加 run_v2.py 支持的其他参数
            # 例如: "--api_url", args.api_url, "--api_token", args.api_token 等
        ]
        # --- 结束路径计算和命令准备 ---

        print(f"执行命令: {' '.join(command)}")
        print(f"工作目录: {target_script_dir}")
        print("-" * 50)
        print(f">>> 开始实时打印 {run_script_name} 输出 (stdout & stderr combined) <<<")
        print("-" * 50)

        # --- 使用 Popen 并合并 stderr 到 stdout ---
        process = subprocess.Popen(
            command,
            cwd=target_script_dir,  # 设置工作目录
            stdout=subprocess.PIPE,  # 捕获标准输出
            stderr=subprocess.STDOUT,  # 合并标准错误到标准输出
            text=True,  # 以文本模式处理输出
            encoding="utf-8",  # 显式指定编码
            errors="replace",  # 替换无法解码的字符
            bufsize=1,  # 行缓冲模式，确保逐行读取
        )

        # --- 实时读取合并后的输出流 ---
        def stream_reader(stream, output_list):
            """读取流并实时打印/存储"""
            if not stream:
                print("[Warning] Output stream is not available.")
                return
            try:
                # 使用 iter 和 readline 读取直到流结束
                for line in iter(stream.readline, ""):
                    print(line, end="", flush=True)  # 实时打印并强制刷新
                    output_list.append(line)  # 同时存储输出行
            except Exception as e:
                # 捕获读取过程中可能发生的异常 (例如，如果进程意外关闭)
                print(f"\n[Error] Exception during stream reading: {e}", flush=True)
            finally:
                # 确保即使出错也尝试关闭流
                if stream and not stream.closed:
                    try:
                        stream.close()
                    except Exception as close_err:
                        print(
                            f"\n[Warning] Error closing stream: {close_err}", flush=True
                        )

        # 使用一个线程来读取合并后的 stdout
        if process.stdout:
            output_thread = threading.Thread(
                target=stream_reader, args=(process.stdout, output_lines)
            )
            output_thread.start()
            # 等待读取线程完成 (意味着流已关闭或读取出错)
            output_thread.join()
        else:
            print("[Warning] process.stdout is None, cannot read output.", flush=True)

        # 等待子进程完全结束并获取返回码
        # 添加一个短暂的超时，以防万一进程挂起（可选）
        try:
            return_code = process.wait(timeout=600)  # 等待最多 10 分钟 (根据需要调整)
        except subprocess.TimeoutExpired:
            print("\n[Warning] Process timed out. Attempting to terminate.", flush=True)
            process.terminate()  # 尝试终止
            time.sleep(1)  # 给点时间
            if process.poll() is None:  # 检查是否仍在运行
                print(
                    "[Warning] Process did not terminate, attempting to kill.",
                    flush=True,
                )
                process.kill()  # 强制杀死
            return_code = process.wait()  # 获取最终返回码
            print(f"[Info] Process terminated with code: {return_code}", flush=True)

        print("\n" + "-" * 50)  # 加一个换行符
        print(f">>> {run_script_name} 执行完毕 (退出码: {return_code}) <<<")
        print("-" * 50)

        # 检查退出码
        if return_code != 0:
            full_output = "".join(output_lines)  # 仍然可以获取收集到的完整输出
            print(f"错误: {run_script_name} 执行失败，退出码 {return_code}")
            # 注意: full_output 现在包含 stdout 和 stderr 的混合内容
            # 可能需要在这里打印 full_output 以便调试
            # print("--- Combined Output on Error ---")
            # print(full_output)
            # print("-----------------------------")
            raise subprocess.CalledProcessError(
                return_code, command, output=full_output
            )

        return return_code

    except FileNotFoundError as e:
        print(f"错误: {e}")
        raise  # 重新抛出异常
    except subprocess.CalledProcessError as e:
        print(f"子进程错误已被捕获 (退出码: {e.returncode})。")
        # 此处不打印 e.output，因为实时输出时已经打印过了
        raise  # 重新抛出异常
    except Exception as e:
        print(f"发生意外错误: {e}")
        print(traceback.format_exc())  # 打印详细的堆栈跟踪
        raise  # 重新抛出异常
    finally:
        # 确保在任何情况下都尝试清理子进程资源
        if process and process.poll() is None:  # 如果进程仍在运行
            print("[Info] Cleaning up running process...", flush=True)
            try:
                process.terminate()
                time.sleep(0.5)  # Give it a moment
                if process.poll() is None:
                    process.kill()
                process.wait()  # Wait for cleanup
            except Exception as cleanup_err:
                print(
                    f"[Warning] Error during process cleanup: {cleanup_err}", flush=True
                )


# --- 示例用法 (需要取消注释并确保 run_v2.py 在同目录下) ---
if __name__ == "__main__":
    test_instruction = "Open Google Chrome."
    test_log_dir = "./pc_agent_test_logs"
    test_task_num = 99

    try:
        print(f"开始调用 call_pc_agent for task {test_task_num}...")
        exit_code = call_pc_agent(test_instruction, test_log_dir, test_task_num)
        print(f"\ncall_pc_agent 调用完成，退出码: {exit_code}")

        # 可以在这里添加检查日志文件是否生成的代码
        expected_success_log = os.path.join(test_log_dir, "task_log_success.json")
        expected_answer_file = os.path.join(
            test_log_dir, str(test_task_num), "task_answer.json"
        )
        if exit_code == 0:
            if os.path.exists(expected_success_log):
                print(f"成功日志文件已找到: {expected_success_log}")
            else:
                print(f"[Warning] 成功日志文件未找到: {expected_success_log}")
            if os.path.exists(expected_answer_file):
                print(f"任务答案文件已找到: {expected_answer_file}")
            else:
                print(f"[Warning] 任务答案文件未找到: {expected_answer_file}")
        else:
            expected_fail_log = os.path.join(test_log_dir, "task_log_failure.json")
            if os.path.exists(expected_fail_log):
                print(f"失败日志文件已找到: {expected_fail_log}")
            else:
                print(f"[Warning] 失败日志文件未找到: {expected_fail_log}")

    except FileNotFoundError:
        print("测试失败: 脚本 run_v2.py 未找到。")
    except subprocess.CalledProcessError as e:
        print(f"测试失败: run_v2.py 返回非零退出码 {e.returncode}。")
    except Exception as e:
        print(f"测试期间发生意外错误: {e}")
        print(traceback.format_exc())
