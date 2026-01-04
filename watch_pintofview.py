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


# ... (imports remain the same, adding xml.etree.ElementTree)
import xml.etree.ElementTree as ET

# ... (Configuration, Email Config, Ticketing logic, LinkExtractor, State functions remain same)

def fetch_feed():
    url = f"https://{SUBSTACK_DOMAIN}/feed.xml"
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"Error fetching feed: {e}")
        return None

def main():
    state = load_state()
    last_post_id = state.get("last_post_id")
    
    feed_content = fetch_feed()
    if not feed_content:
        return

    try:
        root = ET.fromstring(feed_content)
        # RSS 2.0: channel -> item
        channel = root.find("channel")
        if channel is None:
            print("Invalid feed format: no channel found")
            return
            
        latest_item = channel.find("item")
        if latest_item is None:
            print("No items found in feed.")
            return

        # Extract details
        title = latest_item.find("title").text
        link = latest_item.find("link").text
        pub_date = latest_item.find("pubDate").text
        guid = latest_item.find("guid").text
        
        # Use guid as ID (it's usually the permalink)
        # We can also handle simple string comparison for state
        current_id = guid
        
        if last_post_id and current_id == last_post_id:
            print("No new posts.")
            return

        print(f"New post detected: {title}")
        
        # Get content for ticket link extraction
        # Content is often in <content:encoded>, which ElementTree might handle with namespaces
        # Or we can just grab description if content is missing
        
        # Namespace map for 'content'
        namespaces = {'content': 'http://purl.org/rss/1.0/modules/content/'}
        content_encoded = latest_item.find('content:encoded', namespaces)
        
        body_html = ""
        if content_encoded is not None:
            body_html = content_encoded.text
        else:
            description = latest_item.find("description")
            if description is not None:
                body_html = description.text
        
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

    except ET.ParseError as e:
        print(f"Error parsing XML feed: {e}")

if __name__ == "__main__":
    main()
