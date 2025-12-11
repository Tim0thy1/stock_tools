#!/usr/bin/env python3
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
import pytz
import time
import random

URL = "https://news.futunn.com/news-site-api/main/get-flash-list"
OUTPUT_FILE = "futu_flash_news.csv"
PAGE_SIZE = 50
TOTAL_NEWS = 10000  # 设置一个较大的上限，实际上会由时间条件终止

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36",
    "Referer": "https://news.futunn.com/",
    "Accept": "application/json, text/plain, */*",
}

def get_target_time_range():
    """
    获取目标时间范围：
    yesterday_start: 昨天 00:00:00 (本地时间)
    yesterday_end:   今天 00:00:00 (本地时间)
    返回时间戳范围
    """
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    
    # 转换为时间戳
    ts_start = int(yesterday_start.timestamp())
    ts_end = int(today_start.timestamp())
    
    return ts_start, ts_end

def ts_to_us_eastern(ts_str):
    """把 Unix 时间戳转为美东时间（自动处理夏令时）"""
    try:
        ts = int(ts_str)
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        eastern = pytz.timezone("America/New_York")
        dt_est = dt_utc.astimezone(eastern)
        return dt_est.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return ""

def fetch_news(limit=TOTAL_NEWS):
    all_news = []
    seq_mark = ""
    retry = 0
    
    ts_start, ts_end = get_target_time_range()
    print(f"🎯 目标时间范围: {datetime.fromtimestamp(ts_start)} 至 {datetime.fromtimestamp(ts_end)}")

    while len(all_news) < limit:
        params = {"pageSize": PAGE_SIZE, "_t": int(time.time() * 1000)}
        if seq_mark:
            params["seqMark"] = seq_mark

        resp = requests.get(URL, headers=HEADERS, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"❌ 请求失败 HTTP {resp.status_code}")
            break

        if not resp.text.strip():
            retry += 1
            if retry > 3:
                print("⚠️ 连续返回空响应，放弃。")
                break
            print(f"⚠️ 空响应，第 {retry} 次重试 ...")
            time.sleep(2 + random.random())
            continue

        try:
            data = resp.json()
        except Exception:
            print("⚠️ 无法解析 JSON，可能被限流或返回空。稍后重试。")
            time.sleep(2 + random.random())
            continue

        items = data.get("data", {}).get("data", {}).get("news", [])
        seq_mark = data.get("data", {}).get("data", {}).get("seqMark")
        
        if not items:
            print("⚠️ 没有更多数据或被屏蔽。")
            break
            
        # 检查本批次最旧的一条新闻时间
        last_item_time = int(items[-1].get("time"))
        
        # 过滤符合时间范围的新闻
        for item in items:
            item_time = int(item.get("time"))
            if ts_start <= item_time < ts_end:
                all_news.append(item)
        
        print(f"✅ 已抓取 {len(all_news)} 条符合条件的新闻 (当前批次最旧时间: {datetime.fromtimestamp(last_item_time)}) ...")
        
        # 如果当前批次最旧的时间已经早于昨天的开始时间，说明已经获取到了足够的数据，可以停止了
        if last_item_time < ts_start:
            print("🏁 已到达昨天之前的数据，停止抓取。")
            break

        if not data.get("data", {}).get("data", {}).get("hasMore"):
            break

        time.sleep(1.2 + random.random() * 0.8)

    return all_news

if __name__ == "__main__":
    print("📰 正在抓取富途快讯...")
    news_list = fetch_news()

    if not news_list:
        print("❌ 没抓到任何新闻。")
        exit(1)

    df = pd.DataFrame([
        {
            "id": item.get("id"),
            "time_us_eastern": ts_to_us_eastern(item.get("time")),
            "title": item.get("title")
                or item.get("brief")
                or item.get("summary")
                or (item.get("content") or "").split("。")[0],
            "summary": (
                item.get("summary")
                or item.get("brief")
                or (item.get("content") or "")[:120]
            ),
            "source": item.get("sourceName"),
            "url": item.get("detailUrl") or f"https://news.futunn.com/post/{item.get('id')}",
        }
        for item in news_list
    ])

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print(f"✅ 已保存 {OUTPUT_FILE}，共 {len(df)} 条快讯（时间为美东时区）。")

