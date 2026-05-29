# DiscordUpload-RedditV2

A hybrid tool that combines Discord webhooks with a Flask backend to upload files to Discord, while also allowing Reddit media fetching from subreddits.

## Features

- Upload files directly to Discord via webhooks
- Fetch and download media from Reddit subreddits
- Flask web server for easy interaction
- Supports images, videos, and other file types

## Installation

```bash
git clone https://github.com/drew-codes-things/DiscordUpload-RedditV2.git
cd DiscordUpload-RedditV2
pip install -r requirements.txt
```

## Usage

Run the Flask server:
```bash
python app.py
```

Then use the web interface or API endpoints to upload or download media.

## Requirements

- Python 3.8+
- Discord webhook URL(s)
- Reddit API credentials (optional, for Reddit features)

## License

MIT License