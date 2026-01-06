# root/src/Agent/MA_test.py

import json
import subprocess
import os
import sys
import threading
import time
import traceback  # Potentially useful for small delays if needed


def call_mobile_agent_e(
    log_root: str,
    run_name: str,
    setting: str,
    instruction: str,
    atomic_tasks_numbers: str,
):
    """
    从 MA_test.py 调用 Mobile-Agent-E 的 run.py 脚本，并尝试实时打印其合并后的输出。

    Args:
        log_root (str): --log_root 参数的值 (日志根目录的路径)。
        run_name (str): --run_name 参数的值。
        setting (str): --setting 参数的值。
        instruction (str): --instruction 参数的值。

    Returns:
        int: 子进程的退出码。

    Raises:
        FileNotFoundError: 如果 run.py 脚本未找到。
        subprocess.CalledProcessError: 如果 run.py 执行返回非零退出码。
        Exception: 其他潜在错误。
    """
    process = None  # Initialize process to None for finally block
    output_lines = []  # Store combined output lines

    try:
        # --- 路径计算和命令准备 (与之前相同) ---
        current_script_path = os.path.abspath(__file__)
        current_script_dir = os.path.dirname(current_script_path)
        target_script_path = os.path.join(
            current_script_dir, "Operation_Agent", "Mobile-Agent-E", "run.py"
        )
        target_script_dir = os.path.dirname(target_script_path)

        if not os.path.isfile(target_script_path):
            raise FileNotFoundError(f"目标脚本未找到: {target_script_path}")

        log_root_abs = os.path.abspath(log_root)
        print(f"使用日志根目录: {log_root_abs}")

        command = [
            sys.executable,
            target_script_path,
            "--log_root",
            log_root_abs,
            "--run_name",
            run_name,
            "--setting",
            setting,
            "--instruction",
            instruction,
            "--atomic_tasks_numbers",
            atomic_tasks_numbers,
        ]
        # --- 结束路径计算和命令准备 ---

        print(f"执行命令: {' '.join(command)}")
        print(f"工作目录: {target_script_dir}")
        print("-" * 50)
        print(">>> 开始实时打印 Mobile-Agent-E 输出 (stdout & stderr combined) <<<")
        print("-" * 50)

        # --- 使用 Popen 并合并 stderr 到 stdout ---
        process = subprocess.Popen(
            command,
            cwd=target_script_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
            text=True,
            encoding="utf-8",  # 显式指定编码
            errors="replace",  # 替换无法解码的字符
            bufsize=1,  # 行缓冲
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
                    output_list.append(line)
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
        # 检查 process.stdout 是否有效
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
            return_code = process.wait(timeout=60)  # 等待最多30秒 (可选)
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
        print(f">>> Mobile-Agent-E 执行完毕 (退出码: {return_code}) <<<")
        print("-" * 50)

        # 检查退出码
        if return_code != 0:
            full_output = "".join(output_lines)  # 仍然可以获取收集到的完整输出
            print(f"错误: Mobile-Agent-E 执行失败，退出码 {return_code}")
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
        raise
    except subprocess.CalledProcessError as e:
        print(f"子进程错误已被捕获 (退出码: {e.returncode})。")
        raise
    except Exception as e:
        print(f"发生意外错误: {e}")
        raise
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
        target_script_path = os.path.join(
            current_script_dir, "Operation_Agent", "PC-Agent", run_script_name
        )
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


def call_jarvis(
    instruction: str,
    log_dir: str,
    atomic_tasks_numbers: str,
):
    """
    调用 Jarvis Agent 的 run_wrapper.py 脚本，并尝试实时打印其合并后的输出。

    Args:
        instruction (str): --instruction 参数的值 (用户指令)。
        log_dir (str): --log_dir 参数的值 (日志目录路径)。
        atomic_tasks_numbers (str): --atomic_tasks_numbers 参数的值 (原子任务编号)。

    Returns:
        int: 子进程的退出码。

    Raises:
        FileNotFoundError: 如果 run_wrapper.py 未找到。
        subprocess.CalledProcessError: 如果脚本执行返回非零退出码。
        Exception: 其他潜在错误。
    """
    process = None  # 初始化 process 为 None 以便在 finally 块中使用
    output_lines = []  # 存储合并后的输出行

    try:
        # --- 路径计算和命令准备 ---
        current_script_path = os.path.abspath(__file__)
        current_script_dir = os.path.dirname(current_script_path)
        target_script_path = os.path.join(
            current_script_dir, "Operation_Agent", "Jarvis_V2", "run_wrapper.py"
        )
        target_script_dir = os.path.dirname(target_script_path)

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
            atomic_tasks_numbers,
        ]
        # --- 结束路径计算和命令准备 ---

        print(f"执行命令: {' '.join(command)}")
        print(f"工作目录: {target_script_dir}")
        print("-" * 50)
        print(">>> 开始实时打印 Jarvis Agent 输出 (stdout & stderr combined) <<<")
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
        print(f">>> Jarvis Agent 执行完毕 (退出码: {return_code}) <<<")
        print("-" * 50)

        # 检查退出码
        if return_code != 0:
            full_output = "".join(output_lines)  # 仍然可以获取收集到的完整输出
            print(f"错误: Jarvis Agent 执行失败，退出码 {return_code}")
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


def operator(
    agent: str,
    log_root: str,
    run_name: any,
    setting: str,
    instruction: str,
    atomic_tasks_numbers: any,
):  # 可以放宽类型提示为 any 或保留 str
    """
    操作指定代理执行任务。

    Args:
        agent (str): 要使用的代理名称 (例如 "mobile_agent_e", "jarvis_agent")。
        log_root (str): 日志根目录路径。
        run_name (any): 运行的名称或标识符。会被转换为字符串使用。
        setting (str): 运行设置 (例如 "individual")。
        instruction (str): 要执行的任务指令。

    Raises:
        ValueError: 如果代理类型不支持。
        TypeError: 如果传入的参数类型不合适且无法自动转换。
    """
    # --- 增强健壮性：类型检查和转换 ---
    if not isinstance(run_name, str):
        print(
            f"警告: 'run_name' 参数期望是字符串，但收到了 {type(run_name).__name__} 类型的值: {run_name}。正在尝试转换为字符串..."
        )
        try:
            run_name_str = str(run_name)  # 尝试转换为字符串
        except Exception as convert_e:
            # 如果连转换都不行，抛出更具体的错误
            raise TypeError(
                f"无法将 'run_name' 参数 ({run_name}) 转换为字符串: {convert_e}"
            ) from convert_e
    else:
        run_name_str = run_name  # 如果本来就是字符串，直接使用
    if not isinstance(atomic_tasks_numbers, str):
        print(
            f"警告: 'atomic_tasks_numbers' 参数期望是字符串，但收到了 {type(atomic_tasks_numbers).__name__} 类型的值: {atomic_tasks_numbers}。正在尝试转换为字符串..."
        )
        try:
            atomic_tasks_numbers_str = str(atomic_tasks_numbers)  # 尝试转换为字符串
        except Exception as convert_e:
            # 如果连转换都不行，抛出更具体的错误
            raise TypeError(
                f"无法将 'atomic_tasks_numbers' 参数 ({atomic_tasks_numbers}) 转换为字符串: {convert_e}"
            ) from convert_e
    else:
        atomic_tasks_numbers_str = atomic_tasks_numbers  # 如果本来就是字符串，直接使用
    # --- 检查结束 ---

    if agent == "mobile_agent_e":
        try:
            print("\n准备调用mobile-Agent-E...")
            print(f"日志根目录: {log_root}")
            print(f"运行名称: {run_name_str}")  # 打印转换后的字符串
            print(f"设置: {setting}")
            print(f"指令: {instruction}")
            print(f"原子任务编号: {atomic_tasks_numbers_str}")
            # 确保传递转换后的字符串 run_name_str
            exit_code = call_mobile_agent_e(
                log_root=log_root,
                run_name=run_name_str,  # 使用转换后的字符串
                setting=setting,
                instruction=instruction,
                atomic_tasks_numbers=atomic_tasks_numbers_str,
            )
            print(f"\n脚本: Mobile-Agent-E 调用成功完成，退出码: {exit_code}")
        except Exception as e:
            print(f"\n脚本: 调用 Mobile-Agent-E 失败: {type(e).__name__} - {e}")
            if (
                isinstance(e, subprocess.CalledProcessError)
                and hasattr(e, "output")
                and e.output
            ):
                # 确保 e.output 存在且不为空再打印
                print("--- Captured Output on Failure ---")
                # 如果 output 是 bytes，解码为字符串打印
                output_str = (
                    e.output.decode("utf-8", errors="ignore")
                    if isinstance(e.output, bytes)
                    else str(e.output)
                )
                print(output_str)
                print("--------------------------------")
            # 可以考虑在这里重新抛出异常或返回特定错误码，让调用者知道失败了
            # raise e # 或者 return -1
    elif agent == "pc_agent_win":
        try:
            print("\n准备调用 PC Agent...")
            # 注意：PC Agent 需要的是特定任务的日志目录 (log_dir)，
            # 而不是 log_root。调用者需要确保传入正确的路径。
            # 这里我们假设传入的 log_root 实际上是 PC Agent 需要的 log_dir。
            # 如果不是，调用者需要调整传入 operator 的参数。
            log_dir_for_pc = log_root
            print(f"日志目录 (log_dir): {log_dir_for_pc}")
            print(f"指令: {instruction}")
            print(f"原子任务编号 (int): {atomic_tasks_numbers_str}")
            # PC Agent 需要整数类型的 atomic_tasks_numbers
            exit_code = call_pc_agent(
                instruction=instruction,
                log_dir=log_dir_for_pc,  # 假设 log_root 是 PC Agent 的 log_dir
                atomic_tasks_numbers=atomic_tasks_numbers_str,  # 传递整数版本
                # run_script_name="run_v2.py" # 可以保持默认或修改
            )
            print(f"\n脚本: PC Agent 调用成功完成，退出码: {exit_code}")
        except Exception as e:
            print(f"\n脚本: 调用 PC Agent 失败: {type(e).__name__} - {e}")
            # 打印详细错误信息（如果可用）
            if (
                isinstance(e, subprocess.CalledProcessError)
                and hasattr(e, "output")
                and e.output
            ):
                output_str = (
                    e.output.decode("utf-8", errors="ignore")
                    if isinstance(e.output, bytes)
                    else str(e.output)
                )
                print("--- Captured Output on Failure ---")
                print(output_str)
                print("--------------------------------")
            raise e  # 重新抛出异常

    elif agent == "jarvis_agent":
        try:
            print("\n准备调用 Jarvis Agent...")
            # Jarvis Agent 需要的是特定任务的日志目录 (log_dir)
            log_dir_for_jarvis = log_root
            print(f"日志目录 (log_dir): {log_dir_for_jarvis}")
            print(f"指令: {instruction}")
            print(f"原子任务编号 (str): {atomic_tasks_numbers_str}")
            # Jarvis Agent 需要字符串类型的 atomic_tasks_numbers
            exit_code = call_jarvis(
                instruction=instruction,
                log_dir=log_dir_for_jarvis,
                atomic_tasks_numbers=atomic_tasks_numbers_str,
            )
            print(f"\n脚本: Jarvis Agent 调用成功完成，退出码: {exit_code}")
        except Exception as e:
            print(f"\n脚本: 调用 Jarvis Agent 失败: {type(e).__name__} - {e}")
            # 打印详细错误信息（如果可用）
            if (
                isinstance(e, subprocess.CalledProcessError)
                and hasattr(e, "output")
                and e.output
            ):
                output_str = (
                    e.output.decode("utf-8", errors="ignore")
                    if isinstance(e.output, bytes)
                    else str(e.output)
                )
                print("--- Captured Output on Failure ---")
                print(output_str)
                print("--------------------------------")
            raise e  # 重新抛出异常

    else:
        print(f"错误: 不支持的代理类型 '{agent}'。请检查代理名称。")
        raise ValueError(f"Unsupported agent type: {agent}")


def get_answer_from_json(json_file_path: str):
    """
    从指定的 JSON 文件中读取内容，并提取 'answer' 键的值。

    Args:
      json_file_path (str): JSON 文件的路径。

    Returns:
      Optional[Any]: 如果成功找到并读取，则返回 'answer' 键对应的值。
                     如果文件未找到、不是有效的 JSON、缺少 'answer' 键或发生其他错误，
                     则打印错误信息并返回 None。
    """
    try:
        # 使用 'with' 语句确保文件在使用后能正确关闭
        # 指定 encoding='utf-8' 是个好习惯，可以避免编码问题
        with open(json_file_path, "r", encoding="utf-8") as f:
            # 使用 json.load() 从文件对象解析 JSON 数据
            data = json.load(f)

            # 检查 'answer' 键是否存在并获取其值
            if "answer" in data:
                return data["answer"]
            else:
                print(f"错误：在 JSON 文件 '{json_file_path}' 中找不到键 'answer'。")
                return None

    except FileNotFoundError:
        print(f"错误：文件未找到于 '{json_file_path}'")
        return None
    except json.JSONDecodeError:
        print(f"错误：文件 '{json_file_path}' 不是有效的 JSON 格式。")
        return None
    except Exception as e:  # 捕获其他可能的异常，例如权限问题
        print(f"读取或解析文件 '{json_file_path}' 时发生错误: {e}")
        return None


# --- MA_test.py 中的使用示例 ---
if __name__ == "__main__":
    # 计算项目根目录 (假设 MA_test.py 在 root/src/Agent/ 下)
    # try:
    #     current_script_dir = os.path.dirname(os.path.abspath(__file__))
    #     project_root_dir = os.path.abspath(os.path.join(current_script_dir, "..", ".."))
    #     print(f"检测到项目根目录: {project_root_dir}")
    # except Exception as e:
    #     print(f"无法自动检测项目根目录: {e}")
    #     project_root_dir = "."

    # # 参数
    # run_name_arg = "testing_jay_chou_v2"
    # setting_arg = "individual"
    # instruction_arg = "Search for Jay Chou on Wikipedia APP and tell me which album he released in 2000?"

    # try:
    #     print("\n准备调用 Mobile-Agent-E...")
    #     exit_code = call_mobile_agent_e(
    #         log_root=project_root_dir,
    #         run_name=run_name_arg,
    #         setting=setting_arg,
    #         instruction=instruction_arg,
    #     )
    #     print(f"\n主脚本: Mobile-Agent-E 调用成功完成，退出码: {exit_code}")

    # except Exception as e:
    #     print(f"\n主脚本: 调用 Mobile-Agent-E 失败: {type(e).__name__} - {e}")
    #     # 如果是 CalledProcessError，它的 output 属性可能包含一些线索
    #     if isinstance(e, subprocess.CalledProcessError) and e.output:
    #         print("--- Captured Output on Failure ---")
    #         print(e.output)
    #         print("--------------------------------")
    # print(get_answer_from_json("1\output.json"))
    operator(
        "mobile_agent_e",
        "I:/Paper/250302_BenckmarkV2/code/250416/Test_250421/Log/qwen-max-2025-01-25/0301/2025-04-24_21-07-31",
        1,
        "individual",
        "Search for Jay Chou on Wikipedia APP and tell me which album he released in 2000?",
        1,
    )
