# DiscordUpload-RedditV2

Hybrid tool combining Discord webhooks and a Flask backend for uploading files directly to Discord, with an optional Reddit media fetcher that pulls posts from any subreddit and sends them as embeds.

## What it does

- **File upload tab** -> drag and drop images/videos, paste a Discord webhook URL, and send them directly to a channel
- **Reddit fetch tab** -> enter a subreddit name, pick how many posts to pull, and the backend sends each post as a Discord embed (images embedded, videos linked, text posts included as description)
- Duplicate post tracking via `sent_posts.json` (auto-expires after 7 days) so the same post isn't sent twice
- Rate limiting built in (100 req/min globally, 30/min on Reddit fetch)

## File Structure

```
DiscordUpload-RedditV2/
    backend.py         # Flask server (entry point)
    website/           # HTML templates
    static/            # CSS / JS assets
    requirements.txt
    README.md
    LICENSE
```

## Installation

### Linux (Recommended - Virtual Environment)

```bash
git clone https://github.com/drew-codes-things/DiscordUpload-RedditV2.git
cd DiscordUpload-RedditV2

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### macOS / Windows (Simple Method)

```bash
git clone https://github.com/drew-codes-things/DiscordUpload-RedditV2.git
cd DiscordUpload-RedditV2

pip install -r requirements.txt
```

## Usage

```bash
python backend.py
```

The server starts on **http://localhost:1432**. Open that in your browser.

## Getting a Discord Webhook URL

1. Open your Discord server -> go to a channel
2. Channel Settings -> Integrations -> Webhooks -> New Webhook
3. Copy the webhook URL (format: `https://discord.com/api/webhooks/...`)
4. Paste it into the webhook field in the web UI

## Supported File Types (Upload)

`png`, `jpg`, `jpeg`, `gif`, `mp4`, `webm`, `avi`, `mov`, `mkv`

## Reddit Fetch

Enter a subreddit name (e.g. `oddlysatisfying`) and a post count (max 200). The backend:

1. Fetches posts from `reddit.com/r/{sub}/hot.json` (no API key needed)
2. Skips stickied posts and any post already in `sent_posts.json`
3. Sends each post as a Discord embed -> image posts get an embedded image, video posts get a linked video, text posts include their body in the embed description

## Requirements

- Python 3.8+

## License

MIT License
