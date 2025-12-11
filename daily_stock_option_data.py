#!/usr/bin/env python3
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import os

# ========= 计算技术指标 =========
def calc_indicators(df):
    macd = ta.macd(df["Close"])
    if macd is not None:
        df["MACD"] = macd["MACD_12_26_9"]
        df["MACD_signal"] = macd["MACDs_12_26_9"]
        df["MACD_hist"] = macd["MACDh_12_26_9"]

    df["RSI"] = ta.rsi(df["Close"], length=14)

    stoch = ta.stoch(df["High"], df["Low"], df["Close"])
    if stoch is not None:
        df["K"] = stoch["STOCHk_14_3_3"]
        df["D"] = stoch["STOCHd_14_3_3"]
        df["J"] = 3 * df["K"] - 2 * df["D"]

    for ma in [5, 10, 20, 50, 60, 120]:
        df[f"MA{ma}"] = df["Close"].rolling(ma).mean()

    df["Pct_Change"] = df["Close"].pct_change() * 100

    return df


# ========= 获取股票历史数据 =========
def fetch_and_process_stock(code, interval="1d"):
    print(f"📌 Fetching history ({interval}): {code} ...")

    end = datetime.today()
    start = end - timedelta(days=180) # 过去6个月

    try:
        # 30m, 60m 数据最多只能获取 60 天的数据，这是 yfinance 的限制
        # 如果是 1d 数据，可以获取 6 个月
        # 这里对于 30m, 60m 我们尽最大可能获取（yfinance 限制 60d）
        fetch_start = start
        if interval in ["30m", "60m"]:
            fetch_start = end - timedelta(days=59) # 稍微少于 60 天以避免边界问题
        
        df = yf.download(code, start=fetch_start, end=end, interval=interval, progress=False, auto_adjust=False)
    except Exception as e:
        print(f"❌ Error downloading {code} ({interval}): {e}")
        return None

    if df is None or df.empty:
        print(f"❌ Failed: {code} ({interval}) 无历史数据")
        return None

    # 扁平化列名
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    rename_map = {
        "Open": "Open",
        "High": "High",
        "Low": "Low",
        "Close": "Close",
        "Adj Close": "Adj_Close",
        "Volume": "Volume",
    }
    df = df.rename(columns=rename_map)

    if "Close" not in df.columns:
        print(f"❌ ERROR: {code} ({interval}) 没有 Close 列: {df.columns}")
        return None

    df = calc_indicators(df)
    df = df.round(3)

    df["Ticker"] = code
    df["Interval"] = interval
    cols = ["Ticker", "Interval"] + [c for c in df.columns if c not in ["Ticker", "Interval"]]
    df = df[cols]

    return df


# ========= 获取期权链 =========
def fetch_options(code):
    print(f"📌 Fetching options: {code} ...")

    try:
        ticker = yf.Ticker(code)
        expirations = ticker.options
    except Exception as e:
        print(f"❌ Cannot fetch option expirations for {code}: {e}")
        return None, None

    if not expirations:
        print(f"⚠️ No options for {code}")
        return None, None

    try:
        spot_df = ticker.history(period='1d')
        spot = float(spot_df['Close'].iloc[-1]) if not spot_df.empty else None
    except Exception:
        spot = None

    today = datetime.today().date()
    max_exp = today + timedelta(days=180) # 6个月内

    all_raw = []
    all_calls_filtered = []

    for exp in expirations:
        try:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            if exp_date < today or exp_date > max_exp:
                continue

            chain = ticker.option_chain(exp)

            calls = chain.calls.copy()
            puts = chain.puts.copy()

            calls["expiration"] = exp
            calls["option_type"] = "call"
            calls["Ticker"] = code

            puts["expiration"] = exp
            puts["option_type"] = "put"
            puts["Ticker"] = code

            all_raw.append(calls)
            all_raw.append(puts)

            df_calls = calls
            if spot is not None and "strike" in df_calls.columns:
                lower = 0.7 * spot
                upper = 1.3 * spot
                df_calls = df_calls[(df_calls["strike"] >= lower) & (df_calls["strike"] <= upper)]

            all_calls_filtered.append(df_calls)
        except Exception as e:
            print(f"⚠️ Error fetching {code} option {exp}: {e}")
            continue

    raw_df = pd.concat(all_raw, ignore_index=True).round(4) if all_raw else None
    filt_df = pd.concat(all_calls_filtered, ignore_index=True).round(4) if all_calls_filtered else None
    return raw_df, filt_df


# ========= 主程序 =========
def main():
    list_file = "stock.list"
    if not os.path.exists(list_file):
        print(f"❌ Error: {list_file} 不存在")
        return

    with open(list_file) as f:
        codes = [line.strip() for line in f if line.strip()]

    all_history_1d = []
    all_history_30m = []
    all_history_60m = []
    all_options_raw = []
    all_options_filt = []

    for code in codes:
        # 历史数据 - 1d
        hist_df_1d = fetch_and_process_stock(code, interval="1d")
        if hist_df_1d is not None:
            all_history_1d.append(hist_df_1d)

        # 历史数据 - 30m
        hist_df_30m = fetch_and_process_stock(code, interval="30m")
        if hist_df_30m is not None:
            all_history_30m.append(hist_df_30m)

        # 历史数据 - 60m
        hist_df_60m = fetch_and_process_stock(code, interval="60m")
        if hist_df_60m is not None:
            all_history_60m.append(hist_df_60m)

        # 期权链
        raw_df, opt_df = fetch_options(code)
        if raw_df is not None:
            all_options_raw.append(raw_df)
        if opt_df is not None:
            all_options_filt.append(opt_df)

    date_tag = datetime.today().strftime("%Y%m%d")
    out_dir = os.path.join(os.getcwd(), "data2")
    os.makedirs(out_dir, exist_ok=True)

    # 保存历史行情到 Excel (分 3 个 sheet)
    if all_history_1d or all_history_30m or all_history_60m:
        print("\n📦 Saving historical data to Excel...")
        hist_path = os.path.join(out_dir, f"all_stocks_data_{date_tag}.xlsx")
        
        with pd.ExcelWriter(hist_path, engine='openpyxl') as writer:
            if all_history_1d:
                df_hist_1d = pd.concat(all_history_1d)
                # 移除 timezone 信息
                if pd.api.types.is_datetime64_any_dtype(df_hist_1d.index):
                    df_hist_1d.index = df_hist_1d.index.tz_localize(None)
                df_hist_1d.to_excel(writer, sheet_name="Daily", index=True, index_label="Date")
            
            if all_history_30m:
                df_hist_30m = pd.concat(all_history_30m)
                # 移除 timezone 信息
                if pd.api.types.is_datetime64_any_dtype(df_hist_30m.index):
                    df_hist_30m.index = df_hist_30m.index.tz_localize(None)
                df_hist_30m.to_excel(writer, sheet_name="30m", index=True, index_label="Date")
            
            if all_history_60m:
                df_hist_60m = pd.concat(all_history_60m)
                # 移除 timezone 信息
                if pd.api.types.is_datetime64_any_dtype(df_hist_60m.index):
                    df_hist_60m.index = df_hist_60m.index.tz_localize(None)
                df_hist_60m.to_excel(writer, sheet_name="60m", index=True, index_label="Date")
                
        print(f"✅ Saved: {hist_path}")

    # 保存期权链（未过滤）到 Excel
    if all_options_raw:
        print("\n📦 Saving raw option chain to Excel...")
        opt_path_raw = os.path.join(out_dir, f"all_options_raw_{date_tag}.xlsx")
        
        with pd.ExcelWriter(opt_path_raw, engine='openpyxl') as writer:
            df_opt_raw = pd.concat(all_options_raw)
            # 遍历所有列，如果是 datetime 类型且带时区，则移除时区
            for col in df_opt_raw.columns:
                if pd.api.types.is_datetime64_any_dtype(df_opt_raw[col]):
                        df_opt_raw[col] = df_opt_raw[col].dt.tz_localize(None)
            df_opt_raw.to_excel(writer, sheet_name="All_Options", index=False)
        print(f"📄 Saved: {opt_path_raw}")

    # 保存期权链（过滤后）到 Excel
    if all_options_filt:
        print("\n📦 Saving filtered option chain to Excel...")
        opt_path_filt = os.path.join(out_dir, f"all_options_filtered_{date_tag}.xlsx")

        with pd.ExcelWriter(opt_path_filt, engine='openpyxl') as writer:
            df_opt_filt = pd.concat(all_options_filt)
            # 遍历所有列，如果是 datetime 类型且带时区，则移除时区
            for col in df_opt_filt.columns:
                if pd.api.types.is_datetime64_any_dtype(df_opt_filt[col]):
                        df_opt_filt[col] = df_opt_filt[col].dt.tz_localize(None)
            df_opt_filt.to_excel(writer, sheet_name="Filtered_Options", index=False)
        print(f"📄 Saved: {opt_path_filt}")

    print("\n🎉 Done!")


if __name__ == "__main__":
    main()
