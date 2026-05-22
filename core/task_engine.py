from __future__ import annotations
# -*- coding: utf-8 -*-
"""
任务执行引擎

解析任务流、调度步骤执行、管理执行生命周期。
多主机并行，单主机步骤串行。
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QObject, Signal

from data.models import Task, TaskStep, ExecutorResult, ServiceError
from config.settings import get_settings
from core.host_service import HostService
from executors.ssh_executor import SSHExecutor
from executors.sftp_executor import SFTPExecutor
from utils.logger import setup_logger

logger = setup_logger("task_engine")


class TaskEngine(QObject):
    """
    任务执行引擎。

    继承 QObject，通过 Qt Signal 向 UI 层回传执行状态。
    """

    # ============ Qt 信号 ============

    step_started = Signal(str, int, str, str)           # host_id, step_index, step_type, step_name
    step_completed = Signal(str, int, bool, str)       # host_id, step_index, success, error
    command_output = Signal(str, str, str)              # host_id, line_text, output_type
    transfer_progress = Signal(str, int, int, int, int) # host_id, step_idx, transferred, total, speed
    host_finished = Signal(str, bool)                   # host_id, all_success
    task_finished = Signal(bool, dict)                  # all_success, result_summary
    task_error = Signal(str)                            # error_message

    def __init__(self, host_service: HostService | None = None):
        super().__init__()
        self._host_service = host_service or HostService()
        self._settings = get_settings()
        self._cancelled = False
        self._paused = False
        self._running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """当前是否有任务在执行"""
        with self._lock:
            return self._running

    def execute_task(self, task: Task, selected_host_ids: list[int]) -> None:
        """
        启动任务执行。此方法立即返回，实际执行在后台线程池中进行。

        Args:
            task: Task ORM 对象（含 steps 列表）
            selected_host_ids: 用户选中的目标主机 ID 列表
        """
        with self._lock:
            if self._running:
                self.task_error.emit("已有任务正在执行中")
                return
            self._running = True
            self._cancelled = False
            self._paused = False

        # 在后台线程中执行
        thread = threading.Thread(
            target=self._run_task,
            args=(task, selected_host_ids),
            daemon=True,
        )
        thread.start()

    def retry_host(self, task: Task, host_id: int, from_step_index: int = 0) -> None:
        """
        重试单台主机，从指定步骤开始重跑到最后。

        Args:
            task: Task ORM 对象
            host_id: 要重试的主机 ID
            from_step_index: 从第几个步骤开始重试（默认 0，即从头开始）
        """
        with self._lock:
            if self._running:
                self.task_error.emit("已有任务正在执行中，请等待完成后再重试")
                return
            self._running = True
            self._cancelled = False
            self._paused = False

        thread = threading.Thread(
            target=self._run_single_host_retry,
            args=(task, host_id, from_step_index),
            daemon=True,
        )
        thread.start()

    def _run_single_host_retry(self, task: Task, host_id: int, from_step_index: int) -> None:
        """重试单台主机的后台线程"""
        steps = task.steps
        if not steps or from_step_index >= len(steps):
            self.task_error.emit("无效的重试参数")
            self._finish()
            return

        retry_steps = steps[from_step_index:]
        host_id_str = str(host_id)

        self._log_system(f"🔄 开始重试主机: {host_id_str}（从步骤 {from_step_index + 1} 开始）")

        try:
            host_result = self._run_host(host_id, retry_steps)
        except Exception as e:
            host_result = {"success": False, "steps_completed": 0, "steps_failed": 1, "error": str(e)}
            logger.error(f"Retry host {host_id} error: {e}")

        # 发出重试完成的信号（复用 task_finished，携带重试信息）
        all_success = host_result["success"]
        summary = {
            "total_hosts": 1,
            "success_hosts": 1 if all_success else 0,
            "failed_hosts": 0 if all_success else 1,
            "duration_seconds": 0,
            "host_results": {host_id_str: host_result},
            "is_retry": True,
            "retry_host_id": host_id_str,
            "retry_from_step": from_step_index,
        }
        self.task_finished.emit(all_success, summary)
        self._finish()

    def retry_step(self, task: Task, host_id: int, step_index: int) -> None:
        """
        重试单台主机的单个步骤。

        Args:
            task: Task ORM 对象
            host_id: 主机 ID
            step_index: 要重试的步骤索引
        """
        with self._lock:
            if self._running:
                self.task_error.emit("已有任务正在执行中，请等待完成后再重试")
                return
            self._running = True
            self._cancelled = False
            self._paused = False

        thread = threading.Thread(
            target=self._run_single_step_retry,
            args=(task, host_id, step_index),
            daemon=True,
        )
        thread.start()

    def _run_single_step_retry(self, task: Task, host_id: int, step_index: int) -> None:
        """重试单个步骤的后台线程"""
        steps = task.steps
        if not steps or step_index >= len(steps):
            self.task_error.emit("无效的重试参数")
            self._finish()
            return

        retry_step = steps[step_index]
        host_id_str = str(host_id)

        self._log_system(f"🔄 开始重试步骤: {retry_step.name}（主机 {host_id_str}）")

        try:
            host_result = self._run_host(host_id, [retry_step])
        except Exception as e:
            host_result = {"success": False, "steps_completed": 0, "steps_failed": 1, "error": str(e)}
            logger.error(f"Retry step {retry_step.name} on host {host_id} error: {e}")

        all_success = host_result["success"]
        summary = {
            "total_hosts": 1,
            "success_hosts": 1 if all_success else 0,
            "failed_hosts": 0 if all_success else 1,
            "duration_seconds": 0,
            "host_results": {host_id_str: host_result},
            "is_retry": True,
            "retry_host_id": host_id_str,
            "retry_step_index": step_index,
            "is_single_step": True,
        }
        self.task_finished.emit(all_success, summary)
        self._finish()

    def _log_system(self, message: str):
        """通过 command_output 信号输出系统日志（用空 host_id 标记为系统消息）"""
        self.command_output.emit("__system__", message, "system")

    def _run_task(self, task: Task, selected_host_ids: list[int]) -> None:
        """在后台线程中执行任务"""
        steps = task.steps
        if not steps:
            self.task_finished.emit(False, {"error": "任务没有可执行的步骤"})
            self._finish()
            return

        result_summary = {
            "total_hosts": len(selected_host_ids),
            "success_hosts": 0,
            "failed_hosts": 0,
            "duration_seconds": 0.0,
            "host_results": {},
        }

        start_time = time.time()

        # 对每个主机并行执行
        with ThreadPoolExecutor(max_workers=min(len(selected_host_ids), self._settings.MAX_WORKERS)) as executor:
            futures = {}
            for host_id in selected_host_ids:
                future = executor.submit(self._run_host, host_id, steps)
                futures[future] = host_id

            for future in as_completed(futures):
                host_id = futures[future]
                try:
                    host_result = future.result()
                    result_summary["host_results"][str(host_id)] = host_result
                    if host_result["success"]:
                        result_summary["success_hosts"] += 1
                    else:
                        result_summary["failed_hosts"] += 1
                except Exception as e:
                    result_summary["host_results"][str(host_id)] = {
                        "success": False,
                        "steps_completed": 0,
                        "steps_failed": 0,
                        "error": str(e),
                    }
                    result_summary["failed_hosts"] += 1
                    logger.error(f"Host {host_id} execution error: {e}")

        result_summary["duration_seconds"] = round(time.time() - start_time, 2)
        all_success = result_summary["failed_hosts"] == 0
        self.task_finished.emit(all_success, result_summary)
        self._finish()

    def _run_host(self, host_id: int, steps: list[TaskStep]) -> dict:
        """
        在单个主机上串行执行所有步骤。

        Returns:
            该主机的执行结果摘要
        """
        host_id_str = str(host_id)
        host_result = {
            "success": True,
            "steps_completed": 0,
            "steps_failed": 0,
            "error": None,
        }

        for step in steps:
            # 检查取消标志
            if self._cancelled:
                logger.info(f"Task cancelled, skipping step {step.name} on host {host_id}")
                break

            # 检查暂停标志
            while self._paused and not self._cancelled:
                time.sleep(0.5)

            if self._cancelled:
                break

            # 检查目标主机是否匹配
            target_ids = step.target_host_ids or []
            if target_ids and host_id not in target_ids:
                continue

            # 发出步骤开始信号
            self.step_started.emit(host_id_str, step.order_index, step.step_type, step.name)

            # 创建并执行执行器
            try:
                credentials = self._host_service.get_credentials(host_id)
                executor = self._create_executor(step, credentials)
                executor.connect()

                # 绑定进度回调
                executor.on_progress(lambda p, sid=host_id_str, si=step.order_index: self._on_progress(
                    sid, si, p
                ))

                result = executor.execute(**self._get_step_kwargs(step))
                executor.close()

                success = result.success
                error = result.error or ""

                # SSH 命令特殊处理：逐行输出
                if step.step_type == "ssh_command" and result.stdout:
                    for line in result.stdout.strip().split("\n"):
                        self.command_output.emit(host_id_str, line, "stdout")
                if step.step_type == "ssh_command" and result.stderr:
                    for line in result.stderr.strip().split("\n"):
                        self.command_output.emit(host_id_str, line, "stderr")

                self.step_completed.emit(host_id_str, step.order_index, success, error)

                if success:
                    host_result["steps_completed"] += 1
                else:
                    host_result["steps_failed"] += 1
                    host_result["error"] = error
                    # 根据步骤配置决定是否继续
                    if getattr(step, "continue_on_error", False):
                        logger.info(f"Step {step.name} failed on host {host_id}, but continue_on_error is set, continuing...")
                    else:
                        # 单主机某步骤失败，跳过该主机后续步骤
                        host_result["success"] = False
                        break

            except ServiceError as e:
                self.step_completed.emit(host_id_str, step.order_index, False, e.message)
                host_result["steps_failed"] += 1
                host_result["error"] = e.message
                if not getattr(step, "continue_on_error", False):
                    host_result["success"] = False
                    break
            except Exception as e:
                error_msg = str(e)
                self.step_completed.emit(host_id_str, step.order_index, False, error_msg)
                host_result["steps_failed"] += 1
                host_result["error"] = error_msg
                logger.error(f"Step {step.name} failed on host {host_id}: {e}")
                if not getattr(step, "continue_on_error", False):
                    host_result["success"] = False
                    break

        self.host_finished.emit(host_id_str, host_result["success"])
        return host_result

    def _create_executor(self, step: TaskStep, credentials):
        """根据步骤类型创建执行器"""
        if step.step_type == "ssh_command":
            return SSHExecutor(credentials)
        elif step.step_type in ("sftp_upload", "sftp_download"):
            return SFTPExecutor(credentials)
        else:
            raise ValueError(f"Unknown step type: {step.step_type}")

    @staticmethod
    def _get_step_kwargs(step: TaskStep) -> dict:
        """提取步骤的执行参数"""
        if step.step_type == "ssh_command":
            return {
                "command": step.command,
                "timeout": step.timeout,
                "workdir": step.workdir,
            }
        elif step.step_type == "sftp_upload":
            return {
                "local_path": step.local_path,
                "remote_path": step.remote_path,
                "direction": "upload",
            }
        elif step.step_type == "sftp_download":
            return {
                "local_path": step.local_path,
                "remote_path": step.remote_path,
                "direction": "download",
            }
        return {}

    def _on_progress(self, host_id: str, step_index: int, progress):
        """进度回调 → 发射 Qt Signal"""
        self.transfer_progress.emit(
            host_id,
            step_index,
            progress.current,
            progress.total,
            progress.speed or 0,
        )

    def cancel(self) -> None:
        """取消当前正在执行的任务"""
        with self._lock:
            self._cancelled = True
            self._paused = False
        logger.info("Task execution cancelled")

    def pause(self) -> None:
        """暂停任务执行"""
        with self._lock:
            self._paused = True
        logger.info("Task execution paused")

    def resume(self) -> None:
        """恢复暂停的任务"""
        with self._lock:
            self._paused = False
        logger.info("Task execution resumed")

    def _finish(self) -> None:
        """标记执行结束"""
        with self._lock:
            self._running = False
