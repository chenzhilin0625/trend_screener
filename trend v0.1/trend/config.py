"""全局配置"""
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "trend_em.db")

# 反爬参数
REQUEST_DELAY = 0.1          # 每次请求间隔（秒）
REQUEST_TIMEOUT = 10         # HTTP 超时（秒）
MAX_FAIL_BEFORE_BACKOFF = 20 # 连续失败阈值
BACKOFF_SLEEP = 5            # 退避等待（秒）
