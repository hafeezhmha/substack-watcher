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
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

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

def fetch_archive():
    url = f"https://{SUBSTACK_DOMAIN}/api/v1/archive?sort=new&limit=5"
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching archive: {e}")
        return []

def fetch_post_details(slug):
    url = f"https://{SUBSTACK_DOMAIN}/api/v1/posts/{slug}"
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching post details for {slug}: {e}")
        return None

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

def main():
    state = load_state()
    last_post_id = state.get("last_post_id")
    
    archive = fetch_archive()
    if not archive:
        print("No posts found in archive.")
        return

    # archive is a list of posts
    latest_post = archive[0]
    latest_id = latest_post.get("id")
    latest_slug = latest_post.get("slug")
    
    if last_post_id and latest_id == last_post_id:
        print("No new posts.")
        return

    print(f"New post detected: {latest_post.get('title')} (ID: {latest_id})")
    
    # It's a new post (or first run)
    # Fetch details to get body_html
    post_details = fetch_post_details(latest_slug)
    ticket_link = None
    
    if post_details:
        body_html = post_details.get("body_html", "")
        if body_html:
            ticket_link = extract_ticket_link(body_html)
    
    if not ticket_link:
        print("No ticket link found in post body.")
    else:
        print(f"Found ticket link: {ticket_link}")

    # Send email
    send_email(
        post_title=latest_post.get("title"),
        published_date=latest_post.get("post_date"),
        ticket_link=ticket_link
    )

    # Update state
    state["last_post_id"] = latest_id
    state["last_published_at"] = latest_post.get("post_date")
    save_state(state)

if __name__ == "__main__":
    main()
