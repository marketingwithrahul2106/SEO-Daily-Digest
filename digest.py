"""
DM Daily Digest — All 6 Modules (Gemini Version)
Powered by Google AI Studio — 100% Free, No Credit Card
Sends a morning email every day at 8 AM IST with:
  1. Industry news (SEO, AI Search, Digital Marketing)
  2. Case studies & new techniques
  3. LinkedIn activity summary
  4. Instagram activity summary
  5. Competitor & keyword watch
  6. Content ideas for today
  + Free tier usage monitor with cost alerts
"""

import os
import json
import smtplib
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ─────────────────────────────────────────────
# CONFIG — all values read from GitHub Secrets
# ─────────────────────────────────────────────
GEMINI_API_KEY      = os.environ.get("GEMINI_API_KEY", "")
GMAIL_ADDRESS       = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD  = os.environ.get("GMAIL_APP_PASSWORD", "")
RECIPIENT_EMAIL     = os.environ.get("RECIPIENT_EMAIL", GMAIL_ADDRESS)
LINKEDIN_TOKEN      = os.environ.get("LINKEDIN_TOKEN", "")       # optional
INSTAGRAM_TOKEN     = os.environ.get("INSTAGRAM_TOKEN", "")      # optional
INSTAGRAM_USER_ID   = os.environ.get("INSTAGRAM_USER_ID", "")    # optional

# Gemini model to use — gemini-2.0-flash is fast, free, and high quality
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL   = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# ─────────────────────────────────────────────
# FREE TIER LIMITS — Google AI Studio
# Gemini 2.0 Flash: 1,500 requests/day FREE
# Our digest uses ~10 requests/day — well within limits
# ─────────────────────────────────────────────
DAILY_REQUEST_LIMIT   = 1500   # Google's free limit
DAILY_REQUEST_BUDGET  = 50     # Our self-imposed safe limit (warning threshold)
USAGE_FILE = "gemini_usage.json"

# ─────────────────────────────────────────────
# USAGE TRACKER
# ─────────────────────────────────────────────
total_requests_this_run = 0

def load_usage():
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE) as f:
            return json.load(f)
    return {"daily_requests": 0, "monthly_requests": 0,
            "last_reset_day": "", "last_reset_month": ""}

def save_usage(data):
    with open(USAGE_FILE, "w") as f:
        json.dump(data, f)

def update_usage(requests_used):
    data  = load_usage()
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    if data.get("last_reset_day") != today:
        data["daily_requests"]  = 0
        data["last_reset_day"]  = today
    if data.get("last_reset_month") != month:
        data["monthly_requests"]  = 0
        data["last_reset_month"]  = month
    data["daily_requests"]   += requests_used
    data["monthly_requests"] += requests_used
    save_usage(data)
    return data

def check_cost_alerts(usage):
    """
    Google AI Studio free tier is rate-limited — NOT credit-based.
    When you hit the limit, requests simply fail (HTTP 429).
    There is NO charge at all. This monitor is just for awareness.
    """
    alerts = []
    daily_pct = (usage["daily_requests"] / DAILY_REQUEST_BUDGET) * 100

    if daily_pct >= 90:
        alerts.append({
            "level": "WARNING",
            "message": (
                f"You have made {usage['daily_requests']} API requests today "
                f"(our safe budget: {DAILY_REQUEST_BUDGET}). "
                f"Note: Google's actual free limit is 1,500/day — so you are "
                f"still completely safe. No charges are possible on Google AI Studio free tier."
            )
        })
    return alerts

# ─────────────────────────────────────────────
# GEMINI API CALLER
# ─────────────────────────────────────────────
def ask_gemini(prompt, max_tokens=900):
    global total_requests_this_run
    if not GEMINI_API_KEY:
        return "[GEMINI_API_KEY missing — add it to GitHub Secrets]"

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.7
        }
    }).encode()

    url = f"{GEMINI_URL}?key={GEMINI_API_KEY}"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            total_requests_this_run += 1
            # Extract text from Gemini response structure
            candidates = data.get("candidates", [])
            if not candidates:
                return "[No response from Gemini]"
            parts = candidates[0].get("content", {}).get("parts", [])
            text  = " ".join(p.get("text", "") for p in parts).strip()
            return text or "[Empty response]"
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 429:
            return "[Gemini rate limit hit — will retry tomorrow. Still 100% free, no charges.]"
        return f"[Gemini API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Error calling Gemini: {e}]"

# ─────────────────────────────────────────────
# RSS FEED READER
# ─────────────────────────────────────────────
DM_FEEDS = [
    "https://feeds.feedburner.com/NeilPatel",
    "https://ahrefs.com/blog/feed/",
    "https://www.searchenginejournal.com/feed/",
    "https://backlinko.com/feed",
    "https://moz.com/blog/feed",
    "https://www.searchenginewatch.com/feed/",
]

GOOGLE_ALERT_FEEDS = [
    # Add your Google Alerts RSS URLs here
    # Go to google.com/alerts → create an alert → choose RSS feed
    # Paste the URL here like: "https://www.google.com/alerts/feeds/XXXXX/XXXXX"
]

def fetch_rss(url, max_items=3):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            tree = ET.parse(resp)
            root = tree.getroot()
            ns   = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall(".//item") or root.findall(".//atom:entry", ns)
            items = []
            for entry in entries[:max_items]:
                title_el = entry.find("title") or entry.find("atom:title", ns)
                link_el  = entry.find("link")  or entry.find("atom:link", ns)
                title = title_el.text.strip() if title_el is not None and title_el.text else "No title"
                link  = (link_el.text or link_el.get("href", "#")) if link_el is not None else "#"
                items.append({"title": title, "link": link})
            return items
    except Exception:
        return []

# ─────────────────────────────────────────────
# MODULE 1 — INDUSTRY NEWS
# ─────────────────────────────────────────────
def get_industry_news():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%B %d, %Y")
    return ask_gemini(
        f"You are a digital marketing analyst. Search your knowledge and provide the most important "
        f"digital marketing, SEO, and AI Search updates from around {yesterday}. "
        f"Cover: Google algorithm updates, AI Overviews changes, ChatGPT/Perplexity Search news, "
        f"social media algorithm changes, paid search updates, and content marketing trends. "
        f"Return exactly 6 updates. For each write: "
        f"**Headline** (bold), one clear sentence summary, and the source name. "
        f"Rank by importance to a digital marketer working in SEO and AI search. "
        f"Be specific and practical — no generic advice.",
        max_tokens=1000
    )

# ─────────────────────────────────────────────
# MODULE 2 — CASE STUDIES & TECHNIQUES
# ─────────────────────────────────────────────
def get_case_studies():
    all_items = []
    for feed_url in DM_FEEDS:
        items = fetch_rss(feed_url, max_items=2)
        all_items.extend(items)

    if not all_items:
        # Fallback: ask Gemini directly
        return ask_gemini(
            "List 4 highly practical digital marketing techniques or case studies that are working "
            "right now in 2025-2026. Focus on SEO, AI Search optimisation, content strategy, and "
            "social media growth. For each: technique name, what it involves, and the key result "
            "a marketer can expect. Be specific with numbers where possible.",
            max_tokens=800
        )

    headlines = "\n".join(
        f'- "{item["title"]}" — {item["link"]}'
        for item in all_items[:8]
    )
    return ask_gemini(
        f"Here are recent digital marketing articles from top industry blogs:\n{headlines}\n\n"
        f"Pick the 4 most insightful ones. For each write:\n"
        f"- Article title\n"
        f"- 2 bullet points: the key insight and one action a digital marketer should take today\n"
        f"Be concise, practical, and specific. No fluff.",
        max_tokens=800
    )

# ─────────────────────────────────────────────
# MODULE 3 — LINKEDIN ACTIVITY
# ─────────────────────────────────────────────
def get_linkedin_summary():
    if not LINKEDIN_TOKEN:
        return (
            "<div style='background:#fff8e1;border-left:3px solid #f9a825;"
            "padding:10px 14px;border-radius:0 6px 6px 0;font-size:13px;color:#5d4037;'>"
            "<b>LinkedIn not connected yet.</b> To enable this module, add your "
            "<code>LINKEDIN_TOKEN</code> to GitHub Secrets. "
            "<a href='https://www.linkedin.com/developers/' style='color:#1565c0;'>Get token here</a>"
            "</div>"
        )
    try:
        url = ("https://api.linkedin.com/v2/ugcPosts"
               "?q=authors&authors=List(urn%3Ali%3Aperson%3Ame)&count=5")
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {LINKEDIN_TOKEN}",
            "X-Restli-Protocol-Version": "2.0.0"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data  = json.loads(resp.read())
        posts = data.get("elements", [])
        if not posts:
            return "No LinkedIn posts found from yesterday."
        summary_input = f"My recent LinkedIn posts data:\n{json.dumps(posts[:3], indent=2)[:1500]}\n\n"
        return ask_gemini(
            summary_input +
            "Summarise my LinkedIn activity in 3 bullet points:\n"
            "1. Which post performed best and why\n"
            "2. Estimated total reach and engagement\n"
            "3. One specific tip to improve tomorrow's post based on what worked",
            max_tokens=400
        )
    except Exception as e:
        return (f"<div style='color:#c62828;font-size:13px;'>"
                f"LinkedIn error: {e}. Check your token in GitHub Secrets.</div>")

# ─────────────────────────────────────────────
# MODULE 4 — INSTAGRAM ACTIVITY
# ─────────────────────────────────────────────
def get_instagram_summary():
    if not INSTAGRAM_TOKEN or not INSTAGRAM_USER_ID:
        return (
            "<div style='background:#fff8e1;border-left:3px solid #f9a825;"
            "padding:10px 14px;border-radius:0 6px 6px 0;font-size:13px;color:#5d4037;'>"
            "<b>Instagram not connected yet.</b> Add <code>INSTAGRAM_TOKEN</code> and "
            "<code>INSTAGRAM_USER_ID</code> to GitHub Secrets. "
            "Requires an Instagram Business or Creator account. "
            "<a href='https://developers.facebook.com/docs/instagram-api' style='color:#1565c0;'>"
            "Setup guide</a></div>"
        )
    try:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        url = (
            f"https://graph.instagram.com/{INSTAGRAM_USER_ID}/media"
            f"?fields=id,caption,like_count,comments_count,timestamp,media_type"
            f"&access_token={INSTAGRAM_TOKEN}"
        )
        with urllib.request.urlopen(url, timeout=15) as resp:
            data  = json.loads(resp.read())
        posts = [p for p in data.get("data", []) if yesterday in p.get("timestamp","")]
        if not posts:
            return f"No Instagram posts found from {yesterday}."
        summary_input = f"My Instagram posts from {yesterday}:\n{json.dumps(posts, indent=2)[:1000]}\n\n"
        return ask_gemini(
            summary_input +
            "Give a 3-bullet performance summary:\n"
            "1. Best performing post and why it worked\n"
            "2. Total likes and comments combined\n"
            "3. One specific tip to improve engagement on tomorrow's post",
            max_tokens=400
        )
    except Exception as e:
        return (f"<div style='color:#c62828;font-size:13px;'>"
                f"Instagram error: {e}. Check your token.</div>")

# ─────────────────────────────────────────────
# MODULE 5 — COMPETITOR & KEYWORD WATCH
# ─────────────────────────────────────────────
def get_competitor_watch():
    alert_items = []
    for feed_url in GOOGLE_ALERT_FEEDS:
        alert_items.extend(fetch_rss(feed_url, max_items=3))

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%B %d, %Y")

    if alert_items:
        headlines = "\n".join(f'- {i["title"]}' for i in alert_items[:6])
        prompt = (
            f"My competitor monitoring alerts from {yesterday}:\n{headlines}\n\n"
            f"Summarise the 3 most important competitive moves I should know about "
            f"as a digital marketer. For each: what happened and what I should do in response."
        )
    else:
        prompt = (
            f"As a digital marketing intelligence analyst, report on any significant moves "
            f"from around {yesterday} by major players: SEO tool companies (Semrush, Ahrefs, Moz), "
            f"marketing platforms (HubSpot, Meta Ads, Google Ads), and search engines. "
            f"Also report if any major Google Search ranking fluctuations were detected. "
            f"Give 3 specific bullet points a digital marketer in SEO and AI search should act on."
        )
    return ask_gemini(prompt, max_tokens=500)

# ─────────────────────────────────────────────
# MODULE 6 — CONTENT IDEAS
# ─────────────────────────────────────────────
def get_content_ideas():
    today = datetime.now().strftime("%B %d, %Y")
    return ask_gemini(
        f"You are a content strategist for a digital marketer specialising in SEO and AI Search. "
        f"Today is {today}. Based on current trends in digital marketing:\n\n"
        f"Generate 5 content ideas I can post TODAY:\n"
        f"- 3 LinkedIn post ideas (professional, data-driven, insight-based — good for comments)\n"
        f"- 2 Instagram post ideas (visual, punchy hook, good for saves and shares)\n\n"
        f"For each idea give:\n"
        f"1. Post topic/title\n"
        f"2. Opening hook line (first sentence that stops the scroll)\n"
        f"3. Content angle in one sentence\n\n"
        f"Make them timely, specific, and tied to real trends — not generic.",
        max_tokens=800
    )

# ─────────────────────────────────────────────
# EMAIL BUILDER
# ─────────────────────────────────────────────
def build_email(modules, cost_alerts, usage):
    today_str    = datetime.now().strftime("%A, %B %d, %Y")
    daily_pct    = min((usage["daily_requests"] / DAILY_REQUEST_BUDGET) * 100, 100)
    actual_pct   = min((usage["daily_requests"] / DAILY_REQUEST_LIMIT)  * 100, 100)

    def bar(pct, color):
        filled = int(pct / 5)
        empty  = 20 - filled
        return (
            f'<span style="font-family:monospace;letter-spacing:1px;">'
            f'<span style="color:{color};">{"█" * filled}</span>'
            f'<span style="color:#ddd;">{"░" * empty}</span>'
            f'</span> {pct:.0f}%'
        )

    # Cost alert block
    if cost_alerts:
        alert = cost_alerts[0]
        alert_html = f"""
        <div style="background:#fff3cd;border-left:4px solid #f0ad4e;
                    padding:14px 18px;border-radius:0 8px 8px 0;margin-bottom:24px;">
          <p style="margin:0 0 6px;font-size:15px;font-weight:700;color:#856404;">
            ⚠️ USAGE MONITOR ALERT</p>
          <p style="margin:0;font-size:13px;color:#856404;">{alert["message"]}</p>
        </div>"""
    else:
        alert_html = ""

    def section(number, emoji, title, content, color):
        safe_content = content.replace("\n", "<br>").replace("**", "<b>", 1)
        # Simple bold replacement for markdown **text**
        import re
        safe_content = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', content.replace("\n", "<br>"))
        return f"""
        <div style="margin-bottom:28px;">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;
                      border-bottom:2px solid {color};padding-bottom:8px;">
            <span style="background:{color};color:#fff;border-radius:50%;width:26px;height:26px;
                         display:inline-flex;align-items:center;justify-content:center;
                         font-size:12px;font-weight:700;flex-shrink:0;">{number}</span>
            <h2 style="margin:0;font-size:17px;font-weight:700;color:#1a1a2e;">
              {emoji} {title}</h2>
          </div>
          <div style="font-size:14px;line-height:1.8;color:#333;">{safe_content}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f0f4f8;
             font-family:'Helvetica Neue',Arial,sans-serif;">
  <div style="max-width:640px;margin:24px auto;background:#ffffff;
              border-radius:16px;overflow:hidden;
              box-shadow:0 4px 20px rgba(0,0,0,0.08);">

    <!-- HEADER -->
    <div style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 60%,#0f3460 100%);
                padding:28px 32px 24px;">
      <p style="margin:0 0 4px;font-size:12px;color:#8899bb;letter-spacing:2px;
                text-transform:uppercase;">Digital Marketing Intelligence</p>
      <h1 style="margin:0;font-size:24px;font-weight:800;color:#ffffff;">
        Your Daily DM Digest</h1>
      <p style="margin:6px 0 0;font-size:13px;color:#8899bb;">{today_str}</p>
      <p style="margin:6px 0 0;font-size:11px;color:#6677aa;">
        Powered by Google Gemini — 100% Free</p>
    </div>

    <div style="padding:28px 32px;">

      {alert_html}

      {section(1,"📰","Industry News — SEO &amp; AI Search",
               modules.get("news",""),"#0f3460")}
      {section(2,"📚","New Case Studies &amp; Techniques",
               modules.get("case_studies",""),"#e94560")}
      {section(3,"💼","LinkedIn — Yesterday's Performance",
               modules.get("linkedin",""),"#0077b5")}
      {section(4,"📸","Instagram — Yesterday's Performance",
               modules.get("instagram",""),"#c13584")}
      {section(5,"🔍","Competitor &amp; Keyword Watch",
               modules.get("competitors",""),"#f5a623")}
      {section(6,"✍️","Today's Content Ideas",
               modules.get("ideas",""),"#27ae60")}

      <!-- FREE TIER MONITOR -->
      <div style="background:#f8f9fc;border-radius:10px;
                  padding:16px 20px;margin-top:8px;">
        <p style="margin:0 0 10px;font-size:12px;font-weight:700;color:#555;
                  text-transform:uppercase;letter-spacing:1px;">
          🛡️ Google AI Studio — Free Tier Monitor</p>
        <table style="width:100%;font-size:12px;color:#444;">
          <tr>
            <td style="padding:3px 0;width:140px;">Today's requests</td>
            <td>{bar(daily_pct, "#27ae60")}</td>
            <td style="text-align:right;color:#888;">
              {usage["daily_requests"]} / {DAILY_REQUEST_BUDGET} (safe budget)</td>
          </tr>
          <tr>
            <td style="padding:3px 0;">Google's free limit</td>
            <td>{bar(actual_pct, "#0f3460")}</td>
            <td style="text-align:right;color:#888;">
              {usage["daily_requests"]} / {DAILY_REQUEST_LIMIT}</td>
          </tr>
        </table>
        <p style="margin:10px 0 0;font-size:11px;color:#999;">
          ✅ Google AI Studio free tier: <b>1,500 requests/day — completely free, no card, no charges ever.</b><br>
          When limit is hit: requests simply fail (HTTP 429) — you are NEVER charged.<br>
          Monitor at
          <a href="https://aistudio.google.com" style="color:#0f3460;">aistudio.google.com</a>
        </p>
      </div>

    </div>

    <!-- FOOTER -->
    <div style="background:#f8f9fc;padding:16px 32px;border-top:1px solid #eee;
                text-align:center;font-size:11px;color:#aaa;">
      Automated by GitHub Actions · Powered by Google Gemini (Free Tier) · Runs daily at 8 AM IST<br>
      To pause: GitHub repo → Actions → Disable workflow
    </div>

  </div>
</body>
</html>"""
    return html

# ─────────────────────────────────────────────
# SEND EMAIL
# ─────────────────────────────────────────────
def send_email(html_content):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("Email credentials missing — printing preview instead.")
        print(html_content[:300])
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 DM Digest — {datetime.now().strftime('%b %d, %Y')}"
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())
    print(f"✅ Email sent successfully to {RECIPIENT_EMAIL}")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print("🚀 DM Daily Digest starting (Gemini Edition)...")
    print(f"   Model : {GEMINI_MODEL}")
    print(f"   Date  : {datetime.now().strftime('%Y-%m-%d %H:%M IST')}")
    print()

    modules = {}

    print("  [1/6] Fetching industry news...")
    modules["news"] = get_industry_news()
    print(f"        Done — {len(modules['news'])} chars")

    print("  [2/6] Fetching case studies & techniques...")
    modules["case_studies"] = get_case_studies()
    print(f"        Done — {len(modules['case_studies'])} chars")

    print("  [3/6] Fetching LinkedIn activity...")
    modules["linkedin"] = get_linkedin_summary()
    print(f"        Done")

    print("  [4/6] Fetching Instagram activity...")
    modules["instagram"] = get_instagram_summary()
    print(f"        Done")

    print("  [5/6] Fetching competitor & keyword watch...")
    modules["competitors"] = get_competitor_watch()
    print(f"        Done — {len(modules['competitors'])} chars")

    print("  [6/6] Generating today's content ideas...")
    modules["ideas"] = get_content_ideas()
    print(f"        Done — {len(modules['ideas'])} chars")

    # Update usage
    usage       = update_usage(total_requests_this_run)
    cost_alerts = check_cost_alerts(usage)

    print()
    print(f"  📊 Gemini requests this run : {total_requests_this_run}")
    print(f"  📊 Daily requests so far    : {usage['daily_requests']} / {DAILY_REQUEST_LIMIT} (Google limit)")
    print(f"  📊 Monthly requests         : {usage['monthly_requests']}")
    print(f"  ✅ Charges possible          : NEVER (Google AI Studio free tier)")

    if cost_alerts:
        print(f"  ⚠️  Usage note: {cost_alerts[0]['message']}")

    print()
    print("  📧 Building email...")
    html = build_email(modules, cost_alerts, usage)

    print("  📧 Sending email...")
    send_email(html)

    print()
    print("✅ All done! Check your inbox.")

if __name__ == "__main__":
    main()
