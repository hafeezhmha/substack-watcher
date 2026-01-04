# Pint of View Substack Watcher

A Python-based automation tool that monitors the [Pint of View Substack](https://pintofviewclub.substack.com/) for new posts, extracts ticket booking links, and sends instant email notifications.

It is designed to run on **GitHub Actions** on a schedule (completely free), ensuring you never miss a limited-seat guest list.

## Features

- **RSS Monitoring**: Checks the RSS feed every 30 minutes during peak hours.
- **Bot Bypass**: Uses `rss2json.com` as a proxy to bypass Substack/Cloudflare bot protections (403 Forbidden).
- **Smart Extraction**: Parses post content to find booking links for Eventbrite, Razorpay, Luma, etc.
- **State Persistence**: Remembers the last processed post to avoid duplicate emails.
- **Email Notifications**: Sends an email via Gmail SMTP with the direct booking link.

## Setup

### 1. Repository Secrets
For the email notifications to work, you must add the following **Secrets** to your GitHub Repository (`Settings` -> `Secrets and variables` -> `Actions`):

| Secret Name | Description |
|---|---|
| `EMAIL_ADDRESS` | Your Gmail address (e.g., `you@gmail.com`) |
| `EMAIL_APP_PASSWORD` | App Password generated from Google Account > Security > 2-Step Verification > App passwords. |
| `EMAIL_TO` | The email address to receive notifications. |

### 2. Schedule
The workflow is defined in `.github/workflows/schedule.yaml`.
- **Peak Hours (09:30 AM - 01:30 AM IST)**: Runs every 30 minutes.
- **Off-Peak**: Runs every 2 hours.

## Local Development

To run the script locally:

1. **Install dependencies**:
   ```bash
   pip install requests
   ```

2. **Set Environment Variables**:
   ```bash
   export EMAIL_ADDRESS="your@email.com"
   export EMAIL_APP_PASSWORD="your-app-password"
   export EMAIL_TO="target@email.com"
   ```

3. **Run**:
   ```bash
   python watch_pintofview.py
   ```

## Files

- `watch_pintofview.py`: Main logic script.
- `.github/workflows/schedule.yaml`: Automation configuration.
- `state.json`: Tracks the last seen post ID (auto-updated).
