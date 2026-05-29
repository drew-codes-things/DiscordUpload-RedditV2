# DiscordUpload-RedditV2

Hybrid tool combining Discord webhooks + Flask backend for file uploads to Discord, with optional Reddit media fetching.

## Technical Architecture

- **Backend**: Flask (Python)
- **Frontend**: Simple web interface
- **Discord Integration**: Webhook uploads (images, videos, files)
- **Reddit Integration**: Fetch media from subreddits (optional)

## File Structure

```
DiscordUpload-RedditV2/
├── app.py                 # Flask server
├── requirements.txt
├── README.md
└── LICENSE
```

## Installation

```bash
git clone https://github.com/drew-codes-things/DiscordUpload-RedditV2.git
pip install -r requirements.txt
python app.py
```

## Usage

Run the Flask server and use the web UI or API to upload files or download Reddit media.

## Requirements

- Python 3.8+
- Discord webhook URL(s)

## License

MIT License