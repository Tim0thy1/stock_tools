#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import pandas as pd
import time
import os
import sys
import threading
import pytz
import json
import rea
import pickle
import argparse
from datetime import datetime, timezone
from yahooquery import Ticker
#from googletrans import Translator
from typing import List, Dict, Any

# ====== US quotes 缓存（全局） ======
_stock_cache: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL = 30  # 秒

def get_us_quotes(tickers: List[str]) -> Dict[str, dict]:
    """带 30 秒 TTL 的 Yahoo quotes 获取（全局缓存）"""
    now = time.time()
    to_fetch = [t for t in tickers if t not in _stock_cache or now - _stock_cache[t]['ts'] > _CACHE_TTL]
    if to_fetch:
        try:
            tk = Ticker(to_fetch, params={"overnightPrice": "true"})
            fetched = tk.quotes if isinstance(tk.quotes, dict) else {}
        except Exception as e:
            print(f"❌ Yahoo API 获取失败: {e}")
            fetched = {}
        for t in to_fetch:
            _stock_cache[t] = {'ts': now, 'data': fetched.get(t, {})}
    return {t: _stock_cache.get(t, {}).get('data', {}) for t in tickers}


# ====== 刷新时间设置（秒） ======
CRYPTO_REFRESH_INTERVAL = 60      # 虚拟币刷新间隔（60秒）
STOCK_REFRESH_INTERVAL = 100      # 美股刷新间隔（10分钟=600秒）
NEWS_REFRESH_INTERVAL = 300       # 新闻刷新间隔（5分钟=300秒）
MAIN_LOOP_INTERVAL = 60           # 主循环间隔（60秒）

# ====== 虚拟币持仓（成本价与持仓量，size可为杠杆后实际仓位） ======
crypto_positions = {
    "BTCUSDT": {"cost": 0.0, "size": 0.0264},
    "ETHUSDT": {"cost": 0.0, "size": 0.936},
    "BNBUSDT": {"cost": 0.0, "size": 0.0}
}
crypto_positions_spec = {
    "BTCUSDT": "-92264*0.0168",
    "ETHUSDT": "0.0",
    "BNBUSDT": "0*0"
}
_tmp = {}
for _k, _v in crypto_positions_spec.items():
    if isinstance(_v, str) and '*' in _v:
        _p = _v.split('*')
        if len(_p) >= 2:
            try:
                _tmp[_k] = {"cost": float(_p[0]), "size": float(_p[1])}
            except Exception:
                pass
if _tmp:
    crypto_positions.update(_tmp)

# ====== 美股文件路径 ======
STOCK_FILE = "stocks.txt"

# ====== 新闻API URL ======
NEWS_API_URL_EN = "https://static.mktnews.net/json/flash/en.json"  # 英文新闻源
NEWS_API_URL_CN = "https://www.cls.cn/nodeapi/telegraphList"       # 财联社中文新闻源

# ====== 新闻翻译缓存文件 ======
NEWS_CACHE_FILE = "news_translation_cache.pkl"

# ====== 控制退出和手动刷新 ======
stop_flag = False
manual_refresh_flag = False
show_more_news = False
current_news_source = 2  # 默认使用财联社中文新闻源 (1=英文新闻源, 2=财联社中文新闻源)

# ====== 命令行参数解析 ======
def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='实时市场监控工具')
    parser.add_argument('-s', '--source', 
                       choices=['e', 'c'], 
                       default='c',
                       help='选择新闻源: e=英文新闻源, c=财联社中文新闻源 (默认: c)')
    return parser.parse_args()

# ====== 字符串显示宽度计算函数 ======
def get_display_width(text):
    """计算字符串的显示宽度（中文字符占2个宽度）"""
    width = 0
    for char in text:
        if ord(char) > 127:  # 非ASCII字符（包括中文）
            width += 2
        else:
            width += 1
    return width

def format_with_width(text, target_width):
    """格式化字符串，考虑中文字符宽度"""
    current_width = get_display_width(text)
    if current_width >= target_width:
        return text
    else:
        return text + " " * (target_width - current_width)

# 解析命令行参数并设置新闻源
args = parse_arguments()
if args.source == 'e':
    current_news_source = 1  # 英文新闻源
else:
    current_news_source = 2  # 财联社中文新闻源

# ====== 辅助函数 ======
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def key_listener():
    global stop_flag, manual_refresh_flag, show_more_news, current_news_source
    while True:
        key = sys.stdin.read(1).lower()
        if key == 'q':
            stop_flag = True
            break
        elif key == 'w':
            manual_refresh_flag = True
        elif key == 'm':
            show_more_news = not show_more_news
            manual_refresh_flag = True

# ====== 虚拟币价格获取 ======
def fetch_prices_from_gate():
    url = "https://api.gateio.ws/api/v4/spot/tickers"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        prices = {}
        for item in data:
            symbol = item.get("currency_pair", "")
            if symbol in ["BTC_USDT", "ETH_USDT", "BNB_USDT"]:
                last_price = float(item.get("last", 0))
                prices[symbol.replace("_", "")] = last_price
        return prices
    except Exception as e:
        print(f"❌ Gate.io API 错误: {e}")
        return {}

# ====== 时段检测 ======
def detect_session():
    ny_tz = pytz.timezone('America/New_York')
    ny_time = datetime.now(ny_tz)
    hour = ny_time.hour
    minute = ny_time.minute
    
    if (hour == 4 and minute >= 0) or (hour >= 5 and hour < 9) or (hour == 9 and minute < 30):
        phase = "盘前"
        active_price_key = "preMarketPrice"
        active_change_key = "preMarketChangePercent"
    elif (hour == 9 and minute >= 30) or (hour >= 10 and hour < 16):
        phase = "盘中"
        active_price_key = "regularMarketPrice"
        active_change_key = "regularMarketChangePercent"
    elif (hour >= 16 and hour < 20):
        phase = "盘后"
        active_price_key = "postMarketPrice"
        active_change_key = "postMarketChangePercent"
    else:
        phase = "隔夜"
        active_price_key = "overnightMarketPrice"
        active_change_key = "overnightMarketChangePercent"
    
    return ny_time.strftime('%H:%M'), phase, active_price_key, active_change_key

# ====== 读取 stocks.txt（支持第二列 1/2 标记和第三列成本价*持仓票数，识别港股） ======
def read_stocks(file_path):
    us_tickers = []  # 美股代码
    hk_tickers = []  # 港股代码
    marks = {}
    cost_and_shares = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                t = parts[0].upper()
                
                # 判断是否为港股（数字开头）
                if t[0].isdigit():
                    hk_tickers.append(t)
                else:
                    us_tickers.append(t)
                
                mark = ""
                if len(parts) > 1:
                    if parts[1] == "1":
                        mark = "🚀"
                    elif parts[1] == "2":
                        mark = "⚡"
                if mark:
                    marks[t] = mark
                # 解析第三列或第四列的成本价*持仓票数格式
                if len(parts) > 2:
                    # 检查第三列是否包含成本价*持仓票数
                    cost_shares_str = parts[2]
                    if '*' in cost_shares_str:
                        try:
                            cost_price, shares = cost_shares_str.split('*')
                            cost_and_shares[t] = {
                                'cost_price': float(cost_price),
                                'shares': float(shares)
                            }
                        except (ValueError, IndexError):
                            pass
                    # 如果第三列不包含，检查第四列
                    elif len(parts) > 3:
                        cost_shares_str = parts[3]
                        if '*' in cost_shares_str:
                            try:
                                cost_price, shares = cost_shares_str.split('*')
                                cost_and_shares[t] = {
                                    'cost_price': float(cost_price),
                                    'shares': float(shares)
                                }
                            except (ValueError, IndexError):
                                pass
    except FileNotFoundError:
        return [], [], {}, {}
    return us_tickers, hk_tickers, marks, cost_and_shares

# ====== 港股价格获取函数 ======
def get_hk_stock_price(hk_tickers, marks={}, cost_and_shares={}):
    if not hk_tickers:
        return pd.DataFrame()
    
    url = "http://qt.gtimg.cn/q"
    # 为港股代码添加前缀
    code_list = [f"r_hk{code}" for code in hk_tickers]
    code_str = ",".join(code_list)
    
    try:
        response = requests.get(url, params={'q': code_str, 'fmt': 'json'})
        stock_list = response.json()
        
        stock_data = []
        for stock_code, stock_info in stock_list.items():
            # 移除前缀获取原始代码
            original_code = stock_code.replace('r_hk', '')
            
            # 获取股票信息
            name = stock_info[1] if len(stock_info) > 1 else "N/A"
            price = float(stock_info[3]) if len(stock_info) > 3 and stock_info[3] else 0.0
            change_percent = float(stock_info[32]) if len(stock_info) > 32 and stock_info[32] else 0.0
            
            # 格式化显示
            price_s = f"{price:.2f}" if price > 0 else "N/A"
            change_s = f"{change_percent:+.2f}%" if change_percent != 0 else "0.00%"
            
            stock_data.append({
                'Ticker': original_code,
                'Name': name,
                'Price': price_s,
                'Change': change_s,
            })
        
        df = pd.DataFrame(stock_data)
        return df
        
    except Exception as e:
        print(f"获取港股数据失败: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

# ====== 抓取并构建 DataFrame（优化时段价格获取逻辑） ======
def fetch_all_stocks(file_path, active_price_key, active_change_key):
    us_tickers, hk_tickers, marks, cost_and_shares = read_stocks(file_path)
    if not us_tickers:
        return pd.DataFrame()

    # ====== 获取 US quotes，一次性调用全局缓存函数 ======
    quotes_all = get_us_quotes(us_tickers)

    rows = []
    for t in us_tickers:
        q = (quotes_all or {}).get(t, {})
        if not isinstance(q, dict):
            q = {}

        # 所有可能的价格字段对
        field_pairs = [
            ("preMarketPrice", "preMarketChangePercent"),
            ("regularMarketPrice", "regularMarketChangePercent"),
            ("postMarketPrice", "postMarketChangePercent"),
            ("overnightMarketPrice", "overnightMarketChangePercent"),
        ]

        # previous close 用于计算 fallback 的百分比
        prev_close = q.get("regularMarketPrice")

        # 1) 优先获取当前时段的价格和涨跌幅
        active_price = q.get(active_price_key)
        active_change = q.get(active_change_key)

        # 2) 如果当前时段数据不可用，按时间逻辑回退
        if active_price is None:
            # 根据当前时段智能回退
            if active_price_key == "preMarketPrice":
                # 盘前时段：回退到前一日收盘价或隔夜价格
                fallback_order = ["overnightMarketPrice", "regularMarketPrice", "postMarketPrice"]
            elif active_price_key == "regularMarketPrice":
                # 正常交易时段：回退到盘前价格或前一日收盘价
                fallback_order = ["preMarketPrice", "postMarketPrice", "overnightMarketPrice"]
            elif active_price_key == "postMarketPrice":
                # 盘后时段：回退到正常交易价格或盘前价格
                fallback_order = ["regularMarketPrice", "preMarketPrice", "overnightMarketPrice"]
            else:
                # 隔夜时段：回退到盘后价格或正常交易价格
                fallback_order = ["postMarketPrice", "regularMarketPrice", "preMarketPrice"]
            
            for pf in fallback_order:
                p = q.get(pf)
                if p is not None:
                    active_price = p
                    # 找到对应的涨跌幅字段
                    matching_cf = None
                    for pair in field_pairs:
                        if pair[0] == pf:
                            matching_cf = pair[1]
                            break
                    if matching_cf:
                        active_change = q.get(matching_cf)
                    break

        # 3) 涨跌幅直接从API字段获取，不再手动计算

        # 格式化数据，为Last Close添加固定宽度以对齐emoji
        active_price_s = f"{float(active_price):.2f}" if active_price is not None else "N/A"
        active_change_s = f"{float(active_change):+.2f}%" if active_change is not None else "N/A"
        prev_close_s = f"{float(prev_close):.2f}".rjust(8) if prev_close is not None else "N/A".rjust(8)

        prefix = marks.get(t, "")
        # 设置优先级：🚀=3, ⚡=2, 无标记=1
        if prefix == "🚀":
            priority = 3
        elif prefix == "⚡":
            priority = 2
        else:
            priority = 1
        
        # 为没有标记的股票添加占位符，保持对齐
        if prefix:
            ticker_display = prefix + "" + t
        else:
            ticker_display = "  " + t  # 两个空格占位符，与⚡长度相同
        
        # 计算浮盈浮亏并添加到Change列
        profit_loss_str = ""
        if t in cost_and_shares and active_price is not None:
            cost_info = cost_and_shares[t]
            cost_price = cost_info['cost_price']
            shares = cost_info['shares']
            # 判断是否为做空仓位：成本价为负表示做空
            if cost_price < 0:
                # 做空收益：(开仓价的绝对值 - 当前价) * 持仓股数
                profit_loss = (abs(cost_price) - float(active_price)) * shares
            else:
                # 多头收益：(当前价 - 成本价) * 持仓股数
                profit_loss = (float(active_price) - cost_price) * shares
            profit_loss_str = f"({profit_loss:+.2f})"
        
        # 修改Change列格式，添加浮盈浮亏
        if profit_loss_str:
            change_display = f"{active_change_s}{profit_loss_str}"
        else:
            change_display = active_change_s

        rows.append({
            "Last Close": prev_close_s,
            "Ticker": ticker_display,
            "Priority": priority,
            "Price": active_price_s,
            "Change": change_display
        })

    df = pd.DataFrame(rows)
    return df

# ====== 英文新闻模块 ======
def fetch_news_data_en():
    """获取英文新闻数据"""
    try:
        # 添加时间戳参数避免缓存
        timestamp = int(time.time() * 1000)
        url = f"{NEWS_API_URL_EN}?t={timestamp}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"❌ 英文新闻API获取失败: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ 英文新闻JSON解析失败: {e}")
        return None

# ====== 财联社新闻模块 ======
def fetch_news_data_cn():
    """获取财联社中文新闻数据"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        params = {
            "app": "CailianpressWeb",
            "os": "web", 
            "refresh_type": "1",
            "rn": "100",  # 增加获取数量到100条
            "sv": "8.4.6"
        }
        response = requests.get(NEWS_API_URL_CN, params=params, timeout=10, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"❌ 财联社新闻API获取失败: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ 财联社新闻JSON解析失败: {e}")
        return None

def format_news_time(time_str):
    """格式化新闻时间字符串，转换为东8区时间"""
    try:
        # 解析ISO格式时间
        dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        # 转换为东8区时间
        china_tz = pytz.timezone('Asia/Shanghai')
        china_time = dt.astimezone(china_tz)
        # 返回格式化的时间字符串和datetime对象
        return china_time.strftime('%m-%d %H:%M'), china_time
    except ValueError:
        return time_str[:10], None

def format_news_time_cn(timestamp):
    """格式化财联社新闻时间戳"""
    try:
        # 财联社时间戳是秒级的
        dt = datetime.fromtimestamp(timestamp, tz=pytz.timezone('Asia/Shanghai'))
        return dt.strftime('%m-%d %H:%M'), dt
    except Exception:
        return "未知时间", None

def clean_news_content(content):
    """清理新闻内容，移除HTML标签"""
    # 移除HTML标签
    content = re.sub(r'<[^>]+>', '', content)
    # 移除多余的空白字符
    content = re.sub(r'\s+', ' ', content).strip()
    return content

# ====== 新闻翻译缓存管理 ======
def load_translation_cache():
    """加载翻译缓存"""
    try:
        with open(NEWS_CACHE_FILE, 'rb') as f:
            return pickle.load(f)
    except (FileNotFoundError, pickle.PickleError):
        return {}

def save_translation_cache(cache):
    """保存翻译缓存"""
    try:
        with open(NEWS_CACHE_FILE, 'wb') as f:
            pickle.dump(cache, f)
    except Exception as e:
        print(f"❌ 保存翻译缓存失败: {e}")

def get_news_key(news_item):
    """生成新闻的唯一标识符"""
    # 使用新闻内容的前50个字符作为key
    content = news_item.get('content', '')
    return content[:50] if content else str(hash(str(news_item)))

def translate_news_text_cached(text, cache, translator):
    """带缓存的新闻翻译"""
    if not text or len(text.strip()) == 0:
        return text
    
    # 检查缓存
    if text in cache:
        return cache[text]
    
    try:
        # 翻译文本
        translated = translator.translate(text, src='en', dest='zh-cn')
        translated_text = translated.text
        
        # 保存到缓存
        cache[text] = translated_text
        return translated_text
    except Exception as e:
        print(f"❌ 翻译失败: {e}")
        return text

def fetch_latest_news(count=5):
    """获取最新新闻，根据当前新闻源选择"""
    global current_news_source
    
    if current_news_source == 1:
        return fetch_latest_news_en(count)
    else:
        return fetch_latest_news_cn(count)

def fetch_latest_news_en(count=5):
    """获取最新英文新闻并翻译"""
    news_data = fetch_news_data_en()
    if not news_data:
        return []
    
    # 加载翻译缓存
    cache = load_translation_cache()
    translator = Translator()
    
    news_list = []
    # 英文新闻API返回的是数组，不是对象
    items = news_data[:count] if isinstance(news_data, list) else []
    
    for item in items:
        try:
            # 格式化时间
            time_str, dt = format_news_time(item.get('time', ''))
            
            # 获取重要性标记 - 英文新闻使用important字段
            importance = item.get('important', 0)
            if importance >= 2:
                importance_mark = "🔴"
            elif importance == 1:
                importance_mark = "🟡"
            else:
                importance_mark = "⚪"
            
            # 清理和翻译内容 - 英文新闻内容在data.content字段
            content_data = item.get('data', {})
            content = clean_news_content(content_data.get('content', ''))
            translated_content = translate_news_text_cached(content, cache, translator)
            
            news_list.append({
                'time': time_str,
                'importance': importance_mark,
                'content': translated_content
            })
            
        except Exception as e:
            continue
    
    # 保存更新后的缓存
    save_translation_cache(cache)
    
    return news_list

def fetch_latest_news_cn(count=5):
    """获取最新财联社中文新闻"""
    news_data = fetch_news_data_cn()
    if not news_data:
        return []
    
    news_list = []
    items = news_data.get('data', {}).get('roll_data', [])[:count]
    
    for item in items:
        try:
            # 格式化时间
            ctime = item.get('ctime', 0)
            time_str, dt = format_news_time_cn(ctime)
            
            # 财联社新闻等级映射
            level = item.get('level', 'C')
            if level == 'A':
                importance_mark = "🔴"
            elif level == 'B':
                importance_mark = "🟡"
            else:
                importance_mark = "⚪"
            
            # 获取内容（财联社是中文，不需要翻译）
            content = clean_news_content(item.get('content', ''))
            
            news_list.append({
                'time': time_str,
                'importance': importance_mark,
                'content': content
            })
            
        except Exception as e:
            continue
    
    return news_list

# ====== 主循环 ======
def main():
    global stop_flag, manual_refresh_flag, show_more_news, current_news_source
    threading.Thread(target=key_listener, daemon=True).start()
    
    # 显示当前新闻源设置
    current_source_name = "英文新闻源" if current_news_source == 1 else "财联社中文新闻源"
    print(f"当前新闻源: {current_source_name}")
    print("按 Q 退出程序，按 W 手动刷新所有数据，按 M 切换新闻数量.\n")
    time.sleep(1)

    last_stock_update = 0
    last_news_update = 0
    stock_df = pd.DataFrame()
    hk_stock_df = pd.DataFrame()  # 添加港股DataFrame
    news_list = []

    while not stop_flag:
        now = time.time()
        prices = fetch_prices_from_gate()
        ny_time, phase, active_price_key, active_change_key = detect_session()

        # 检查是否需要手动刷新
        force_refresh = manual_refresh_flag
        if manual_refresh_flag:
            manual_refresh_flag = False  # 重置标志

        # 每10分钟更新一次美股数据（或第一次或手动刷新）
        if now - last_stock_update > STOCK_REFRESH_INTERVAL or stock_df.empty or force_refresh:
            stock_df = fetch_all_stocks(STOCK_FILE, active_price_key, active_change_key)
            
            # 同时获取港股数据
            us_tickers, hk_tickers, marks, cost_and_shares = read_stocks(STOCK_FILE)
            if hk_tickers:
                hk_stock_df = get_hk_stock_price(hk_tickers, marks, cost_and_shares)
            
            last_stock_update = now

        # 每5分钟更新一次新闻数据（或第一次或手动刷新）
        if now - last_news_update > NEWS_REFRESH_INTERVAL or not news_list or force_refresh:
            # 根据show_more_news标志决定显示数量
            news_count = 10 if show_more_news else 5
            news_list = fetch_latest_news(news_count)
            last_news_update = now
            
            # 如果是手动刷新触发的，在下一个周期重置为默认显示数量
            if force_refresh and show_more_news:
                # 设置一个标志，在下一个自动刷新周期重置
                pass

        clear_screen()
        
        print("=== 综合行情显示 ===")
        # print(f"⏰ 本地时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        # print(f"   美东时间: {ny_time}  - {phase}  (使用: {active_price_key} / {active_change_key})\n")
        print()

        # 新闻部分 - 第一位
        if news_list:
            news_count_display = len(news_list)
            news_source_name = "英文新闻" if current_news_source == 1 else "财联社"
            print(f"📰 最新财经新闻（{news_source_name} - 最近{news_count_display}条）:")
            print("-" * 70)
            for i, news in enumerate(news_list, 1):
                print(f"{news['time']} {news['importance']} {news['content']}")
        else:
            print("📰 新闻获取失败")

        print()

        # 美股部分 - 第二位：只显示当前时段 price + change
        if not stock_df.empty:
            df_sorted = stock_df.copy()

            # 把 Change 字符串转换为数值用于排序（将 "N/A" 视作 0）
            def parse_pct(s):
                try:
                    return float(str(s).replace("%", "").replace("+", ""))
                except Exception:
                    return 0.0

            df_sorted["val"] = df_sorted["Change"].apply(parse_pct)
            df_sorted = df_sorted.sort_values(by=["Priority", "val"], ascending=[False, False]).drop(columns=["Priority", "val"])

            # add arrow
            def add_arrow(s):
                if str(s).startswith("+"):
                    return s + " "
                elif str(s).startswith("-"):
                    return s + " "
                else:
                    return s + " "
                return s

            df_sorted["Change"] = df_sorted["Change"].apply(add_arrow)

            print(f"📊 美股行情（当前时段价格 & 涨跌%）:")
            
            # 两列显示：将股票分成两组
            total_stocks = len(df_sorted)
            mid_point = (total_stocks + 1) // 2
            
            left_df = df_sorted.iloc[:mid_point].reset_index(drop=True)
            right_df = df_sorted.iloc[mid_point:].reset_index(drop=True)
            
            # 格式化左右两列的字符串
            left_strings = []
            right_strings = []
            
            for i in range(max(len(left_df), len(right_df))):
                # 左列
                if i < len(left_df):
                    row = left_df.iloc[i]
                    # 截断股票名字以适应显示宽度
                    if 'Name' in row:
                        name_display = row['Name'][:6] if get_display_width(row['Name']) > 12 else row['Name']
                    else:
                        name_display = row['Ticker']  # 如果没有Name列，使用Ticker
                    
                    name_formatted = format_with_width(name_display, 12)
                    price_formatted = format_with_width(str(row['Price']), 6)
                    change_formatted = format_with_width(str(row['Change']), 8)
                    left_str = f"{name_formatted} {price_formatted} {change_formatted}"
                else:
                    left_str = " " * 26
                left_strings.append(left_str)
                
                # 右列
                if i < len(right_df):
                    row = right_df.iloc[i]
                    # 截断股票名字以适应显示宽度
                    if 'Name' in row:
                        name_display = row['Name'][:6] if get_display_width(row['Name']) > 12 else row['Name']
                    else:
                        name_display = row['Ticker']  # 如果没有Name列，使用Ticker
                    
                    name_formatted = format_with_width(name_display, 12)
                    price_formatted = format_with_width(str(row['Price']), 6)
                    change_formatted = format_with_width(str(row['Change']), 8)
                    right_str = f"{name_formatted} {price_formatted} {change_formatted}"
                else:
                    right_str = ""
                right_strings.append(right_str)
            
            # 打印表头
            header_name = format_with_width("Name", 12)
            header_price = format_with_width("Price", 6)
            header_change = format_with_width("Change", 8)
            header_left = f"{header_name} {header_price} {header_change}"
            header_right = f"{header_name} {header_price} {header_change}"
            print(f"{header_left}    {header_right}")
            print("-" * 60)
            
            # 打印数据行
            for left, right in zip(left_strings, right_strings):
                if right.strip():
                    print(f"{left}    {right}")
                else:
                    print(left)
        else:
            print("📊 未找到美股列表 (请创建 stocks.txt)")

        print()

        # 港股部分 - 第三位：显示港股价格和涨跌幅
        if not hk_stock_df.empty:
            print(f"🏢 港股行情:")
            
            # 按涨跌幅排序，涨幅大的在前面
            # 将Change列的字符串格式（如"+2.50%"）转换为数值进行排序
            def parse_change(change_str):
                try:
                    # 移除%符号并转换为浮点数
                    return float(change_str.replace('%', ''))
                except:
                    return 0.0
            
            hk_stock_df['change_numeric'] = hk_stock_df['Change'].apply(parse_change)
            hk_stock_df_sorted = hk_stock_df.sort_values('change_numeric', ascending=False).reset_index(drop=True)
            # 删除临时列
            hk_stock_df_sorted = hk_stock_df_sorted.drop('change_numeric', axis=1)
            
            # 两列显示：将港股分成两组
            total_hk_stocks = len(hk_stock_df_sorted)
            mid_point = (total_hk_stocks + 1) // 2
            
            left_df = hk_stock_df_sorted.iloc[:mid_point].reset_index(drop=True)
            right_df = hk_stock_df_sorted.iloc[mid_point:].reset_index(drop=True)
            
            # 格式化左右两列的字符串
            left_strings = []
            right_strings = []
            
            for i in range(max(len(left_df), len(right_df))):
                # 左列
                if i < len(left_df):
                    row = left_df.iloc[i]
                    # 截断股票名字以适应显示宽度 - 缩小到3个中文字符（6个显示单位）
                    if 'Name' in row:
                        name_display = row['Name']
                        if get_display_width(name_display) > 8:
                            # 截断到6个显示单位（约3个中文字符）
                            truncated = ""
                            for char in name_display:
                                if get_display_width(truncated + char) <= 8:
                                    truncated += char
                                else:
                                    break
                            name_display = truncated
                    else:
                        name_display = row['Ticker']  # 如果没有Name列，使用Ticker
                    
                    name_formatted = format_with_width(name_display, 8)
                    price_formatted = format_with_width(str(row['Price']), 5)
                    change_formatted = format_with_width(str(row['Change']), 6)
                    left_str = f"{name_formatted} {price_formatted} {change_formatted}"
                else:
                    left_str = " " * 18
                left_strings.append(left_str)
                
                # 右列
                if i < len(right_df):
                    row = right_df.iloc[i]
                    # 截断股票名字以适应显示宽度 - 缩小到3个中文字符（6个显示单位）
                    if 'Name' in row:
                        name_display = row['Name']
                        if get_display_width(name_display) > 8:
                            # 截断到6个显示单位（约3个中文字符）
                            truncated = ""
                            for char in name_display:
                                if get_display_width(truncated + char) <= 8:
                                    truncated += char
                                else:
                                    break
                            name_display = truncated
                    else:
                        name_display = row['Ticker']  # 如果没有Name列，使用Ticker
                    
                    name_formatted = format_with_width(name_display, 6)
                    price_formatted = format_with_width(str(row['Price']), 5)
                    change_formatted = format_with_width(str(row['Change']), 6)
                    right_str = f"{name_formatted} {price_formatted} {change_formatted}"
                else:
                    right_str = ""
                right_strings.append(right_str)
            
            # 打印表头
            header_name = format_with_width("Name", 6)
            header_price = format_with_width("Price", 5)
            header_change = format_with_width("Change", 6)
            header_left = f"{header_name} {header_price} {header_change}"
            header_right = f"{header_name} {header_price} {header_change}"
            print(f"{header_left}  {header_right}")
            print("-" * 38)
            
            # 打印数据行
            for left, right in zip(left_strings, right_strings):
                if right.strip():
                    print(f"{left}  {right}")
                else:
                    print(left)

        print()

        print("💰 虚拟币行情（Gate.io）：")
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        for sym in symbols:
            price = prices.get(sym)
            if price is None:
                print(f"{sym}: 获取失败")
            else:
                pos_info = crypto_positions.get(sym, {"cost": 0.0, "size": 0.0})
                cost = pos_info.get("cost", 0.0)
                size = pos_info.get("size", 0.0)
                if size and cost:
                    notional = abs(cost) * size
                    margin = notional
                    if cost > 0:
                        pnl = (price - cost) * size
                        roi_pct = (pnl / margin) * 100 if margin else 0.0
                        pos = "多头"
                        cdisp = cost
                    else:
                        pnl = (abs(cost) - price) * size
                        roi_pct = (pnl / margin) * 100 if margin else 0.0
                        pos = "做空"
                        cdisp = abs(cost)
                    print(f"{sym}: {price:,.2f} | 成本 {cdisp:,.2f}*{size} {pos} | 盈亏 {pnl:+.2f} (ROI {roi_pct:+.2f}%)")
                else:
                    print(f"{sym}: {price:,.2f}")

        print()



        #print(f"\n(虚拟币每{CRYPTO_REFRESH_INTERVAL}秒刷新 | 美股每{STOCK_REFRESH_INTERVAL//60}分钟刷新 | 新闻每{NEWS_REFRESH_INTERVAL//60}分钟刷新)")
        print("按 Q 退出 | 按 W 手动刷新 | 按 M 切换新闻数量")
        
        # 在循环中检查是否需要重置新闻显示数量
        for i in range(MAIN_LOOP_INTERVAL):
            if stop_flag:
                break
            # 如果用户按下 W 请求手动刷新，则立即跳出等待循环
            if manual_refresh_flag:
                break
            # 在自动刷新周期中重置show_more_news标志
            if i == MAIN_LOOP_INTERVAL//2 and show_more_news and not manual_refresh_flag:
                show_more_news = False
            time.sleep(1)

    print("\n程序已退出。")

# ====== 启动入口 ======
if __name__ == '__main__':
    if os.name != 'nt':
        import termios, tty
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)
    try:
        main()
    finally:
        if os.name != 'nt':
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

