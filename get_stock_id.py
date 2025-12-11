import requests
import json
import hashlib
import hmac
import time
import random
import pandas as pd
import os

# ================= 1. 核心加密算法 (本地修正版) =================

def hmac_encrypt(text, key):
    return hmac.new(key.encode('utf-8'), text.encode('utf-8'), hashlib.sha512).hexdigest()

def sha256_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def sss_fixed(e):
    """生成签名 Token，强制去除空格"""
    data_str = json.dumps(e.get('data'), separators=(',', ':'), ensure_ascii=False)
    if not data_str: data_str = "{}"
    t = hmac_encrypt(data_str, "quote_web")
    return sha256_hash(t[:10])[:10]

# ================= 2. 爬虫主逻辑 =================

def run_spider():
    # --- 配置区域 ---
    TOTAL_PAGES = 190       # 想要抓取的总页数
    PAGE_SIZE = 50          # 每页数据量 (不要改，50是上限)
    OUTPUT_FILE = "us_stocks_list.csv" # 保存的文件名
    
    # ！！！请务必填入最新的 Cookie 和 CSRF Token ！！！
    HEADERS = {
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
        "futu-x-csrf-token": "TrQPZf8bSxUuGhEYu3690RGc",  # <--- 替换这里
        "cookie": "cipher_device_id=1757403252389365; _ss_pp_id=d4f81c0a82f9e4fa8011757891542641; _mg_ckp=eyJja1RrZERGIjoiIn0=; __mguid_=8f69460901fdf0492jr6l000mf3ps4bm; passport_custom_data=%7B%22auth_type%22%3A%22google_one_tap%22%7D; FUTU_TIMEZONE=Asia%2FShanghai; _tt_enable_cookie=1; _ttp=01K797MW43MDBQSYXAWGRRV3V4_.tt.1; device_id=1757403252389365; __lt__cid=05598bb5-3b8a-47b3-9135-79caca447b1e; _clck=ajs404%5E2%5Eg0m%5E0%5E2122; _gac_UA-137699611-6=1.1761893098.Cj0KCQjwmYzIBhC6ARIsAHA3IkS2qoxkzfDk92xVy8HUZa7P84i1P_MZyGc7BUXrbpgrWsY0m9PQUfYaAiv0EALw_wcB; _gac_UA-137699611-5=1.1761893104.Cj0KCQjwmYzIBhC6ARIsAHA3IkS2qoxkzfDk92xVy8HUZa7P84i1P_MZyGc7BUXrbpgrWsY0m9PQUfYaAiv0EALw_wcB; _ga_ZHE4KJQ4SF=GS2.1.s1762130091$o3$g0$t1762130091$j60$l0$h0; pt_5amrs9ty=deviceId%3D81055617-3118-4250-b7bb-5a7fa58710e1%26sessionId%3D4e370063-b096-42ae-ad6e-60234d976022%26accountId%3D%26vn%3D1%26pvn%3D1%26lastActionTime%3D1762130091541%26; pt_3apoiooh=deviceId%3Dd157e982-14c4-4c9d-8788-0b78a2ba3834%26sessionId%3D0db9bd3c-e152-4ce1-85fc-40b1c584d447%26accountId%3D%26vn%3D1%26pvn%3D1%26lastActionTime%3D1762130091565%26; _ga_QMQR1WC63N=GS2.1.s1762130092$o1$g0$t1762130092$j60$l0$h0; _gcl_au=1.1.581836686.1757920330.2074130925.1762130090.1762130098; _yjsu_yjad=1762396159.b07eee59-efa2-4fbe-bd4d-40a753a42681; hasShowedStatement=true; __qca=P1-8936fdbd-7943-4aa3-8f7d-37611464dc0c; _gid=GA1.2.1277889535.1765239660; csrfToken=TrQPZf8bSxUuGhEYu3690RGc; futu-csrf=2F6AEAAYYSgR67lNNScQg54HrEQ=; _gcl_gs=2.1.k1$i1765326291$u134163986; _gcl_aw=GCL.1765326295.Cj0KCQiArt_JBhCTARIsADQZaylvhfCoL5S258pplwGMmWHSvRNn-ZiN1Pq06XWqIcmbug3ryyaBRFUaAoU_EALw_wcB; futu-offline-csrf-v2=KfxQTQPFUXF9JGAx3VAhzg%3D%3D; locale=zh-cn; locale.sig=eVtJzhiDzMABPIvfa_Sa-au5krEj-s_mhZ9m_Dq3tvg; _ga_WF9DGEYEHB=GS2.1.s1765326260$o21$g1$t1765327297$j20$l0$h1161261841; showWatch=0; _td=17710744-b72d-4bb8-b174-062fc23c72b4; ftreport-jssdk%40session={%22distinctId%22:%22ftv1VHmgN1Y3OeVz5T6EsrNItk+996+j2KNd+awpiypcRjVUOztphvu9ohC37Yzf0b4n%22%2C%22firstId%22:%22ftv1VHmgN1Y3OeVz5T6EsrNItlJI55VJJbx3Vu6421IfITZUOztphvu9ohC37Yzf0b4n%22%2C%22latestReferrer%22:%22https://www.moomoo.com/hans/stock/NVDA-US%22}; ttcsid=1765326261550::FoU5ISHu6L5yI526OWg0.28.1765329147165.0; ttcsid_D4E40SBC77UA35RT20JG=1765326261551::01mb8x03qs-XJBkpMzXz.2.1765329147166.1; ttcsid_D0QOPQRC77U7M2KJAGJG=1765326261549::930yahSa5w7r5kXI90V-.2.1765329147166.1; ttcsid_D4DUI6JC77UA35RT1N4G=1765326261551::e0pW_TUcmX15MTj3QHT1.2.1765329147166.1; _ga=GA1.2.781263147.1757920332; _ga_76MJLWJGT4=GS2.2.s1765326265$o30$g1$t1765331072$j60$l0$h0; _uetsid=f14b8e90d49411f08ce6318a59e00cfd|mx56dn|2|g1q|0|2169; _rdt_uuid=1757920331922.b88690aa-4027-4ffe-b377-044d021fb265; _uetvid=4fa4c110920311f08ce77d482e32728d|ye3q0z|1765331469753|24|1|bat.bing.com/p/insights/c/a; _ga_25WYRC4KDG=GS2.1.s1765331539$o33$g0$t1765331539$j60$l0$h0$dLNw9jYg1UdiXzDf9ASYJmJlNbw-kK9LFpA"   # <--- 替换这里
    }
    # ----------------

    url = "https://www.moomoo.com/quote-api/quote-v2/get-screener-list"

    print(f"🚀 开始采集，目标：{TOTAL_PAGES} 页，结果将保存到 {OUTPUT_FILE}")

    # 如果文件不存在，先写入表头
    if not os.path.exists(OUTPUT_FILE):
        df_header = pd.DataFrame(columns=["Stock ID", "Code", "Name", "Market Cap", "Price"])
        df_header.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    for page in range(TOTAL_PAGES):
        start_index = page * PAGE_SIZE
        print(f"\n[进度 {page+1}/{TOTAL_PAGES}] 正在请求第 {page+1} 页 (Offset: {start_index})...")

        # 1. 构造 Payload
        payload = {
            "exchanges": [],
            "plates": [],
            "values": [],
            "isWatch": False,
            "market": 2,  # 2 = 美股
            "dataFrom": start_index,
            "dataMaxCount": PAGE_SIZE,
            "extendsRetrie": True,
            "sort": {"key": "markcap", "order": "desc"},
            "accountStatus": False
        }

        # 2. 计算动态 Token
        payload_compact = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        req_obj = {
            "data": payload,
            "params": None,
            "method": "post",
            "url": "/quote-api/quote-v2/get-screener-list"
        }
        token = sss_fixed(req_obj)
        
        # 更新 Header 里的 token
        current_headers = HEADERS.copy()
        current_headers["quote-token"] = token

        try:
            # 3. 发送请求
            res = requests.post(url, headers=current_headers, data=payload_compact, timeout=10)
            
            if res.status_code == 200:
                data = res.json()
                
                # 检查业务状态
                if data.get('code') == 0:
                    stock_list = data.get('data', {}).get('list', [])
                    
                    if not stock_list:
                        print("⚠️警告：当前页没有数据，可能已到达末尾，提前结束！")
                        break

                    # 4. 提取数据
                    row_list = []
                    for stock in stock_list:
                        row_list.append({
                            "Stock ID": stock.get('stockId'),
                            "Code": stock.get('stockCode'),
                            "Name": stock.get('name'),
                            "Market Cap": stock.get('markcap'), # 顺便存一下市值
                            "Price": stock.get('price')         # 顺便存一下价格
                        })

                    # 5. 写入文件 (追加模式 mode='a')
                    df = pd.DataFrame(row_list)
                    # header=False 因为我们之前已经写过表头了
                    df.to_csv(OUTPUT_FILE, mode='a', header=False, index=False, encoding="utf-8-sig")
                    
                    print(f"✅ 成功写入 {len(row_list)} 条数据。({row_list[0]['Name']})")

                else:
                    print(f"❌ 业务报错 (Code: {data.get('code')}): {data.get('message')}")
                    # 如果遇到 Params Error 或者 登录失效，最好停止循环
                    if data.get('code') in [500, 401, 403]:
                        print("检测到严重错误，停止脚本。")
                        break
            else:
                print(f"❌ HTTP 请求失败: {res.status_code}")

        except Exception as e:
            print(f"❌ 发生异常: {e}")

        # 6. 防封睡眠 (随机 10~20 秒)
        sleep_time = random.randint(10, 20)
        print(f"💤 休息 {sleep_time} 秒...")
        time.sleep(sleep_time)

    print(f"\n🎉 任务全部完成！数据已保存在 {OUTPUT_FILE}")

if __name__ == "__main__":
    run_spider()
