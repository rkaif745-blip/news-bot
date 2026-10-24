import os, json, itertools, re, base64, feedparser, requests
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
USE_AI_TITLE = True
USE_AI_IMAGE = True
TEXT_MODEL = "gemini-2.5-flash"
IMAGE_MODEL = "gemini-2.5-flash-image"   # change here if Google renames it
# ------------------------------

PAGE_ID = os.environ["FB_PAGE_ID"]
TOKEN = os.environ["FB_TOKEN"]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
DB = "posted.json"
API = "https://generativelanguage.googleapis.com/v1beta/models"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

history = json.load(open(DB)) if os.path.exists(DB) else []
posted = set(history)


def gemini(model, payload):
    if not GEMINI_KEY:
        return None
    try:
        r = requests.post(
            f"{API}/{model}:generateContent",
            headers={"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"},
            json=payload, timeout=90,
        )
        if not r.ok:
            print("Gemini error:", model, r.status_code, r.text[:300])
            return None
        return r.json()
    except Exception as e:
        print("Gemini exception:", e)
        return None


def ai_title_and_prompt(title, summary):
    prompt = (
        "You are a news editor. Given this news item, return JSON with two keys:\n"
        '"title": a clear, accurate, neutral headline under 100 characters (no clickbait, no added facts),\n'
        '"image_prompt": a prompt for an editorial illustration of this story. '
        "Style: modern flat vector news illustration. No text, no letters, no logos, "
        "no real people or recognizable faces, no flags of real persons.\n\n"
        f"Headline: {title}\nSummary: {summary}"
    )
    data = gemini(TEXT_MODEL, {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    })
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        out = json.loads(text)
        return out.get("title") or title, out.get("image_prompt")
    except Exception:
        return title, None


def ai_image(image_prompt):
    data = gemini(IMAGE_MODEL, {
        "contents": [{"parts": [{"text": image_prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    })
    try:
        for part in data["candidates"][0]["content"]["parts"]:
            blob = part.get("inlineData") or part.get("inline_data")
            if blob and blob.get("data"):
                return base64.b64decode(blob["data"])
    except Exception:
        pass
    return None


def image_from_entry(e):
    for key in ("media_content", "media_thumbnail"):
        for m in e.get(key, []) or []:
            if m.get("url", "").startswith("http"):
                return m["url"]
    for enc in e.get("enclosures", []) or []:
        if enc.get("type", "").startswith("image") and enc.get("href"):
            return enc["href"]
    m = re.search(r'<img[^>]+src="([^"]+)"', e.get("summary", "") or "")
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
        print(f"{region}: {len(entries)} entries")
        lists.append([(region, e) for e in entries])
    except Exception as e:
        print("feed error:", e)

mixed = [x for group in itertools.zip_longest(*lists) for x in group if x]

count = 0
for region, entry in mixed:
    if count >= MAX_POSTS:
        break
    link = entry.get("link", "")
    orig_title = entry.get("title", "").strip()
    if not link or not orig_title or link in posted:
        continue
    print(f"Trying [{region}]:", orig_title)

    summary = BeautifulSoup(entry.get("summary", "") or "", "html.parser").get_text()[:500]

    title, img_prompt = orig_title, None
    if USE_AI_TITLE or USE_AI_IMAGE:
        title, img_prompt = ai_title_and_prompt(orig_title, summary)
        if not USE_AI_TITLE:
            title = orig_title
    print("Title:", title)

    img_bytes = ai_image(img_prompt) if (USE_AI_IMAGE and img_prompt) else None
    print("AI image:", "yes" if img_bytes else "no (using original image)")

    if img_bytes:
        caption = f"{title}\n\nRead more: {link}\n\nImage: AI-generated illustration"
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{PAGE_ID}/photos",
            data={"caption": caption, "access_token": TOKEN},
            files={"source": ("news.png", img_bytes, "image/png")},
        )
    else:
        image = image_from_entry(entry) or image_from_page(link)
        caption = f"{title}\n\nRead more: {link}"
        if image:
            r = requests.post(
                f"https://graph.facebook.com/v21.0/{PAGE_ID}/photos",
                data={"url": image, "caption": caption, "access_token": TOKEN},
            )
        else:
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
