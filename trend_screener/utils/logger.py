"""
日志系统

同时输出到终端和文件。日志文件保存在 output/ 目录下，
按日期命名：output/screener_20260604.log。
"""
import os
import sys
from datetime import datetime


class Logger:
    """双通道日志：print 到终端 + 写入文件。"""

    def __init__(self, log_dir="report"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        today = datetime.now().strftime("%Y%m%d")
        self.log_path = os.path.join(log_dir, f"screener_{today}.log")
        self._file = open(self.log_path, "a", encoding="utf-8")
        self._write_header()

    def _write_header(self):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._file.write(f"\n{'=' * 60}\n")
        self._file.write(f"  Session: {ts}\n")
        self._file.write(f"{'=' * 60}\n")
        self._file.flush()

    def log(self, msg, level="INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] [{level}] {msg}"
        print(msg)  # 终端
        self._file.write(line + "\n")  # 文件
        self._file.flush()

    def info(self, msg):
        self.log(msg, "INFO")

    def warn(self, msg):
        self.log(msg, "WARN")

    def error(self, msg):
        self.log(msg, "ERROR")

    def result(self, msg):
        """重要结果，同时输出到 results 文件。"""
        self.log(msg, "RESULT")
        # 额外写入一个汇总文件
        today = datetime.now().strftime("%Y%m%d")
        result_path = os.path.join(self.log_dir, f"result_{today}.txt")
        with open(result_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")

    def close(self):
        if self._file:
            self._file.close()

    def get_path(self):
        return self.log_path
