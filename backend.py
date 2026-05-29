import os, io, time, sys, json, shutil, logging, requests
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from requests.exceptions import RequestException
from dotenv import load_dotenv
from datetime import datetime, timedelta
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()

REDDIT_HEADERS  = {'User-Agent': 'DiscordUpload-Reddit/2.0 by Drew'}
MAX_REDDIT_ITEMS = 200
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB -- Discord webhook hard limit

# Minimum delay between consecutive Discord webhook POSTs to stay well under
# the ~30 requests/30s rate limit. 0.5s gives a headroom of ~20 req/10s.
WEBHOOK_POST_DELAY = 0.5


class CustomFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.INFO and record.msg.startswith(('Starting', 'Ready', 'Shutting down')):
            return f"INFO: {record.msg}"
        elif record.levelno == logging.INFO and 'WEBSITE' in record.msg:
            return f"WEBSITE: {record.msg.split('WEBSITE: ')[-1]}"
        elif record.levelno == logging.INFO and 'RESULT' in record.msg:
            return f"RESULT: {record.msg.split('RESULT: ')[-1]}"
        elif record.levelno == logging.INFO and record.msg.startswith('NOTE:'):
            return record.msg
        return super().format(record)


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(CustomFormatter())
    logger.handlers.clear()
    logger.addHandler(console_handler)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    return logger


app = Flask(__name__, template_folder='website')

_secret = os.getenv('FLASK_SECRET_KEY')
if not _secret:
    raise RuntimeError(
        "FLASK_SECRET_KEY is not set in .env. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\" "
        "and add it to your .env file."
    )
app.config['SECRET_KEY'] = _secret

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'webm', 'avi', 'mov', 'mkv'}
SENT_POSTS_FILE = './sent_posts.json'
SENT_POSTS_BACKUP = './sent_posts.json.bak'

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per minute"]
)


def allowed_file(filename):
    return ('.' in filename and
            filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS and
            len(secure_filename(filename)) > 0)


def validate_webhook_url(url):
    return url.startswith('https://discord.com/api/webhooks/')


def fetch_reddit_posts_json(subreddit_name, limit):
    """Fetch posts from Reddit's public JSON API -- no credentials needed."""
    posts = []
    after = None

    while len(posts) < limit:
        batch = min(100, limit - len(posts))
        url = f"https://www.reddit.com/r/{subreddit_name}/hot.json?limit={batch}&include_over_18=on"
        if after:
            url += f"&after={after}"

        try:
            resp = requests.get(url, headers=REDDIT_HEADERS, timeout=15)
            if resp.status_code == 429:
                time.sleep(60)
                continue
            resp.raise_for_status()
            data = resp.json().get('data', {})
            children = data.get('children', [])
            if not children:
                break
            for child in children:
                posts.append(child.get('data', {}))
            after = data.get('after')
            if not after:
                break
        except RequestException as e:
            logger.error(f"Error fetching from Reddit: {e}")
            break

    return posts


def extract_video_url(post):
    media = post.get('media') or {}
    rv = media.get('reddit_video') or {}
    if rv.get('fallback_url'):
        return rv['fallback_url']
    url = post.get('url', '')
    if any(url.endswith(ext) for ext in ['.mp4', '.webm', '.mov', '.mkv', '.avi']):
        return url
    if 'v.redd.it' in url:
        return url
    return None


def extract_gallery_images(post):
    """
    For gallery posts (is_gallery=True), return a list of the best-quality
    image URLs from media_metadata, preserving the gallery order.
    Returns an empty list if the post is not a gallery or has no metadata.
    """
    if not post.get('is_gallery'):
        return []
    media_metadata = post.get('media_metadata') or {}
    items_order = []
    gallery_data = post.get('gallery_data') or {}
    for item in gallery_data.get('items', []):
        media_id = item.get('media_id')
        if media_id and media_id in media_metadata:
            meta = media_metadata[media_id]
            status = meta.get('status')
            if status != 'valid':
                continue
            # prefer 'p' (preview sizes) descending, fall back to 's' (source)
            previews = meta.get('p', [])
            if previews:
                best = previews[-1].get('u', '')
            else:
                best = (meta.get('s') or {}).get('u', '')
            if best:
                # Reddit preview URLs use HTML entities
                items_order.append(best.replace('&amp;', '&'))
    return items_order


def load_sent_posts():
    """
    Load the sent-posts deduplication dict from disk.

    If the JSON file is corrupted (empty file, partial write, etc.) a warning
    is logged, the corrupted file is backed up to sent_posts.json.bak so it
    can be inspected, and an empty dict is returned. This prevents all
    previously-seen posts being re-sent to Discord after a bad write.
    """
    if not os.path.exists(SENT_POSTS_FILE):
        return {}
    try:
        with open(SENT_POSTS_FILE, 'r') as f:
            data = json.load(f)
        cutoff = datetime.now() - timedelta(days=7)
        return {k: v for k, v in data.items()
                if datetime.fromisoformat(v) > cutoff}
    except json.JSONDecodeError as e:
        logger.warning(
            f"sent_posts.json is corrupted ({e}). "
            f"Backing up to {SENT_POSTS_BACKUP} and starting fresh -- "
            "posts from the last 7 days may be re-sent once."
        )
        try:
            shutil.copy2(SENT_POSTS_FILE, SENT_POSTS_BACKUP)
        except OSError as backup_err:
            logger.warning(f"Could not create backup: {backup_err}")
        return {}
    except (IOError, ValueError) as e:
        logger.error(f"Error loading sent posts: {e}")
        return {}


def save_sent_posts(sent_posts):
    try:
        with open(SENT_POSTS_FILE, 'w') as f:
            json.dump(sent_posts, f, indent=4)
    except IOError as e:
        logger.error(f"Error saving sent posts: {e}")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
@limiter.limit("50 per minute")
def upload_file():
    webhook_url = request.form['webhook_url']
    if not validate_webhook_url(webhook_url):
        return jsonify({"error": "Invalid webhook URL"}), 400
    if 'files[]' not in request.files:
        return jsonify({"error": "No files were uploaded"}), 400

    files = request.files.getlist('files[]')
    uploaded_files = 0
    failed_files = []

    for file in files:
        if file.filename == '':
            failed_files.append('Empty filename')
            continue
        if not allowed_file(file.filename):
            failed_files.append(file.filename)
            continue

        safe_name = secure_filename(file.filename)

        # Read once so we can check size before uploading
        file_bytes = file.read()
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            failed_files.append(
                f"{safe_name} (exceeds 25 MB limit: {len(file_bytes) // (1024*1024)} MB)"
            )
            continue

        try:
            response = requests.post(
                webhook_url,
                files={'file': (safe_name, io.BytesIO(file_bytes))}
            )
            if response.status_code in [200, 204]:
                uploaded_files += 1
            else:
                failed_files.append(safe_name)
        except (RequestException, Exception):
            failed_files.append(safe_name)

    logger.info("RESULT: Successfully sent uploaded files")
    return jsonify({
        "message": f"{uploaded_files}/{len(files)} files uploaded successfully",
        "status": "success" if uploaded_files == len(files) else "partial",
        "uploaded_count": uploaded_files,
        "total_files": len(files),
        "failed_files": failed_files
    })


@app.route('/fetch_reddit', methods=['POST'])
@limiter.limit("30 per minute")
def fetch_reddit():
    webhook_url = request.form['webhook_url']
    subreddit_name = request.form['subreddit_name']

    try:
        num_items = int(request.form['num_items'])
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "num_items must be an integer"}), 400

    if not subreddit_name:
        return jsonify({"status": "error", "message": "Subreddit name is required"}), 400
    if num_items <= 0:
        return jsonify({"status": "error", "message": "Number of posts must be greater than 0"}), 400
    if num_items > MAX_REDDIT_ITEMS:
        return jsonify({
            "status": "error",
            "message": f"num_items cannot exceed {MAX_REDDIT_ITEMS}. Requested: {num_items}"
        }), 400

    try:
        sent_posts = load_sent_posts()
        sent_count = 0
        failed_items = []

        all_posts = fetch_reddit_posts_json(subreddit_name, num_items + 50)
        posts = [p for p in all_posts if not p.get('stickied') and p.get('id') not in sent_posts]
        posts = posts[:num_items]

        for post in posts:
            video_url     = extract_video_url(post)
            gallery_images = extract_gallery_images(post)
            post_url      = post.get('url', '')

            embed = {
                "title": post.get('title', ''),
                "color": 0x40e0d0,
                "description": f"[View Post](https://reddit.com{post.get('permalink', '')})",
            }

            if video_url:
                embed["video"] = {"url": video_url}
            elif gallery_images:
                # Use the first gallery image as the embed image;
                # append remaining URLs to the description so nothing is lost.
                embed["image"] = {"url": gallery_images[0]}
                if len(gallery_images) > 1:
                    extra = "\n".join(gallery_images[1:])
                    embed["description"] += f"\n\n**Gallery ({len(gallery_images)} images):**\n{extra}"
            elif post_url.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                embed["image"] = {"url": post_url}
            else:
                desc = post.get('selftext', '')
                if len(desc) > 4096:
                    desc = desc[:4090] + "..."
                if desc:
                    embed["description"] += f"\n\n{desc}"

            try:
                response = requests.post(webhook_url, json={"embeds": [embed]})
                if response.status_code == 204:
                    sent_posts[post['id']] = datetime.now().isoformat()
                    sent_count += 1
                    # Throttle to avoid hitting Discord's webhook rate limit
                    # (~30 requests per 30s per webhook URL).
                    time.sleep(WEBHOOK_POST_DELAY)
                else:
                    failed_items.append(post.get('title', post['id']))
            except RequestException:
                failed_items.append(post.get('title', post['id']))

        save_sent_posts(sent_posts)

        if failed_items:
            return jsonify({"status": "partial", "message": f"Sent {sent_count} posts. Failed: {', '.join(failed_items)}"})
        return jsonify({"status": "success", "message": f"Successfully sent {sent_count} Reddit posts to Discord!"})

    except Exception as e:
        logger.error(f"Error fetching posts from r/{subreddit_name}: {e}")
        return jsonify({"status": "error", "message": f"Error fetching posts from r/{subreddit_name}"}), 500


if __name__ == '__main__':
    logger = setup_logging()
    logger.info("NOTE: Coded by Drew")
    logger.info("Ready")
    logger.info("WEBSITE: http://localhost:1432 or http://127.0.0.1:1432")
    try:
        app.run(host='0.0.0.0', port=1432, debug=False)
    except Exception as e:
        print(f"Failed to start the application: {e}")
        sys.exit(1)
    finally:
        logger.info("INFO: Shutting down...")
