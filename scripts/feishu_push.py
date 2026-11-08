import os
import time
import hmac
import hashlib
import base64
import requests
from datetime import datetime

WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
SIGN_SECRET = os.environ.get("FEISHU_SIGN_SECRET", "").strip()


def gen_sign(secret: str):
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    sign = base64.b64encode(hmac_code).decode("utf-8")
    return timestamp, sign


def build_card(date_str, bid_items, win_items):
    elements = []

    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"**📊 统计**\n招标 **{len(bid_items)}** 条 · 中标 **{len(win_items)}** 条"
        }
    })
    elements.append({"tag": "hr"})

    if bid_items:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**📢 招标公告（{len(bid_items)}）**"
            }
        })
        for i, item in enumerate(bid_items, 1):
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{i}. [{item['title']}]({item['url']})**\n"
                        f"来源：{item['source']} · {item['date']}"
                    )
                }
            })
        elements.append({"tag": "hr"})

    if win_items:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**🏆 中标公告（{len(win_items)}）**"
            }
        })
        for i, item in enumerate(win_items, 1):
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{i}. [{item['title']}]({item['url']})**\n"
                        f"来源：{item['source']} · {item['date']}"
                    )
                }
            })
        elements.append({"tag": "hr"})

    elements.append({
        "tag": "note",
        "elements": [{
            "tag": "plain_text",
            "content": f"推送时间：{date_str} · 关键词：信息化/弱电/网络 · 地域：南江县"
        }]
    })

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"南江县招中标日报 · {date_str}"
                },
                "template": "blue"
            },
            "elements": elements
        }
    }


def send_card(card: dict):
    if not WEBHOOK_URL:
        raise RuntimeError("没有读取到 FEISHU_WEBHOOK_URL，请检查 GitHub Secrets 配置。")

    body = dict(card)

    if SIGN_SECRET:
        timestamp, sign = gen_sign(SIGN_SECRET)
        body["timestamp"] = timestamp
        body["sign"] = sign

    resp = requests.post(WEBHOOK_URL, json=body, timeout=10)
    try:
        result = resp.json()
    except Exception:
        raise RuntimeError(f"飞书返回内容无法解析：{resp.text}")

    if result.get("code") != 0:
        raise RuntimeError(f"飞书推送失败：{result}")

    print("✅ 飞书推送成功")
    return result


def main():
    date_str = datetime.now().strftime("%Y-%m-%d")

    # =========================================================
    # 这里是数据入口。
    # 目前放的是示例数据，用来测试飞书推送链路是否成功。
    # 正式使用时，把下面两个列表替换成你抓取到的南江县招中标结果。
    # 每条数据格式必须是：
    # {"title": "公告标题", "url": "公告链接", "source": "来源网站", "date": "日期"}
    # =========================================================

    bid_items = [
        {
            "title": "【示例】南江县某单位弱电智能化系统采购项目招标公告",
            "url": "https://www.ccgp-sichuan.gov.cn/",
            "source": "四川政府采购网",
            "date": date_str
        },
        {
            "title": "【示例】南江县某学校教育信息化设备采购公开招标",
            "url": "https://search.ccgp.gov.cn/",
            "source": "中国政府采购网",
            "date": date_str
        }
    ]

    win_items = [
        {
            "title": "【示例】南江县某局网络机房升级改造项目中标结果公告",
            "url": "https://ggzyjy.sc.gov.cn/",
            "source": "四川公共资源交易平台",
            "date": date_str
        }
    ]

    if not bid_items and not win_items:
        print("今日没有需要推送的招中标信息，跳过推送。")
        return

    # 条目较多时拆成两张卡片，避免单张卡片过大。
    if len(bid_items) + len(win_items) > 15:
        if bid_items:
            send_card(build_card(date_str, bid_items, []))
        if win_items:
            send_card(build_card(date_str, [], win_items))
    else:
        send_card(build_card(date_str, bid_items, win_items))


if __name__ == "__main__":
    main()
