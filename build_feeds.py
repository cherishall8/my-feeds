#!/usr/bin/env python3
"""把沒有 RSS 的網站列表頁，轉成 RSS 檔（輸出到 docs/ 資料夾）。"""
import re
import sys
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup

TW = timezone(timedelta(hours=8))
OUT_DIR = Path("docs")
HEADERS = {"User-Agent": "Mozilla/5.0 (personal RSS builder; twice a week)"}


def roc_to_datetime(text):
    m = re.search(r"(\d{2,3})[-./](\d{1,2})[-./](\d{1,2})", text)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return datetime(y + 1911, mo, d, tzinfo=TW)
    except ValueError:
        return None


def ad_to_datetime(text):
    m = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", text or "")
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return datetime(y, mo, d, tzinfo=TW)
    except ValueError:
        return None


def parse_taipei_table(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for tr in soup.select("table tr"):
        a = tr.find("a", href=True)
        if not a:
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        date = None
        for td in tr.find_all("td"):
            date = roc_to_datetime(td.get_text(strip=True))
            if date:
                break
        items.append(
            {"title": title, "link": urljoin(base_url, a["href"]), "date": date}
        )
    return items


def parse_hpa_workplace(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"news_in\.aspx\?Id=(\d+)", a["href"], re.I)
        if not m or m.group(1) in seen:
            continue
        title = (a.get("title") or a.get_text(strip=True) or "").strip()
        title = re.sub(r"^連結\s*", "", title)
        if not title:
            continue
        date_text = a.find_previous(
            string=re.compile(r"20\d{2}[/-]\d{1,2}[/-]\d{1,2}")
        )
        seen.add(m.group(1))
        items.append(
            {
                "title": title,
                "link": urljoin(base_url, a["href"]),
                "date": ad_to_datetime(date_text),
            }
        )
    return items


SOURCES = [
    {
        "slug": "taipei-mental-health-news",
        "title": "臺北市社區心理衛生中心－最新消息",
        "url": (
            "https://mental-health.gov.taipei/News.aspx"
            "?n=FAB9374F6BCE2D48&sms=EEA94C26A90DD864&page=1&PageSize=20"
        ),
        "parser": parse_taipei_table,
    },
    {
        "slug": "hpa-workplace-news",
        "title": "國健署健康職場資訊網－最新消息與活動快訊",
        "url": "https://health.hpa.gov.tw/hpa/info/index.aspx",
        "parser": parse_hpa_workplace,
    },
]


def build_rss(source, items):
    now = format_datetime(datetime.now(TW))
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel>',
        f"<title>{escape(source['title'])}</title>",
        f"<link>{escape(source['url'])}</link>",
        f"<description>{escape(source['title'])}（自動產生）</description>",
        "<language>zh-TW</language>",
        f"<lastBuildDate>{now}</lastBuildDate>",
    ]
    for it in items:
        parts.append("<item>")
        parts.append(f"<title>{escape(it['title'])}</title>")
        parts.append(f"<link>{escape(it['link'])}</link>")
        parts.append(f'<guid isPermaLink="true">{escape(it["link"])}</guid>')
        if it["date"]:
            parts.append(f"<pubDate>{format_datetime(it['date'])}</pubDate>")
        parts.append("</item>")
    parts.append("</channel></rss>")
    return "\n".join(parts)


def main():
    OUT_DIR.mkdir(exist_ok=True)
    failed = False
    for src in SOURCES:
        try:
            resp = requests.get(src["url"], headers=HEADERS, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            items = src["parser"](resp.text, src["url"])
        except Exception as e:
            print(f"[錯誤] {src['slug']}: {e}", file=sys.stderr)
            failed = True
            continue
        if not items:
            print(f"[錯誤] {src['slug']}: 抓到 0 筆，網站可能改版", file=sys.stderr)
            failed = True
            continue
        (OUT_DIR / f"{src['slug']}.xml").write_text(
            build_rss(src, items), encoding="utf-8"
        )
        print(f"[完成] {src['slug']}: {len(items)} 筆")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
