import os, json, itertools, re, feedparser, requests
from bs4 import BeautifulSoup

# ---------- SETTINGS ----------
FEEDS = [
    ("USA",    "https://feeds.npr.org/1001/rss.xml"),
    ("Europe", "https://feeds.bbci.co.uk/news/world/europe/rss.xml"),
    ("USA",    "https://rss.nytimes.com/services/xml/rss/nyt/US.xml"),
    ("Europe", "https://www.theguardian.com/world/europe-news/rss"),
    ("USA",    "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml"),
    ("Europe", "https://www.euronews.com/rss?level=theme&name=news"),
]
MAX_POSTS = 1
MAX_PER_FEED = 10
KEEP_HISTORY = 1000
# ------------------------------

PAGE_ID = os.environ["FB_PAGE_ID"]
TOKEN = os.environ["FB_TOKEN"]
DB = "posted.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

history = json.load(open(DB)) if os.path.exists(DB) else []
posted = set(history)


def image_from_entry(e):
    for key in ("media_content", "media_thumbnail"):
        for m in e.get(key, []) or []:
            if m.get("url", "").startswith("http"):
                return m["url"]
    for enc in e.get("enclosures", []) or []:
        if enc.get("type", "").startswith("image") and enc.get("href"):
            return enc["href"]
    html = e.get("summary", "") or ""
    m = re.search(r'<img[^>]+src="([^"]+)"', html)
    return m.group(1) if m else None


def image_from_page(url):
    try:
        html = requests.get(url, timeout=15, headers=HEADERS).text
        soup = BeautifulSoup(html, "html.parser")
        for prop in ("og:image", "twitter:image"):
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content", "").startswith("http"):
                return tag["content"]
    except Exception as e:
        print("image error:", e)
    return None


lists = []
for region, url in FEEDS:
    try:
        entries = feedparser.parse(url, request_headers=HEADERS).entries[:MAX_PER_FEED]
        print(f"{region}: {len(entries)} entries - {url}")
        lists.append([(region, e) for e in entries])
    except Exception as e:
        print("feed error:", e)

mixed = [x for group in itertools.zip_longest(*lists) for x in group if x]

count = 0
for region, entry in mixed:
    if count >= MAX_POSTS:
        break
    link = entry.get("link", "")
    title = entry.get("title", "").strip()
    if not link or not title or link in posted:
        continue
    print(f"Trying [{region}]:", title)

    image = image_from_entry(entry) or image_from_page(link)
    caption = f"{title}\n\nRead more: {link}"

    if image:
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{PAGE_ID}/photos",
            data={"url": image, "caption": caption, "access_token": TOKEN},
        )
        if not r.ok:
            print("Photo post failed:", r.status_code, r.text)
            r = requests.post(
                f"https://graph.facebook.com/v21.0/{PAGE_ID}/feed",
                data={"message": title, "link": link, "access_token": TOKEN},
            )
    else:
        print("No image, posting link instead")
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{PAGE_ID}/feed",
            data={"message": title, "link": link, "access_token": TOKEN},
        )

    print(r.status_code, r.text)
    if r.ok:
        history.append(link)
        posted.add(link)
        count += 1

json.dump(history[-KEEP_HISTORY:], open(DB, "w"))
print("Done. Posted:", count)
