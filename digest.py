"""
DM Daily Digest — All 6 Modules
Sends a morning email every day at 8 AM with:
  1. Industry news (SEO, AI Search, Digital Marketing)
  2. Case studies & new techniques
  3. LinkedIn activity summary
  4. Instagram activity summary
  5. Competitor & keyword watch
  6. Content ideas for today
  + Cost protection alert if API usage is near free limit
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
# CONFIG — reads from GitHub Secrets
# ─────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
GMAIL_ADDRESS       = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD  = os.environ.get("GMAIL_APP_PASSWORD", "")
RECIPIENT_EMAIL     = os.environ.get("RECIPIENT_EMAIL", GMAIL_ADDRESS)
LINKEDIN_TOKEN      = os.environ.get("LINKEDIN_TOKEN", "")       # optional
INSTAGRAM_TOKEN     = os.environ.get("INSTAGRAM_TOKEN", "")      # optional
INSTAGRAM_USER_ID   = os.environ.get("INSTAGRAM_USER_ID", "")    # optional
GSC_JSON_KEY        = os.environ.get("GSC_JSON_KEY", "")         # optional

# Cost protection thresholds (Anthropic free tier = $5 credit)
DAILY_TOKEN_BUDGET   = 80_000   # tokens per day — warn if exceeded
MONTHLY_TOKEN_BUDGET = 1_500_000 # tokens per month — hard warn

# ─────────────────────────────────────────────
# USAGE TRACKER (stored in a local file per run)
# ─────────────────────────────────────────────
USAGE_FILE = "token_usage.json"

def load_usage():
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE) as f:
            return json.load(f)
    return {"daily": 0, "monthly": 0, "last_reset_day": "", "last_reset_month": ""}

def save_usage(data):
    with open(USAGE_FILE, "w") as f:
        json.dump(data, f)

def update_usage(tokens_used):
    data = load_usage()
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    if data.get("last_reset_day") != today:
        data["daily"] = 0
        data["last_reset_day"] = today
    if data.get("last_reset_month") != month:
        data["monthly"] = 0
        data["last_reset_month"] = month
    data["daily"]   += tokens_used
    data["monthly"] += tokens_used
    save_usage(data)
    return data

def check_cost_alerts(usage):
    alerts = []
    daily_pct   = (usage["daily"]   / DAILY_TOKEN_BUDGET)   * 100
    monthly_pct = (usage["monthly"] / MONTHLY_TOKEN_BUDGET) * 100

    if daily_pct >= 90:
        alerts.append({
            "level": "DANGER",
            "message": f"You have used {daily_pct:.0f}% of today's token budget. "
                       f"If this keeps up, paid charges may start. "
                       f"Consider pausing the digest or reducing modules."
        })
    elif daily_pct >= 70:
        alerts.append({
            "level": "WARNING",
            "message": f"You have used {daily_pct:.0f}% of today's token budget. "
                       f"Still within the free limit, but worth watching."
        })

    if monthly_pct >= 80:
        alerts.append({
            "level": "DANGER",
            "message": f"Monthly token usage is at {monthly_pct:.0f}% of the free limit. "
                       f"You may hit paid territory before the month ends. "
                       f"Log in to console.anthropic.com to check your balance."
        })

    return alerts

# ─────────────────────────────────────────────
# CLAUDE API CALLER
# ─────────────────────────────────────────────
total_tokens_this_run = 0

def ask_claude(prompt, max_tokens=900):
    global total_tokens_this_run
    if not ANTHROPIC_API_KEY:
        return "[Claude API key missing]"

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "interleaved-thinking-2025-05-14",
            "content-type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            tokens = data.get("usage", {})
            used = tokens.get("input_tokens", 0) + tokens.get("output_tokens", 0)
            total_tokens_this_run += used
            # Extract text from response (skip tool_use blocks)
            text_parts = [
                b["text"] for b in data.get("content", [])
                if b.get("type") == "text"
            ]
            return " ".join(text_parts).strip() or "[No response]"
    except Exception as e:
        return f"[Error calling Claude: {e}]"

# ─────────────────────────────────────────────
# RSS FEED READER (for case studies & alerts)
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
    # Replace these with your own Google Alert RSS URLs
    # Go to google.com/alerts → create alert → "RSS feed" option
    # Example: "https://www.google.com/alerts/feeds/YOUR_ID/YOUR_TOKEN"
]

def fetch_rss(url, max_items=3):
    """Fetch and parse an RSS feed, return recent items."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            tree = ET.parse(resp)
            root = tree.getroot()
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            items = []
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)

            # Handle both RSS and Atom
            entries = root.findall(".//item") or root.findall(".//atom:entry", ns)
            for entry in entries[:max_items]:
                title_el = entry.find("title") or entry.find("atom:title", ns)
                link_el  = entry.find("link")  or entry.find("atom:link", ns)
                title = title_el.text if title_el is not None else "No title"
                link  = link_el.text if link_el is not None else (
                    link_el.get("href") if link_el is not None else "#"
                )
                items.append({"title": title.strip(), "link": link})
            return items
    except Exception:
        return []

def get_case_studies():
    all_items = []
    for feed_url in DM_FEEDS:
        items = fetch_rss(feed_url, max_items=2)
        all_items.extend(items)
    if not all_items:
        return "[No new case studies found today]"

    headlines = "\n".join(
        f'- "{item["title"]}" ({item["link"]})'
        for item in all_items[:8]
    )
    return ask_claude(
        f"These are recent digital marketing articles published in the last 24 hours:\n{headlines}\n\n"
        f"Pick the 4 most insightful ones (prioritise case studies, unique techniques, and data-backed strategies). "
        f"For each, write: Article title as a link, then 2 bullet points summarising the key insight a digital marketer should know. "
        f"Be concise and practical. No fluff.",
        max_tokens=700
    )

# ─────────────────────────────────────────────
# MODULE 1 — INDUSTRY NEWS
# ─────────────────────────────────────────────
def get_industry_news():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%B %d, %Y")
    return ask_claude(
        f"Search for the most important digital marketing, SEO, and AI Search news from {yesterday}. "
        f"Cover: Google algorithm updates, AI Overviews changes, SearchGPT/Perplexity news, "
        f"social media algorithm changes, paid search updates, and content marketing trends. "
        f"Return exactly 6 updates. For each: "
        f"**Headline** (bold), one sentence summary, and the source name. "
        f"Rank by importance to a digital marketer working in SEO and AI search.",
        max_tokens=900
    )

# ─────────────────────────────────────────────
# MODULE 3 — LINKEDIN
# ─────────────────────────────────────────────
def get_linkedin_summary():
    if not LINKEDIN_TOKEN:
        return (
            "<p style='color:#856404;background:#fff3cd;padding:10px;border-radius:6px;font-size:13px;'>"
            "<b>LinkedIn not connected.</b> Add your LINKEDIN_TOKEN secret to GitHub to enable this module. "
            "<a href='https://www.linkedin.com/developers/'>Get token here</a></p>"
        )
    try:
        # Fetch recent posts via LinkedIn API
        url = "https://api.linkedin.com/v2/ugcPosts?q=authors&authors=List(urn%3Ali%3Aperson%3Ame)&count=5"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {LINKEDIN_TOKEN}",
            "X-Restli-Protocol-Version": "2.0.0"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        posts = data.get("elements", [])
        if not posts:
            return "No LinkedIn posts found from yesterday."

        summary_input = f"I have {len(posts)} LinkedIn posts. Here is the raw data:\n{json.dumps(posts[:3], indent=2)[:1500]}\n\n"
        return ask_claude(
            summary_input +
            "Summarise my LinkedIn activity from yesterday in 3 bullet points: "
            "1) Which post performed best and why, 2) Total estimated reach, 3) One actionable tip to improve tomorrow's post.",
            max_tokens=400
        )
    except Exception as e:
        return f"<p style='color:#721c24;'>LinkedIn fetch error: {e}. Check your token.</p>"

# ─────────────────────────────────────────────
# MODULE 4 — INSTAGRAM
# ─────────────────────────────────────────────
def get_instagram_summary():
    if not INSTAGRAM_TOKEN or not INSTAGRAM_USER_ID:
        return (
            "<p style='color:#856404;background:#fff3cd;padding:10px;border-radius:6px;font-size:13px;'>"
            "<b>Instagram not connected.</b> Add INSTAGRAM_TOKEN and INSTAGRAM_USER_ID secrets to GitHub. "
            "Requires a Business/Creator account. "
            "<a href='https://developers.facebook.com/docs/instagram-api'>Setup guide</a></p>"
        )
    try:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        url = (
            f"https://graph.instagram.com/{INSTAGRAM_USER_ID}/media"
            f"?fields=id,caption,like_count,comments_count,timestamp,media_type"
            f"&access_token={INSTAGRAM_TOKEN}"
        )
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        posts = [p for p in data.get("data", []) if yesterday in p.get("timestamp", "")]
        if not posts:
            return f"No Instagram posts found from {yesterday}."

        summary_input = f"My Instagram posts from {yesterday}:\n{json.dumps(posts, indent=2)[:1000]}\n\n"
        return ask_claude(
            summary_input +
            "Give me a 3-bullet summary: 1) Best performing post, 2) Total likes + comments, "
            "3) One tip to improve engagement based on what worked.",
            max_tokens=400
        )
    except Exception as e:
        return f"<p style='color:#721c24;'>Instagram fetch error: {e}. Check your token.</p>"

# ─────────────────────────────────────────────
# MODULE 5 — COMPETITOR & KEYWORD WATCH
# ─────────────────────────────────────────────
def get_competitor_watch():
    alert_items = []
    for feed_url in GOOGLE_ALERT_FEEDS:
        items = fetch_rss(feed_url, max_items=3)
        alert_items.extend(items)

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%B %d, %Y")

    if alert_items:
        headlines = "\n".join(f'- {i["title"]}' for i in alert_items[:6])
        prompt = (
            f"My competitor monitoring alerts from {yesterday}:\n{headlines}\n\n"
            f"Summarise the 3 most important competitive moves I should know about as a digital marketer. "
            f"For each: what happened and what should I do in response (one sentence each)."
        )
    else:
        prompt = (
            f"Search for any significant moves by major SEO tool companies (Semrush, Ahrefs, Moz, Screaming Frog) "
            f"or major marketing platforms (HubSpot, Mailchimp, Meta Ads, Google Ads) from {yesterday}. "
            f"Also check if any major Google Search ranking changes were detected by industry trackers. "
            f"Give me 3 bullet points on what competitors or platforms are doing that a digital marketer should know."
        )
    return ask_claude(prompt, max_tokens=500)

# ─────────────────────────────────────────────
# MODULE 6 — CONTENT IDEAS
# ─────────────────────────────────────────────
def get_content_ideas():
    today = datetime.now().strftime("%B %d, %Y")
    return ask_claude(
        f"Based on what's trending in digital marketing, SEO, and AI search today ({today}), "
        f"generate 5 content ideas I can post TODAY:\n"
        f"- 3 LinkedIn post ideas (professional, insight-driven, good for engagement)\n"
        f"- 2 Instagram post ideas (visual, punchy, good for saves/shares)\n\n"
        f"For each idea: Topic name, one-line hook/caption opener, and the content angle. "
        f"Make them timely, specific, and tied to real trends — not generic.",
        max_tokens=700
    )

# ─────────────────────────────────────────────
# EMAIL BUILDER
# ─────────────────────────────────────────────
def build_email(modules, cost_alerts, usage):
    today_str   = datetime.now().strftime("%A, %B %d, %Y")
    daily_pct   = min((usage["daily"]   / DAILY_TOKEN_BUDGET)   * 100, 100)
    monthly_pct = min((usage["monthly"] / MONTHLY_TOKEN_BUDGET) * 100, 100)

    def bar(pct, color):
        filled = int(pct / 5)  # 20 segments
        empty  = 20 - filled
        return (
            f'<span style="font-family:monospace;letter-spacing:1px;">'
            f'<span style="color:{color};">{"█"*filled}</span>'
            f'<span style="color:#ccc;">{"░"*empty}</span>'
            f'</span> {pct:.0f}%'
        )

    # Cost alert block
    if cost_alerts:
        top_alert = cost_alerts[0]
        alert_color = "#721c24" if top_alert["level"] == "DANGER" else "#856404"
        alert_bg    = "#f8d7da" if top_alert["level"] == "DANGER" else "#fff3cd"
        alert_icon  = "🚨" if top_alert["level"] == "DANGER" else "⚠️"
        alert_html  = f"""
        <div style="background:{alert_bg};border-left:4px solid {alert_color};
                    padding:14px 18px;border-radius:0 8px 8px 0;margin-bottom:24px;">
          <p style="margin:0 0 6px;font-size:15px;font-weight:700;color:{alert_color};">
            {alert_icon} COST PROTECTION ALERT — ACTION NEEDED</p>
          <p style="margin:0;font-size:13px;color:{alert_color};">{top_alert["message"]}</p>
          <p style="margin:8px 0 0;font-size:12px;color:{alert_color};">
            To stop charges: Go to
            <a href="https://console.anthropic.com" style="color:{alert_color};">console.anthropic.com</a>
            → Billing → Set a spending limit of $0. Or disable the GitHub Actions workflow.
          </p>
        </div>"""
    else:
        alert_html = ""

    def section(number, emoji, title, content, color):
        return f"""
        <div style="margin-bottom:28px;">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;
                      border-bottom:2px solid {color};padding-bottom:8px;">
            <span style="background:{color};color:#fff;border-radius:50%;
                         width:26px;height:26px;display:inline-flex;align-items:center;
                         justify-content:center;font-size:12px;font-weight:700;flex-shrink:0;">
              {number}</span>
            <h2 style="margin:0;font-size:17px;font-weight:700;color:#1a1a2e;">
              {emoji} {title}</h2>
          </div>
          <div style="font-size:14px;line-height:1.8;color:#333;">{content}</div>
        </div>"""

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:'Helvetica Neue',Arial,sans-serif;">
  <div style="max-width:640px;margin:24px auto;background:#ffffff;
              border-radius:16px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">

    <!-- HEADER -->
    <div style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 60%,#0f3460 100%);
                padding:28px 32px 24px;">
      <p style="margin:0 0 4px;font-size:12px;color:#8899bb;letter-spacing:2px;
                text-transform:uppercase;">Digital Marketing Intelligence</p>
      <h1 style="margin:0;font-size:24px;font-weight:800;color:#ffffff;">
        Your Daily DM Digest</h1>
      <p style="margin:6px 0 0;font-size:13px;color:#8899bb;">{today_str}</p>
    </div>

    <div style="padding:28px 32px;">

      <!-- COST ALERT (if any) -->
      {alert_html}

      <!-- MODULE 1: NEWS -->
      {section(1, "📰", "Industry News — SEO &amp; AI Search",
               modules.get("news","").replace("\n","<br>"), "#0f3460")}

      <!-- MODULE 2: CASE STUDIES -->
      {section(2, "📚", "New Case Studies &amp; Techniques",
               modules.get("case_studies","").replace("\n","<br>"), "#e94560")}

      <!-- MODULE 3: LINKEDIN -->
      {section(3, "💼", "LinkedIn — Yesterday's Performance",
               modules.get("linkedin","").replace("\n","<br>"), "#0077b5")}

      <!-- MODULE 4: INSTAGRAM -->
      {section(4, "📸", "Instagram — Yesterday's Performance",
               modules.get("instagram","").replace("\n","<br>"), "#c13584")}

      <!-- MODULE 5: COMPETITORS -->
      {section(5, "🔍", "Competitor &amp; Keyword Watch",
               modules.get("competitors","").replace("\n","<br>"), "#f5a623")}

      <!-- MODULE 6: CONTENT IDEAS -->
      {section(6, "✍️", "Today's Content Ideas",
               modules.get("ideas","").replace("\n","<br>"), "#27ae60")}

      <!-- USAGE METER -->
      <div style="background:#f8f9fc;border-radius:10px;padding:16px 20px;margin-top:8px;">
        <p style="margin:0 0 10px;font-size:12px;font-weight:700;color:#555;
                  text-transform:uppercase;letter-spacing:1px;">
          🛡️ Free Tier Usage Monitor</p>
        <table style="width:100%;font-size:12px;color:#444;">
          <tr>
            <td style="padding:3px 0;width:120px;">Today's tokens</td>
            <td>{bar(daily_pct, "#e94560")}</td>
            <td style="text-align:right;color:#888;">{usage["daily"]:,} / {DAILY_TOKEN_BUDGET:,}</td>
          </tr>
          <tr>
            <td style="padding:3px 0;">This month</td>
            <td>{bar(monthly_pct, "#0f3460")}</td>
            <td style="text-align:right;color:#888;">{usage["monthly"]:,} / {MONTHLY_TOKEN_BUDGET:,}</td>
          </tr>
        </table>
        <p style="margin:10px 0 0;font-size:11px;color:#999;">
          ✅ Green = safe &nbsp;|&nbsp; ⚠️ 70%+ = watch &nbsp;|&nbsp; 🚨 90%+ = stop before charges.
          Check anytime at <a href="https://console.anthropic.com" style="color:#0f3460;">console.anthropic.com</a>
        </p>
      </div>

    </div>

    <!-- FOOTER -->
    <div style="background:#f8f9fc;padding:16px 32px;border-top:1px solid #eee;
                text-align:center;font-size:11px;color:#aaa;">
      Automated by your GitHub Actions digest — running free on Anthropic's API free tier.<br>
      To pause: go to your GitHub repo → Actions → disable the workflow.
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
        print("Email credentials missing — printing to console instead.")
        print(html_content[:500])
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 DM Digest — {datetime.now().strftime('%b %d')}"
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())
    print(f"✅ Email sent to {RECIPIENT_EMAIL}")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print("🚀 Starting DM Daily Digest...")

    modules = {}

    print("  [1/6] Fetching industry news...")
    modules["news"] = get_industry_news()

    print("  [2/6] Fetching case studies...")
    modules["case_studies"] = get_case_studies()

    print("  [3/6] Fetching LinkedIn activity...")
    modules["linkedin"] = get_linkedin_summary()

    print("  [4/6] Fetching Instagram activity...")
    modules["instagram"] = get_instagram_summary()

    print("  [5/6] Fetching competitor watch...")
    modules["competitors"] = get_competitor_watch()

    print("  [6/6] Generating content ideas...")
    modules["ideas"] = get_content_ideas()

    # Update usage tracker
    usage       = update_usage(total_tokens_this_run)
    cost_alerts = check_cost_alerts(usage)

    print(f"  📊 Tokens used this run: {total_tokens_this_run:,}")
    print(f"  📊 Daily total: {usage['daily']:,} / {DAILY_TOKEN_BUDGET:,}")
    print(f"  📊 Monthly total: {usage['monthly']:,} / {MONTHLY_TOKEN_BUDGET:,}")
    if cost_alerts:
        print(f"  ⚠️  COST ALERT: {cost_alerts[0]['message']}")

    print("  📧 Building and sending email...")
    html = build_email(modules, cost_alerts, usage)
    send_email(html)
    print("✅ Done!")

if __name__ == "__main__":
    main()
