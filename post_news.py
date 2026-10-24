import os, json, itertools, feedparser, requests
from bs4 import BeautifulSoup
from googlenewsdecoder import gnewsdecoder

# ---------- SETTINGS ----------
FEEDS = [
    ("USA",    "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"),
    ("Europe", "https://news.google.com/rss/search?q=europe&hl=en-GB&gl=GB&ceid=GB:en"),
    ("USA",    "https://news.google.com/rss/search?q=united+states+breaking+news&hl=en-US&gl=US&ceid=US:en"),
    ("Europe", "https://news.google.com/rss?hl=en-GB&gl=GB&ceid=GB:en"),
    ("Europe", "https://news.google.com/rss?hl=en-IE&gl=IE&ceid=IE:en"),
]
MAX_POSTS = 1          # posts per run
MAX_PER_FEED = 10      # articles checked per feed
KEEP_HISTORY = 1000    # remembered posted links
# ------------------------------

PAGE_ID = os.environ["FB_PAGE_ID"]
TOKEN = os.environ["FB_TOKEN"]
DB = "posted.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

history = json.load(open(DB)) if os.path.exists(DB) else []
posted = set(history)


def get_image(url):
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


# Load all feeds and mix them so USA and Europe alternate
lists = []
for region, url in FEEDS:
    try:
        entries = feedparser.parse(url).entries[:MAX_PER_FEED]
        print(f"{region}: {len(entries)} entries")
        lists.append([(region, e) for e in entries])
    except Exception as e:
        print("feed error:", e)

mixed = [x for group in itertools.zip_longest(*lists) for x in group if x]

count = 0
seen_titles = set()
for region, entry in mixed:
    if count >= MAX_POSTS:
        break
    if entry.link in posted or entry.title in seen_titles:
        continue
    seen_titles.add(entry.title)
    print(f"Trying [{region}]:", entry.title)

    try:
        real = gnewsdecoder(entry.link)
        real_url = real.get("decoded_url") if real.get("status") else None
    except Exception as e:
        print("decode error:", e)
        real_url = None

    if not real_url:
        print("Could not decode link, skipping")
        continue

    image = get_image(real_url)
    caption = f"{entry.title}\n\nRead more: {real_url}"

    if image:
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{PAGE_ID}/photos",
            data={"url": image, "caption": caption, "access_token": TOKEN},
        )
        if not r.ok:
            print("Photo post failed:", r.status_code, r.text)
            print("Trying link post instead")
            r = requests.post(
                f"https://graph.facebook.com/v21.0/{PAGE_ID}/feed",
                data={"message": entry.title, "link": real_url, "access_token": TOKEN},
            )
    else:
        print("No image, posting link instead")
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{PAGE_ID}/feed",
            data={"message": entry.title, "link": real_url, "access_token": TOKEN},
        )

    print(r.status_code, r.text)
    if r.ok:
        history.append(entry.link)
        posted.add(entry.link)
        count += 1

json.dump(history[-KEEP_HISTORY:], open(DB, "w"))
print("Done. Posted:", count)
