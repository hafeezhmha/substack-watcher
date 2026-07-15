"""
Substack Watcher for 'pintofviewclub'

This script checks for new posts on the specified Substack publication.
If a new post is found, it parses the content for a ticket booking link
and sends an email notification via Gmail SMTP.

SETUP & CONSIGNMENT:
--------------------
1. GitHub Secrets:
   Go to your repository -> Settings -> Secrets and variables -> Actions
   Add the following repository secrets:
   - EMAIL_ADDRESS: Your Gmail address (e.g. user@gmail.com)
   - EMAIL_APP_PASSWORD: Your Gmail App Password (generated in Google Account > Security)
   - EMAIL_TO: The recipient email address

2. State Management:
   The script uses `state.json` to track the ID of the last processed post.
   This file is automatically updated and committed back to the repo by the GitHub Action.
   Initially, it can be an empty JSON object `{}`.

3. Local Testing:
   - Install dependencies: `pip install requests`
   - Run: `python watch_pintofview.py`
   - To force a run suitable for testing email, you can manually edit `state.json` 
     to reduce the `last_post_id` or delete the file (this will treat the latest post as new).
   - Expected output: "New post detected...", "Found ticket link...", "Email sent..." (or "Would have sent..." if no secrets).

"""
import os
import json
import sys
import smtplib
import time
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

# Configuration
SUBSTACK_DOMAIN = "pintofviewclub.substack.com"
STATE_FILE = "state.json"

# Headers to mimic a real browser to avoid 403 Forbidden
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# Email Configuration from Environment Variables
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
EMAIL_TO = os.environ.get("EMAIL_TO")

# Ticketing logic
KNOWN_TICKETING_DOMAINS = [
    "eventbrite",
    "lu.ma",
    "ra.co",
    "razorpay.com",
    "rzp.io",
    "bookmyshow",
    "urbanaut.app",
    "puttingscene.com",
]

TICKET_KEYWORDS = [
    "ticket",
    "book",
    "rsvp",
    "register"
]

BOOKING_PATH_KEYWORDS = [
    "booking",
    "bookings",
    "checkout",
    "event",
    "events",
    "spot",
]

IGNORED_LINK_DOMAINS = [
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "substackcdn.com",
    "twitter.com",
    "x.com",
]

IMAGE_EXTENSIONS = (".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp")

class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_link = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attributes = dict(attrs)
            self.current_link = attributes.get("href")
            self.current_text = []

    def handle_data(self, data):
        if self.current_link:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current_link:
            self.links.append((self.current_link, " ".join(self.current_text)))
            self.current_link = None
            self.current_text = []

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)




def ticket_link_score(url, text):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return 0

    hostname = parsed.hostname.lower()
    path_and_query = f"{parsed.path}?{parsed.query}".lower()
    text_lower = text.lower()

    if hostname.endswith("substack.com") or any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in IGNORED_LINK_DOMAINS
    ):
        return 0
    if parsed.path.lower().endswith(IMAGE_EXTENSIONS):
        return 0

    score = 0
    if any(hostname == domain or hostname.endswith(f".{domain}") for domain in KNOWN_TICKETING_DOMAINS):
        score += 100
    if any(keyword in hostname for keyword in TICKET_KEYWORDS):
        score += 40
    if any(keyword in path_and_query for keyword in TICKET_KEYWORDS):
        score += 40
    if any(keyword in path_and_query for keyword in BOOKING_PATH_KEYWORDS):
        score += 30
    if any(keyword in text_lower for keyword in TICKET_KEYWORDS):
        score += 40

    return score

def extract_ticket_links(body_html):
    parser = LinkExtractor()
    parser.feed(body_html)

    candidates = [
        (ticket_link_score(url, text), index, url)
        for index, (url, text) in enumerate(parser.links)
    ]
    candidates = [candidate for candidate in candidates if candidate[0] > 0]
    return list(dict.fromkeys(candidate[2] for candidate in candidates))


def extract_ticket_link(body_html):
    candidates = extract_ticket_links(body_html)
    if not candidates:
        return None

    return candidates[0]

def send_email(post_title, published_date, ticket_links):
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD or not EMAIL_TO:
        print("Email credentials are not set.")
        return False

    msg = EmailMessage()
    msg['Subject'] = "New Pint of View guest announced"
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_TO

    booking_links = "\n".join(ticket_links) if ticket_links else "No specific booking link found."
    content = f"""
New post published: {post_title}
Date: {published_date}

Booking Links:
{booking_links}
    """
    msg.set_content(content)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        print("Email sent successfully.")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def get_with_retries(url):
    for attempt in range(1, 4):
        try:
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            print(f"Feed request attempt {attempt}/3 failed: {error}")
            if attempt < 3:
                time.sleep(attempt)
    return None


def parse_rss_feed(xml_content):
    root = ET.fromstring(xml_content)
    items = []
    for item in root.findall("./channel/item"):
        content = next(
            (child.text or "" for child in item if child.tag.endswith("}encoded")),
            "",
        )
        items.append({
            "title": item.findtext("title"),
            "link": item.findtext("link"),
            "pubDate": item.findtext("pubDate"),
            "guid": item.findtext("guid"),
            "description": item.findtext("description", ""),
            "content": content,
        })
    return {"items": items}


def fetch_feed_json():
    rss_url = f"https://{SUBSTACK_DOMAIN}/feed.xml"
    api_url = f"https://api.rss2json.com/v1/api.json?rss_url={rss_url}"

    response = get_with_retries(api_url)
    if response:
        try:
            data = response.json()
            if data.get("status") == "ok":
                return data
            print(f"rss2json error: {data.get('message')}")
        except ValueError as error:
            print(f"Invalid rss2json response: {error}")

    print("Falling back to the direct Substack RSS feed.")
    response = get_with_retries(rss_url)
    if not response:
        return None
    try:
        return parse_rss_feed(response.content)
    except ET.ParseError as error:
        print(f"Invalid direct RSS response: {error}")
        return None


def post_id(item):
    return item.get("guid") or item.get("link")


def unseen_items(items, last_post_id):
    if not items:
        return []
    if not last_post_id:
        return [items[0]]

    for index, item in enumerate(items):
        if post_id(item) == last_post_id:
            return list(reversed(items[:index]))

    print("Last processed post was not found in the feed; processing all available posts.")
    return list(reversed(items))

def main():
    state = load_state()
    last_post_id = state.get("last_post_id")
    
    feed_data = fetch_feed_json()
    if not feed_data or "items" not in feed_data:
        print("Could not fetch a usable feed.")
        return 1

    items = feed_data["items"]
    if not items:
        print("No items found.")
        return 0

    new_items = unseen_items(items, last_post_id)
    if not new_items:
        print("No new posts.")
        return 0

    for item in new_items:
        current_id = post_id(item)
        if not current_id:
            print("New post is missing a stable ID.")
            return 1

        title = item.get("title")
        pub_date = item.get("pubDate")
        print(f"New post detected: {title}")

        body_html = item.get("content") or item.get("description", "")
        ticket_links = extract_ticket_links(body_html) if body_html else []

        if not ticket_links:
            print("No ticket link found in post body.")
        else:
            print("Found ticket links:")
            for ticket_link in ticket_links:
                print(f"- {ticket_link}")

        if not send_email(title, pub_date, ticket_links):
            print("Email delivery failed; state was not updated.")
            return 1

        state["last_post_id"] = current_id
        state["last_published_at"] = pub_date
        save_state(state)

    return 0

if __name__ == "__main__":
    sys.exit(main())
