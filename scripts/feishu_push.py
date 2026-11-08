import os
import time
import hmac
import hashlib
import base64
import requests
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# ==================== 飞书配置 (从 Secrets 读取) ====================
WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
SIGN_SECRET = os.environ.get("FEISHU_SIGN_SECRET", "").strip()

def gen_feishu_sign(secret):
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return timestamp, base64.b64encode(hmac_code).decode("utf-8")

def send_feishu_card(card):
    if not WEBHOOK_URL:
        print("未配置 WEBHOOK_URL，跳过推送。")
        return
    body = dict(card)
    if SIGN_SECRET:
        timestamp, sign = gen_feishu_sign(SIGN_SECRET)
        body["timestamp"] = timestamp
        body["sign"] = sign
    try:
        resp = requests.post(WEBHOOK_URL, json=body, timeout=10)
        print(f"飞书推送结果：{resp.json()}")
    except Exception as e:
        print(f"飞书推送失败：{e}")

def build_feishu_card(date_str, bid_items, win_items):
    """构建飞书消息卡片"""
    elements = []
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**📊 统计**\n招标 **{len(bid_items)}** 条 · 中标 **{len(win_items)}** 条"}})
    elements.append({"tag": "hr"})
    for title, items in [("📢 招标/采购公告", bid_items), ("🏆 中标/成交公告", win_items)]:
        if items:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**{title}（{len(items)}）**"}})
            for i, item in enumerate(items, 1):
                elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**{i}. [{item['title']}]({item['url']})**\n来源：{item['source']} · {item['date']}"}})
            elements.append({"tag": "hr"})
    elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": f"推送时间：{date_str} · 地域：南江县"}]})
    return {"msg_type": "interactive", "card": {"config": {"wide_screen_mode": True}, "header": {"title": {"tag": "plain_text", "content": f"南江县招中标日报 · {date_str}"}, "template": "blue"}, "elements": elements}}

# ==================== 数据源 1: 中国政府采购网 (稳定可抓) ====================
def fetch_ccgp():
    """抓取中国政府采购网，关键词检索南江县相关公告"""
    print("开始抓取 中国政府采购网 (search.ccgp.gov.cn)...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    # 必须先访问主站建立会话，否则直接请求搜索页会返回“频繁访问”拦截页
    try:
        requests.get("http://www.ccgp.gov.cn/", headers=headers, timeout=10)
    except Exception as e:
        print(f"会话预热失败: {e}")

    keywords = ["南江县 信息化", "南江县 弱电", "南江县 网络", "南江县 智能化"]
    bid_items, win_items = [], []
    seen_urls = set()

    for kw in keywords:
        params = {
            "searchtype": "1", "page_index": "1", "bidSort": "0",
            "kw": kw, "displayZone": "四川", "timeType": "3", "dbselect": "bidx",
        }
        try:
            time.sleep(1.5)  # 严格遵守限速，请求间隔不低于1秒
            resp = requests.get("http://search.ccgp.gov.cn/bxsearch", params=params, headers=headers, timeout=15)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            # 常见的列表路径，如果失效需要根据实际HTML调整
            for li in soup.select("ul.vT-srch-result-list-bid li"):
                a_tag = li.find("a")
                if not a_tag: continue
                title = a_tag.get_text(strip=True)
                url = a_tag.get("href")
                if not url or url in seen_urls: continue
                seen_urls.add(url)

                # 提取日期
                date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", li.get_text())
                item_date = date_match.group(1).replace(".", "-") if date_match else datetime.now().strftime("%Y-%m-%d")

                item = {"title": title, "url": url, "source": "中国政府采购网", "date": item_date}
                if "中标" in title or "成交" in title:
                    win_items.append(item)
                else:
                    bid_items.append(item)
        except Exception as e:
            print(f"CCGP 关键词 [{kw}] 抓取失败: {e}")
            continue
    return bid_items, win_items

# ==================== 数据源 2: 四川省公共资源交易平台 (接口可用) ====================
def fetch_sc_ggzy():
    """
    抓取四川省公共资源交易平台 (ggzyjy.sc.gov.cn)。
    此站有公开的 JSON 列表接口，稳定性高于 HTML 解析。
    参考旧版接口：http://www.scggzy.gov.cn/Info/GetInfoListNew [reference:2]
    """
    print("开始抓取 四川省公共资源交易平台 (ggzyjy.sc.gov.cn)...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "http://ggzyjy.sc.gov.cn/",
    }
    
    # 注意：此类接口的域名和参数可能随网站改版而变化，如果失效，需要打开浏览器 F12 抓包更新。
    api_url = "http://www.scggzy.gov.cn/Info/GetInfoListNew"
    params = {
        "keywords": "南江县",   # 直接用关键词检索
        "page": "1",
        # 其他参数保持最小化，或根据网站实际需要添加
    }
    
    bid_items, win_items = [], []
    try:
        resp = requests.get(api_url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        # 假设返回的 JSON 结构中包含一个列表字段，这里用 'data' 或 'list' 作为占位
        # 实际字段名需要在浏览器 F12 -> Network 中查看该接口的响应来确定
        raw_list = data.get("data") or data.get("list") or []
        
        for item in raw_list:
            title = item.get("title", "") or item.get("name", "")
            if "南江县" not in title:
                continue
            
            url = item.get("url", "") or item.get("link", "")
            item_date = item.get("publishDate", "") or item.get("date", "")
            # 如果日期是时间戳，可能需要转换
            if isinstance(item_date, (int, float)):
                item_date = datetime.fromtimestamp(item_date / 1000).strftime("%Y-%m-%d")
            elif not item_date:
                item_date = datetime.now().strftime("%Y-%m-%d")

            record = {"title": title, "url": url, "source": "四川公共资源交易平台", "date": item_date}
            if "中标" in title or "成交" in title:
                win_items.append(record)
            else:
                bid_items.append(record)
    except Exception as e:
        print(f"四川公共资源交易平台抓取失败: {e}")
    
    return bid_items, win_items

# ==================== 主入口 ====================
def main():
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"[{datetime.now()}] 开始执行多源抓取任务...")

    all_bid_items, all_win_items = [], []

    # 依次调用各个数据源
    try:
        b, w = fetch_ccgp()
        all_bid_items.extend(b)
        all_win_items.extend(w)
    except Exception as e:
        print(f"数据源 CCGP 执行异常: {e}")

    try:
        b, w = fetch_sc_ggzy()
        all_bid_items.extend(b)
        all_win_items.extend(w)
    except Exception as e:
        print(f"数据源 SC_GGZY 执行异常: {e}")

    # 根据 URL 去重
    def dedup(items):
        seen = set()
        result = []
        for it in items:
            if it["url"] not in seen:
                seen.add(it["url"])
                result.append(it)
        return result

    all_bid_items = dedup(all_bid_items)
    all_win_items = dedup(all_win_items)

    print(f"抓取完成：招标 {len(all_bid_items)} 条，中标 {len(all_win_items)} 条。")

    if all_bid_items or all_win_items:
        send_feishu_card(build_feishu_card(date_str, all_bid_items, all_win_items))
    else:
        print("今日没有抓取到符合条件的数据。")

if __name__ == "__main__":
    main()
