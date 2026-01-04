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
import re
from datetime import datetime
from email.message import EmailMessage
from html.parser import HTMLParser

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
    "ticket",
    "lu.ma",
    "ra.co",
    "razorpay.com",
    "bookmyshow"
]

TICKET_KEYWORDS = [
    "ticket",
    "book",
    "rsvp",
    "register"
]

class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = None
            text = "" # We might want text, but HTMLParser processes text in handle_data separate from tags.
                      # We can't easily associate text with the exact tag without a more complex state machine.
                      # For now, let's just look at the href.
            for attr, val in attrs:
                if attr == "href":
                    href = val
            
            if href:
                self.links.append(href)

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




def is_ticketing_link(url):
    url_lower = url.lower()
    
    # Ignore internal links and social
    if "substack.com" in url_lower and "pintofviewclub" in url_lower:
        return False
    if "facebook.com" in url_lower or "twitter.com" in url_lower or "instagram.com" in url_lower or "linkedin.com" in url_lower:
        return False
        
    for domain in KNOWN_TICKETING_DOMAINS:
        if domain in url_lower:
            return True
            
    # Check for keywords in the path/query (not as reliable, but helpful)
    for keyword in TICKET_KEYWORDS:
        if keyword in url_lower:
            return True
            
    return False

def extract_ticket_link(body_html):
    parser = LinkExtractor()
    parser.feed(body_html)
    
    for link in parser.links:
        if is_ticketing_link(link):
            return link
            
    return None

def send_email(post_title, published_date, ticket_link):
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD or not EMAIL_TO:
        print("Email credentials not set. Skipping email.")
        print(f"Would have sent: {post_title} - {ticket_link}")
        return

    msg = EmailMessage()
    msg['Subject'] = "New Pint of View guest announced"
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_TO

    content = f"""
New post published: {post_title}
Date: {published_date}

Ticket Link: {ticket_link if ticket_link else "No specific booking link found."}
    """
    msg.set_content(content)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        print("Email sent successfully.")
    except Exception as e:
        print(f"Failed to send email: {e}")


def fetch_feed_json():
    # Use rss2json.com as a proxy to bypass Cloudflare and parse XML to JSON
    # This avoids the 403 Forbidden error from Substack's direct RSS feed.
    rss_url = f"https://{SUBSTACK_DOMAIN}/feed.xml"
    api_url = f"https://api.rss2json.com/v1/api.json?rss_url={rss_url}"
    
    try:
        resp = requests.get(api_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "ok":
            print(f"rss2json error: {data.get('message')}")
            return None
        return data
    except Exception as e:
        print(f"Error fetching feed via rss2json: {e}")
        return None

def main():
    state = load_state()
    last_post_id = state.get("last_post_id")
    
    feed_data = fetch_feed_json()
    if not feed_data or "items" not in feed_data:
        print("No items found in feed.")
        return

    items = feed_data["items"]
    if not items:
        print("No items found.")
        return
        
    latest_item = items[0]

    # Extract details
    title = latest_item.get("title")
    link = latest_item.get("link")
    pub_date = latest_item.get("pubDate")
    guid = latest_item.get("guid")
    
    # Use guid as ID
    current_id = guid
    
    if last_post_id and current_id == last_post_id:
        print("No new posts.")
        return

    print(f"New post detected: {title}")
    
    # rss2json typically puts the full content in 'content'
    body_html = latest_item.get("content", "")
    if not body_html:
        body_html = latest_item.get("description", "")
    
    ticket_link = None
    if body_html:
        ticket_link = extract_ticket_link(body_html)
    
    if not ticket_link:
        print("No ticket link found in post body.")
    else:
        print(f"Found ticket link: {ticket_link}")

    # Send email
    send_email(
        post_title=title,
        published_date=pub_date,
        ticket_link=ticket_link
    )

    # Update state
    state["last_post_id"] = current_id
    state["last_published_at"] = pub_date
    save_state(state)

if __name__ == "__main__":
    main()
