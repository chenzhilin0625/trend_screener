# 量化研究工作区

A趋势研究与量化交易的本地工作区，包含三个自研趋势工具链（趋势筛选器、ROC 动量排名 v0.1 / v0.2）、一个 QMT 自动交易策略，以及一套模块化 QMT 量化工具集。

> 仅供学习研究使用，不构成投资建议。

---

## 目录总览

| 目录 | 类型 | 说明 |
|------|------|------|
| `trend_screener/` |  趋势筛选器 v2.2：大盘 → 行业 → 个股三层过滤，纯本地通达信数据，带 Flask Web 界面 |
| `trend v0.1/` |  ROC(20/60/120) 动量排名工具（东方财富数据源，SQLite 存储） |
| `trend v0.2/` |  ROC 动量排名升级版：argparse CLI、申万 SW2/SW3 行业、ID 强度指标、板块成分股明细 |
| `EasyXT/` |  模块化 QMT 量化交易工具集（miniQMT API 封装、回测、因子平台、策略与学习实例） |
| `CL/` |  QMT 自动交易策略 `B1.PY` |
| `report/` |  各趋势工具运行结果与报告的存档目录 |

```
claude/
├── trend_screener/        # 趋势筛选器（三层过滤 + Web UI）
├── trend v0.1/            # ROC 动量排名（东方财富数据源）
├── trend v0.2/            # ROC 动量排名升级版（申万行业 + ID 强度）
├── EasyXT/                # QMT 量化交易工具集（第三方项目）
├── CL/                    # QMT 自动交易策略
│   └── B1.PY              # 宽基轮动 ETF 策略（云飞量化生成）
├── report/                # 报告存档
└── README.md
```

---

## 1. trend_screener — 趋势筛选器 v2.2

**定位**：趋势交易者每日复盘工具箱

三层过滤管道：

内置 30+ 独立指标函数

### 使用

```bash
cd trend_screener
pip install -r requirements.txt

python main.py                    # 日常：成分股内筛选
python main.py --full-scan        # 全量扫描所有股票（慢）
python main.py --market-only      # 仅评估大盘趋势
python main.py --report           # 生成 Markdown 报告
python main.py --verbose          # 详细日志
```

### Web 界面

```bash
python server.py                  # 访问 http://localhost:5000
# 或 Windows 双击 启动.bat，Mac/Linux 运行 启动.sh
```

### 数据来源

- 通达信本地 vipdoc 行情 → `tdx_sync.py` 增量同步 → SQLite（`trend_data.db`）
- 首次导入：`tdx_importer.py`（日线）、`tdx_industry_import.py`（板块）

详细策略说明见 [`trend_screener/STRATEGY_GUIDE.md`](trend_screener/STRATEGY_GUIDE.md)。

---

## 2. trend v0.1 — ROC 动量排名（东方财富数据源）

**定位**：一个指标——相对 N 个交易日前的涨跌幅（ROC），给行业板块、概念板块、ETF 和个股排名。数据来自东方财富公开 HTTP API，纯本地 SQLite 存储。

### 使用

```bash
cd "trend v0.1"

# 数据更新（tools/ 下）
python tools/updater.py           # 增量更新
python tools/em_updater.py        # 东方财富数据更新
python tools/reload_stock_etf.py  # 重建股票/ETF 列表

# 运行排名
python run.py                     # 板块 + ETF + 个股全量排名
python run.py --sectors           # 仅板块
python run.py --etf               # 仅 ETF
python run.py --top 50            # 个股自定义数量
python run.py --no-report         # 不生成 HTML 报告
python run.py --no-sync           # 跳过自动增量同步
```

输出同时写入终端与 `report/*.html`。

### 模块结构

```
trend v0.1/
├── run.py              # 主入口
├── trend/
│   ├── db/             # loader / schema（SQLite → pandas）
│   ├── score/          # indicators（ROC / ID 排名打分）
│   ├── source/         # eastmoney / sina / tencent 数据源
│   ├── sync.py         # 增量同步
│   └── report.py       # HTML 报告输出
├── tools/              # updater / em_updater / reload_stock_etf
├── report/             # HTML 报告输出目录
└── etf_list.txt        # ETF 列表
```

---

## 3. trend v0.2 — ROC 动量排名升级版

**定位**：v0.1 的演进版本，改进点：

- 用 `argparse` 规范化 CLI（`trend/cli.py` 统一入口）
- 行业板块升级为申万 **SW2 行业 / SW3 细分**
- 新增 **ID 强度指标**（与 ROC 并列排名）
- 新增 `--detail BK代码` 查看板块成分股明细
- 数据源模块调整为 miniQMT 接口（`trend/source/miniqmt.py`）

### 使用

```bash
cd "trend v0.2"

python run.py                     # 板块 + ETF + 个股全量排名
python run.py --sectors           # 仅板块
python run.py --etf               # 仅 ETF
python run.py --top 50            # 个股自定义数量
python run.py --detail BK0475     # 查看某板块成分股 ROC 排名
python run.py --no-report         # 不生成 HTML 报告
python run.py --no-sync           # 跳过增量更新
```

---

## 4. EasyXT — 模块化 QMT 量化交易工具集

**定位**：面向 miniQMT 的模块化工具集，与本目录中的自研工具相互独立。

核心模块：

- `easy_xt/`：QMT API 轻量封装（行情 / 交易），可独立安装使用
- `easyxt_backtest/`：通用回测框架
- `101因子/`：基于 Streamlit 的因子分析平台
- `strategies/`：实战策略集合（雪球跟单、网格交易、通达信预警、聚宽转 QMT）

### 使用

```bash
cd EasyXT

# 安装核心库（需先配置特殊版本 xtquant，见 EasyXT/README.md）
pip install -e ./easy_xt

# 启动因子分析平台
cd 101因子/101因子分析平台 && python 启动增强版.py
```

> 注意：完整安装涉及特殊版本 xtquant、QMT 客户端路径、Tushare Token 等配置，详见 [`EasyXT/README.md`](EasyXT/README.md) 与 [`EasyXT/INSTALL.md`](EasyXT/INSTALL.md)。

---

## 5. CL — QMT 自动交易策略

**内容**：`B1.PY`，QMT 策略代码。

- 运行方式：在 QMT 客户端中导入该策略文件运行
- 工作时间：09:32–14:58，佣金万 1，初始资金 50 万（策略内部参数，可在 `init()` 中修改）

---

## 6. report — 报告存档

各工具生成的历史报告：

- `trend_report_2026-06-08.md`：趋势筛选器 Markdown 报告
- `screener_20260608.log` / `result_20260608.txt`：趋势筛选器日志与结果摘要
- `2026-07-21_0046.txt`：ROC 动量排名终端输出存档

---

## 环境要求

- Python 3.9+（部分模块需 3.11+，如 v0.2 有 cpython-314 缓存）
- 主要依赖：`pandas`、`numpy`、`flask`、`akshare`、`mootdx`（趋势筛选器）；`requests`（数据抓取）
- 趋势筛选器依赖本地通达信行情目录（vipdoc）
- EasyXT / CL 依赖 Windows + QMT（或 miniQMT）客户端

## 风险提示

1. 所有工具仅供学习研究，不构成投资建议
2. 量化交易存在投资风险，请谨慎操作
3. 建议先在模拟环境中测试策略，再考虑实盘
4. 遵守相关法律法规和交易所规则
