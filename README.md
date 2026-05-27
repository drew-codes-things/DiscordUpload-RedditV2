# DiscordUpload-Reddit

A local web app to send Reddit posts and local files directly to a Discord channel via webhook.

**Version 2 requires no Reddit API credentials.** It uses Reddit's public JSON API (`reddit.com/r/{sub}/hot.json`) so you can run it immediately with zero setup.

---

## Requirements

- Python 3.8+
- Dependencies:

```bash
pip install -r requirements.txt
```

---

## Usage

```bash
python backend.py
```

Then open [http://localhost:1432](http://localhost:1432) in your browser.

From the web UI you can:
- **Upload local files** (images, videos) directly to a Discord webhook
- **Fetch Reddit posts** from any public subreddit and send them as Discord embeds

---

## What gets sent to Discord

| Post type | Embed content |
|-----------|---------------|
| Image post | Embed with inline image |
| Reddit-hosted video | Embed with video URL |
| Text/link post | Embed with title, permalink, and post body |

Already-sent posts are tracked in `sent_posts.json` and skipped for 7 days to avoid duplicates.

---

## Why no credentials?

Reddit's `.json` API is publicly accessible — it's the same data your browser loads when you add `.json` to any Reddit URL. No OAuth, no client ID, no secret needed.

---

## License

MIT
