"""全局配置"""
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "trend_em.db")

# 排名参数
DEFAULT_TOP_N = 30
DEFAULT_MIN_MCAP = 5e9       # 50 亿
DEFAULT_MIN_DAYS = 250
