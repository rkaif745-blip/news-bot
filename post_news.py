import os, json, feedparser, requests
from bs4 import BeautifulSoup
from googlenewsdecoder import gnewsdecoder

RSS = "https://news.google.com/rss/search?q=pakistan&hl=en-PK&gl=PK&ceid=PK:en"
PAGE_ID = os.environ["FB_PAGE_ID"]
TOKEN = os.environ["FB_TOKEN"]
DB = "posted.json"

posted = set(json.load(open(DB))) if os.path.exists(DB) else set()

def get_image(url):
    try:
        html = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}).text
        tag = BeautifulSoup(html, "html.parser").find("meta", property="og:image")
        return tag["content"] if tag else None
    except Exception:
        return None

for entry in feedparser.parse(RSS).entries[:5]:
    if entry.link in posted:
        continue
    real = gnewsdecoder(entry.link)
    real_url = real.get("decoded_url") if real.get("status") else None
    if not real_url:
        continue
    image = get_image(real_url)
    if not image:
        continue
    r = requests.post(
        f"https://graph.facebook.com/v21.0/{PAGE_ID}/photos",
        data={"url": image, "caption": f"{entry.title}\n\nRead more: {real_url}", "access_token": TOKEN},
    )
    print(r.status_code, r.text)
    if r.ok:
        posted.add(entry.link)

json.dump(list(posted), open(DB, "w"))
