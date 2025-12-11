# Investment Tools

> [!IMPORTANT]
> **⚠️ 郑重声明 / DISCLAIMER**
> 
> **以上这些脚本都是利用 AI 大模型生成。作者编程能力有限，无法处理深奥问题，代码逻辑与功能实现均源自与 AI 的问答互动。**
> 
> **These scripts were generated using AI Large Language Models. The author has limited programming skills and cannot handle complex technical issues. All code logic and implementations are results of AI interactions.**

该项目包含一系列用于股票数据获取、分析和新闻抓取的 Python 工具脚本。主要功能包括：获取股票代码、下载历史行情与期权数据、进行技术面诊断分析以及抓取 24 小时财经快讯。

## 目录

- [环境准备](#环境准备)
- [脚本功能介绍](#脚本功能介绍)
  - [1. 获取股票代码 (get_stock_id.py)](#1-获取股票代码-get_stock_idpy)
  - [2. 获取历史行情与期权数据 (daily_stock_option_data.py)](#2-获取历史行情与期权数据-daily_stock_option_datapy)
  - [3. 股票智能诊断 (stock_diagnosis.py)](#3-股票智能诊断-stock_diagnosispy)
  - [4. 获取富途 24 小时快讯 (get_futu_24hour_news.py)](#4-获取富途-24-小时快讯-get_futu_24hour_newspy)

---

## 环境准备

在使用这些脚本之前，请确保已安装必要的 Python 依赖库。建议使用 `pip` 进行安装：

```bash
pip install requests pandas yfinance pandas_ta scikit-learn pytz openpyxl
```

---

## 脚本功能介绍

### 1. 获取股票代码 (get_stock_id.py)

**路径**: `get_stock_id/get_stock_id.py`

**功能**:
该脚本通过模拟请求从 Moomoo (富途牛牛国际版) 获取美股市场的股票列表，包括股票代码、名称、市值和价格等信息。

**使用方法**:
1.  **配置 Cookie 和 CSRF Token**: 打开脚本，找到 `HEADERS` 部分，手动更新 `futu-x-csrf-token` 和 `cookie` 字段（需从浏览器抓包获取）。
2.  运行脚本：
    ```bash
    python3 get_stock_id/get_stock_id.py
    ```

**输出**:
-   `us_stocks_list.csv`: 包含所有抓取到的股票信息。
-   其实主要就是想获取stock_id这个富途独有的id，然后其他url的参数会用上 
---

### 2. 获取历史行情与期权数据 (daily_stock_option_data.py)

**路径**: `daily_stock_option_data.py`

**功能**:
批量下载指定股票的历史行情数据（日线、30分钟、60分钟）和期权链数据，并计算常用的技术指标（MACD, RSI, KDJ, MA 等）。

**前置条件**:
-   需要在当前目录下创建一个 `stock.list` 文件，每行一个股票代码（例如 `AAPL`, `TSLA`）。

**使用方法**:
```bash
python3 daily_stock_option_data.py
```

**输出**:
-   数据保存在 `data2/` 目录下。
-   生成 Excel 文件 `all_stocks_data_{YYYYMMDD}.xlsx`，包含历史行情数据。

---

### 3. 股票智能诊断 (stock_diagnosis.py)

**路径**: `stock_diagnosis.py`

**功能**:
对单个股票的历史数据进行深度技术面分析，生成诊断报告。分析内容包括趋势判定、乖离率、RSI/MACD/KDJ 指标解读、K 线形态识别以及基于线性回归的价格预测。

**使用方法**:
该脚本设计为命令行工具，需要指定输入的数据文件（通常是 `daily_stock_option_data.py` 下载的数据或其他符合格式的 TSV/CSV 文件）。

```bash
python3 stock_diagnosis.py -i <数据文件路径>
```

**示例**:
```bash
python3 stock_diagnosis.py -i data/AAPL.tsv
```

**输出**:
-   在终端打印详细的诊断报告，包括市场状态、关键指标解读、未来走势预测和操作建议。

---

### 4. 获取富途 24 小时快讯 (get_futu_24hour_news.py)

**路径**: `get_futu_24hour_news/get_futu_24hour_news.py`

**功能**:
抓取富途牛牛的 24 小时财经快讯，自动筛选出“昨天 00:00”到“今天 00:00”之间的新闻，并将时间转换为美东时间。

**使用方法**:
```bash
python3 get_futu_24hour_news/get_futu_24hour_news.py
```

**输出**:
-   `get_futu_24hour_news/futu_flash_news.csv`: 包含抓取到的快讯数据（ID, 美东时间, 标题, 摘要, 来源, URL）。

