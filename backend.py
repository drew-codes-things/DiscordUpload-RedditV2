import os, time, threading, sys, json, logging, requests
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from requests.exceptions import RequestException
from dotenv import load_dotenv
from datetime import datetime, timedelta
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()

REDDIT_HEADERS = {'User-Agent': 'DiscordUpload-Reddit/2.0 by Drew'}


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
app.config['SECRET_KEY'] = os.urandom(24)

UPLOAD_FOLDER = './uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'webm', 'avi', 'mov', 'mkv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
SENT_POSTS_FILE = './sent_posts.json'

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per minute"]
)

try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
except OSError as e:
    print(f"Failed to create upload directory: {e}")
    raise


def allowed_file(filename):
    return ('.' in filename and
            filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS and
            len(secure_filename(filename)) > 0)


def validate_webhook_url(url):
    return url.startswith('https://discord.com/api/webhooks/')


def cleanup_old_uploads():
    try:
        now = time.time()
        for filename in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(file_path) and now - os.path.getctime(file_path) > 86400:
                os.unlink(file_path)
    except Exception as e:
        print(f"Error during upload cleanup: {e}")


def start_cleanup_job():
    def run_cleanup():
        while True:
            cleanup_old_uploads()
            time.sleep(86400)
    threading.Thread(target=run_cleanup, daemon=True).start()


def fetch_reddit_posts_json(subreddit_name, limit):
    """Fetch posts from Reddit's public JSON API — no credentials needed."""
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


def load_sent_posts():
    try:
        if os.path.exists(SENT_POSTS_FILE):
            with open(SENT_POSTS_FILE, 'r') as f:
                data = json.load(f)
                cutoff = datetime.now() - timedelta(days=7)
                return {k: v for k, v in data.items()
                        if datetime.fromisoformat(v) > cutoff}
        return {}
    except (json.JSONDecodeError, IOError) as e:
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
        safe_filename = secure_filename(file.filename)
        try:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
            file.save(file_path)
            with open(file_path, 'rb') as f:
                response = requests.post(webhook_url, files={'file': (safe_filename, f)})
            if response.status_code in [200, 204]:
                uploaded_files += 1
            else:
                failed_files.append(safe_filename)
        except (RequestException, Exception):
            failed_files.append(safe_filename)

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
    num_items = int(request.form['num_items'])

    if not subreddit_name:
        return jsonify({"status": "error", "message": "Subreddit name is required"}), 400
    if num_items <= 0:
        return jsonify({"status": "error", "message": "Number of posts must be greater than 0"}), 400

    try:
        sent_posts = load_sent_posts()
        sent_count = 0
        failed_items = []

        all_posts = fetch_reddit_posts_json(subreddit_name, num_items + 50)
        # Filter stickied and already-sent, then take what we need
        posts = [p for p in all_posts if not p.get('stickied') and p.get('id') not in sent_posts]
        posts = posts[:num_items]

        for post in posts:
            video_url = extract_video_url(post)
            post_url = post.get('url', '')

            embed = {
                "title": post.get('title', ''),
                "color": 0x40e0d0,
                "description": f"[View Post](https://reddit.com{post.get('permalink', '')})",
            }

            if video_url:
                embed["video"] = {"url": video_url}
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
    start_cleanup_job()
    try:
        app.run(host='0.0.0.0', port=1432, debug=False)
    except Exception as e:
        print(f"Failed to start the application: {e}")
        sys.exit(1)
    finally:
        logger.info("INFO: Shutting down...")
