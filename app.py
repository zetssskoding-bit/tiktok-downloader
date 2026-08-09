from flask import Flask, request, send_file, render_template_string
import subprocess
import tempfile
import os
import sys
import json
import shutil
import re
from urllib.parse import urlparse

app = Flask(__name__)


# =========================
# HELPERS
# =========================

def valid_tiktok_url(url):
    try:
        host = urlparse(url).hostname

        if not host:
            return False

        host = host.lower()

        return (
            host == "tiktok.com"
            or host.endswith(".tiktok.com")
        )

    except Exception:
        return False


def format_number(number):
    if number is None:
        return "-"

    try:
        number = int(number)

        if number >= 1_000_000_000:
            return f"{number / 1_000_000_000:.1f}B".replace(".0B", "B")

        if number >= 1_000_000:
            return f"{number / 1_000_000:.1f}M".replace(".0M", "M")

        if number >= 1_000:
            return f"{number / 1_000:.1f}K".replace(".0K", "K")

        return str(number)

    except Exception:
        return "-"


def format_duration(duration):
    if not duration:
        return "-"

    duration = int(duration)

    minutes = duration // 60
    seconds = duration % 60

    if minutes >= 60:
        hours = minutes // 60
        minutes = minutes % 60

        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes}:{seconds:02d}"
    

def get_available_resolutions(info):

    resolutions = set()

    formats = info.get("formats") or []

    for fmt in formats:

        # Harus ada video
        if fmt.get("vcodec") in (None, "none"):
            continue

        # Hindari format video-only kalau TikTok
        # memang memberi info audio codec
        if fmt.get("acodec") == "none":
            continue

        width = fmt.get("width")
        height = fmt.get("height")

        if not width or not height:
            continue

        try:
            width = int(width)
            height = int(height)
        except:
            continue

        # Untuk video portrait:
        # 1080 x 1920 -> 1080p
        resolution = min(
            width,
            height
        )

        if resolution >= 240:
            resolutions.add(
                resolution
            )

    return sorted(
        resolutions,
        reverse=True
    )[:6]


def safe_filename(text):
    text = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "-",
        text
    )

    text = text.strip("-")

    return text[:45] or "tiktok"


def select_thumbnail(info):

    thumbnails = info.get("thumbnails") or []

    # Prioritas cover statis TikTok.
    priorities = [
        "cover",
        "origin_cover",
        "originCover",
        "thumbnail"
    ]

    for wanted_id in priorities:

        for item in thumbnails:

            if (
                item.get("id") == wanted_id
                and item.get("url")
            ):
                return item["url"]

    # Hindari dynamic/animated kalau memungkinkan.
    static_items = [
        item for item in thumbnails
        if item.get("url")
        and "dynamic" not in str(
            item.get("id", "")
        ).lower()
        and "animated" not in str(
            item.get("id", "")
        ).lower()
    ]

    if static_items:
        return static_items[-1]["url"]

    return info.get("thumbnail") or ""


def extract_info(url):

    command = [
        sys.executable,
        "-m",
        "yt_dlp",

        "--dump-single-json",
        "--skip-download",
        "--no-playlist",

        "--impersonate",
        "chrome",

        url
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=70
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr[-2000:]
        )

    return json.loads(
        result.stdout
    )


# =========================
# STYLE
# =========================

STYLE = """
<style>

:root {
    --bg: #090909;
    --card: #171717;
    --soft: #222;
    --border: #2b2b2b;
    --primary: #ff2d55;
    --primary2: #ff174c;
    --text: #ffffff;
    --muted: #999;
}

* {
    box-sizing: border-box;
    -webkit-tap-highlight-color: transparent;
}

body {
    margin: 0;
    min-height: 100vh;
    color: var(--text);
    font-family:
        Arial,
        Helvetica,
        sans-serif;

    background:
        radial-gradient(
            circle at 50% -10%,
            #262626,
            #0d0d0d 38%,
            #050505 80%
        );

    padding: 22px;
}

.container {
    width: 100%;
    max-width: 460px;
    margin: 42px auto;
}

.brand {
    text-align: center;
    margin-bottom: 30px;
}

.brand-icon {
    width: 62px;
    height: 62px;

    display: flex;
    align-items: center;
    justify-content: center;

    margin: 0 auto 15px;

    border-radius: 20px;

    font-size: 31px;
    font-weight: bold;

    background:
        linear-gradient(
            135deg,
            #25f4ee,
            #111 45%,
            #fe2c55
        );

    box-shadow:
        0 13px 35px
        rgba(254,44,85,.18);
}

h1 {
    font-size: 29px;
    margin: 0;
}

.subtitle {
    color: var(--muted);
    font-size: 14px;
    line-height: 1.55;
    margin-top: 9px;
}

.card {
    padding: 18px;
    border: 1px solid var(--border);
    border-radius: 25px;

    background:
        rgba(24,24,24,.96);

    box-shadow:
        0 22px 70px
        rgba(0,0,0,.35);
}

.input-wrap {
    display: flex;
    gap: 8px;

    padding: 6px;

    background: #222;
    border: 1px solid #333;
    border-radius: 15px;
}

.url-input {
    min-width: 0;
    flex: 1;

    background: transparent;
    border: 0;
    outline: none;

    padding: 12px;

    color: white;
    font-size: 14px;
}

.paste-btn {
    width: auto;
    min-width: 76px;

    margin: 0;
    padding: 11px 12px;

    background: #333;
    border-radius: 11px;

    font-size: 13px;
}

button {
    border: 0;
    cursor: pointer;

    color: white;

    font-weight: 700;
    font-size: 15px;

    transition: .15s;
}

button:active {
    transform: scale(.98);
}

.primary-btn {
    width: 100%;
    margin-top: 12px;
    padding: 16px;

    border-radius: 14px;

    background:
        linear-gradient(
            135deg,
            var(--primary),
            var(--primary2)
        );

    box-shadow:
        0 9px 24px
        rgba(254,44,85,.18);
}

.cover {
    width: 100%;
    aspect-ratio: 9 / 12;

    object-fit: cover;

    display: block;

    border-radius: 18px;

    background:
        linear-gradient(
            135deg,
            #181818,
            #080808
        );
}

.creator-row {
    display: flex;
    align-items: center;
    gap: 11px;

    margin-top: 17px;
}

.avatar {
    width: 43px;
    height: 43px;

    flex-shrink: 0;

    display: flex;
    align-items: center;
    justify-content: center;

    border-radius: 50%;

    font-weight: 800;
    font-size: 18px;

    background:
        linear-gradient(
            135deg,
            #25f4ee,
            #fe2c55
        );

    color: white;
}

.creator-name {
    font-weight: 700;
    color: white;
}

.username {
    margin-top: 2px;
    color: var(--primary);
    font-size: 13px;
}

.caption {
    margin-top: 15px;

    color: #eee;
    font-size: 15px;
    line-height: 1.55;

    word-break: break-word;
}

.stats {
    display: grid;
    grid-template-columns:
        repeat(4, 1fr);

    margin-top: 18px;
    overflow: hidden;

    border: 1px solid #292929;
    border-radius: 15px;

    background: #202020;
}

.stat {
    padding: 13px 4px;
    text-align: center;

    border-right:
        1px solid #2d2d2d;
}

.stat:last-child {
    border-right: none;
}

.stat-value {
    font-size: 14px;
    font-weight: 800;
}

.stat-label {
    font-size: 10px;
    color: #888;
    margin-top: 5px;
}

.meta-box {
    margin-top: 13px;
    padding: 13px;

    border-radius: 14px;

    background: #202020;

    font-size: 12px;
    line-height: 1.6;

    color: #aaa;
}

.meta-box strong {
    color: #eee;
}

.download-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;

    gap: 10px;

    margin-top: 14px;
}

.download-btn {
    width: 100%;
    padding: 15px 8px;

    border-radius: 14px;
}

.video-btn {
    background:
        linear-gradient(
            135deg,
            #fe2c55,
            #ff174c
        );
}

.audio-btn {
    background:
        #2b2b2b;

    border:
        1px solid #3c3c3c;
}

.small {
    display: block;

    margin-top: 3px;

    font-size: 10px;
    font-weight: 400;

    opacity: .75;
}

.back {
    display: block;

    text-align: center;
    text-decoration: none;

    color: #999;

    margin: 20px 0 5px;

    font-size: 14px;
}

.footer {
    margin-top: 24px;

    text-align: center;

    font-size: 11px;
    line-height: 1.5;

    color: #555;
}

.error-card {
    text-align: center;
}

.error-icon {
    font-size: 42px;
}

.error-title {
    font-size: 22px;
    margin: 12px 0 8px;
}

.error-text {
    color: #999;
    line-height: 1.6;
}

.loading-overlay {
    position: fixed;
    inset: 0;

    display: none;

    align-items: center;
    justify-content: center;

    background:
        rgba(0,0,0,.82);

    backdrop-filter:
        blur(7px);

    z-index: 999;
}

.loading-card {
    width: 80%;
    max-width: 300px;

    text-align: center;

    padding: 28px;

    border:
        1px solid #333;

    border-radius: 22px;

    background: #181818;
}

.spinner {
    width: 42px;
    height: 42px;

    margin:
        0 auto 16px;

    border:
        4px solid #333;

    border-top-color:
        var(--primary);

    border-radius: 50%;

    animation:
        rotate .75s
        linear infinite;
}

.loading-title {
    font-weight: bold;
}

.loading-text {
    margin-top: 7px;

    color: #888;
    font-size: 12px;
}

@keyframes rotate {
    to {
        transform:
            rotate(360deg);
    }
}

@media (
    max-width: 390px
) {

    body {
        padding: 14px;
    }

    .container {
        margin: 28px auto;
    }

    .card {
        padding: 15px;
    }

    .stats {
        grid-template-columns:
            repeat(2, 1fr);
    }

    .stat:nth-child(2) {
        border-right: 0;
    }

    .stat:nth-child(-n+2) {
        border-bottom:
            1px solid #2d2d2d;
    }
}

</style>
"""


LOADING = """
<div
    id="loading"
    class="loading-overlay"
>

    <div class="loading-card">

        <div class="spinner"></div>

        <div
            id="loadingTitle"
            class="loading-title"
        >
            Memproses...
        </div>

        <div
            id="loadingText"
            class="loading-text"
        >
            Sebentar ya.
        </div>

    </div>

</div>
"""


# =========================
# HOME
# =========================

@app.route("/")
def home():

    return render_template_string("""
<!DOCTYPE html>

<html lang="id">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
    initial-scale=1.0"
>

<title>TikTok Downloader</title>

{{ style|safe }}

</head>


<body>

<div class="container">

    <div class="brand">

        <div class="brand-icon">
            ♪
        </div>

        <h1>
            TikTok Downloader
        </h1>

        <div class="subtitle">
            Preview video dan download
            TikTok dengan cepat.
        </div>

    </div>


    <div class="card">

        <form
            id="previewForm"
            action="/preview"
            method="POST"
        >

            <div class="input-wrap">

                <input
                    id="urlInput"
                    class="url-input"
                    type="url"
                    name="url"
                    placeholder="Paste link TikTok..."
                    required
                >

                <button
                    type="button"
                    class="paste-btn"
                    onclick="pasteLink()"
                >
                    Paste
                </button>

            </div>


            <button
                class="primary-btn"
                type="submit"
            >
                Preview Video
            </button>

        </form>

    </div>


    <div class="footer">
        Gunakan hanya untuk konten
        yang kamu punya hak atau izin
        untuk mengunduh.
    </div>

</div>


{{ loading|safe }}


<script>

async function pasteLink() {

    try {

        const text =
            await navigator
            .clipboard
            .readText();

        document
            .getElementById(
                "urlInput"
            )
            .value = text;

    } catch (error) {

        const input =
            document.getElementById(
                "urlInput"
            );

        input.focus();

        alert(
            "Browser tidak mengizinkan akses clipboard. Tekan lama kolom lalu pilih Paste."
        );

    }

}


document
.getElementById(
    "previewForm"
)
.addEventListener(
    "submit",
    () => {

        document
        .getElementById(
            "loadingTitle"
        )
        .innerText =
            "Mengambil video";

        document
        .getElementById(
            "loadingText"
        )
        .innerText =
            "Sedang membaca informasi TikTok...";

        document
        .getElementById(
            "loading"
        )
        .style.display =
            "flex";

    }
);

</script>

</body>

</html>
""",

    style=STYLE,
    loading=LOADING

    )


# =========================
# PREVIEW
# =========================

@app.route(
    "/preview",
    methods=["POST"]
)
def preview():

    url = request.form.get(
        "url",
        ""
    ).strip()


    if not valid_tiktok_url(url):

        return error_page(
            "Link tidak valid",
            "Masukkan link TikTok yang benar."
        ), 400


    try:

        info = extract_info(url)


        uploader = (
            info.get("uploader")
            or info.get("creator")
            or "TikTok User"
        )


        creator_name = (
            info.get("channel")
            or info.get("creator")
            or uploader
        )


        caption = (
            info.get("description")
            or info.get("title")
            or "Video TikTok"
        )


        thumbnail = select_thumbnail(
            info
        )


        duration = format_duration(
            info.get("duration")
        )


        view_count = format_number(
            info.get("view_count")
        )


        like_count = format_number(
            info.get("like_count")
        )


        comment_count = format_number(
            info.get("comment_count")
        )


        repost_count = format_number(
            info.get("repost_count")
        )


        save_count = format_number(
            info.get("save_count")
        )
        

        qualities = get_available_resolutions(
    info
        )


        track = (
            info.get("track")
            or "Original sound"
        )


        artist = (
            info.get("artist")
            or uploader
        )


        avatar_letter = (
            uploader[0].upper()
            if uploader
            else "T"
        )


        return render_template_string("""
<!DOCTYPE html>

<html lang="id">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
    initial-scale=1.0"
>

<title>Preview TikTok</title>

{{ style|safe }}

</head>


<body>

<div class="container">

    <div class="card">

        {% if thumbnail %}

        <img
            class="cover"
            src="{{ thumbnail }}"
            alt="TikTok cover"
            referrerpolicy="no-referrer"
        >

        {% else %}

        <div class="cover"></div>

        {% endif %}


        <div class="creator-row">

            <div class="avatar">
                {{ avatar }}
            </div>

            <div>

                <div class="creator-name">
                    {{ creator }}
                </div>

                <div class="username">
                    @{{ uploader }}
                </div>

            </div>

        </div>


        <div class="caption">
            {{ caption }}
        </div>


        <div class="stats">

            <div class="stat">

                <div class="stat-value">
                    {{ views }}
                </div>

                <div class="stat-label">
                    VIEWS
                </div>

            </div>


            <div class="stat">

                <div class="stat-value">
                    {{ likes }}
                </div>

                <div class="stat-label">
                    LIKES
                </div>

            </div>


            <div class="stat">

                <div class="stat-value">
                    {{ comments }}
                </div>

                <div class="stat-label">
                    COMMENTS
                </div>

            </div>


            <div class="stat">

                <div class="stat-value">
                    {{ shares }}
                </div>

                <div class="stat-label">
                    SHARES
                </div>

            </div>

        </div>


        <div class="meta-box">

            <div>
                <strong>Durasi:</strong>
                {{ duration }}
            </div>

            <div>
                <strong>Sound:</strong>
                {{ track }}
            </div>

            <div>
                <strong>Artist:</strong>
                {{ artist }}
            </div>

            <div>
                <strong>Disimpan:</strong>
                {{ saves }}
            </div>

        </div>


        <div class="download-grid">


            <form
                class="download-form"
                action="/download/video"
                method="POST"
            >

                <input
                    type="hidden"
                    name="url"
                    value="{{ url }}"
                >

                <button
                    class="
                    download-btn
                    video-btn
                    "
                    type="submit"
                >
                    Download MP4

                    <span class="small">
                        Video
                    </span>

                </button>

            </form>


            <form
                class="download-form"
                action="/download/audio"
                method="POST"
            >

                <input
                    type="hidden"
                    name="url"
                    value="{{ url }}"
                >

                <button
                    class="
                    download-btn
                    audio-btn
                    "
                    type="submit"
                >
                    Download MP3

                    <span class="small">
                        Audio
                    </span>

                </button>

            </form>


        </div>


        <a
            class="back"
            href="/"
        >
            ← Masukkan link lain
        </a>

    </div>

</div>


{{ loading|safe }}


<script>

document
.querySelectorAll(
    ".download-form"
)
.forEach(form => {

    form.addEventListener(
        "submit",
        () => {

            document
            .getElementById(
                "loadingTitle"
            )
            .innerText =
                "Menyiapkan file";

            document
            .getElementById(
                "loadingText"
            )
            .innerText =
                "Download akan dimulai setelah file siap.";

            document
            .getElementById(
                "loading"
            )
            .style.display =
                "flex";

        }
    );

});

</script>

</body>

</html>
""",

        style=STYLE,
        loading=LOADING,

        thumbnail=thumbnail,

        creator=creator_name,
        uploader=uploader,
        avatar=avatar_letter,

        caption=caption,

        views=view_count,
        likes=like_count,
        comments=comment_count,
        shares=repost_count,
        saves=save_count,

        qualities=qualities,

        duration=duration,

        track=track,
        artist=artist,

        url=url

        )


    except subprocess.TimeoutExpired:

        return error_page(
            "Server terlalu lama",
            "TikTok membutuhkan waktu terlalu lama untuk merespons."
        ), 504


    except Exception as e:

        print(
            "Preview error:",
            e
        )

        return error_page(
            "Video tidak bisa diproses",
            "Video mungkin privat, sudah dihapus, dibatasi TikTok, atau link sedang tidak tersedia."
        ), 500


# =========================
# VIDEO DOWNLOAD
# =========================

@app.route(
    "/download/video",
    methods=["POST"]
)
def download_video():

    url = request.form.get(
        "url",
        ""
    ).strip()


    if not valid_tiktok_url(url):

        return error_page(
            "Link tidak valid",
            "Masukkan link TikTok yang benar."
        ), 400


    folder = tempfile.mkdtemp()


    try:

        info = extract_info(url)

        uploader = safe_filename(
            info.get("uploader")
            or "tiktok"
        )


        video_id = safe_filename(
            str(
                info.get("id")
                or "video"
            )
        )


        output = os.path.join(
            folder,
            "%(id)s.%(ext)s"
        )


        command = [

            sys.executable,
            "-m",
            "yt_dlp",

            "--no-playlist",

            "--impersonate",
            "chrome",

            "-f",
            "best[ext=mp4]/best",

            "-o",
            output,

            url
        ]


        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=150
        )


        if result.returncode != 0:

            raise RuntimeError(
                result.stderr[-2000:]
            )


        files = [
            f for f
            in os.listdir(folder)

            if not f.endswith(
                ".part"
            )
        ]


        if not files:

            raise RuntimeError(
                "File video tidak ditemukan"
            )


        filepath = os.path.join(
            folder,
            files[0]
        )


        ext = os.path.splitext(
            filepath
        )[1]


        return send_file(
            filepath,

            as_attachment=True,

            download_name=(
                f"{uploader}-"
                f"{video_id}"
                f"{ext}"
            )
        )


    except subprocess.TimeoutExpired:

        return error_page(
            "Download timeout",
            "Video membutuhkan waktu terlalu lama untuk diproses."
        ), 504


    except Exception as e:

        print(
            "Video error:",
            e
        )

        return error_page(
            "Download gagal",
            "TikTok tidak memberikan file video untuk link ini."
        ), 500


# =========================
# AUDIO DOWNLOAD
# =========================

@app.route(
    "/download/audio",
    methods=["POST"]
)
def download_audio():

    url = request.form.get(
        "url",
        ""
    ).strip()


    if not valid_tiktok_url(url):

        return error_page(
            "Link tidak valid",
            "Masukkan link TikTok yang benar."
        ), 400


    folder = tempfile.mkdtemp()


    try:

        info = extract_info(url)

        uploader = safe_filename(
            info.get("uploader")
            or "tiktok"
        )


        video_id = safe_filename(
            str(
                info.get("id")
                or "audio"
            )
        )


        output = os.path.join(
            folder,
            "%(id)s.%(ext)s"
        )


        command = [

            sys.executable,
            "-m",
            "yt_dlp",

            "--no-playlist",

            "--impersonate",
            "chrome",

            "-x",

            "--audio-format",
            "mp3",

            "--audio-quality",
            "0",

            "-o",
            output,

            url
        ]


        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180
        )


        if result.returncode != 0:

            raise RuntimeError(
                result.stderr[-2500:]
            )


        files = [
            f for f
            in os.listdir(folder)

            if f.lower().endswith(
                ".mp3"
            )
        ]


        if not files:

            raise RuntimeError(
                "MP3 tidak ditemukan. Pastikan FFmpeg terpasang."
            )


        filepath = os.path.join(
            folder,
            files[0]
        )


        return send_file(
            filepath,

            as_attachment=True,

            download_name=(
                f"{uploader}-"
                f"{video_id}"
                ".mp3"
            )
        )


    except subprocess.TimeoutExpired:

        return error_page(
            "Audio timeout",
            "Audio membutuhkan waktu terlalu lama untuk diproses."
        ), 504


    except Exception as e:

        print(
            "Audio error:",
            e
        )

        return error_page(
            "MP3 gagal dibuat",
            "Server tidak berhasil mengubah audio menjadi MP3."
        ), 500


# =========================
# ERROR PAGE
# =========================

def error_page(title, text):

    return render_template_string("""
<!DOCTYPE html>

<html lang="id">

<head>

<meta
    name="viewport"
    content="width=device-width,
    initial-scale=1.0"
>

<title>Error</title>

{{ style|safe }}

</head>


<body>

<div class="container">

    <div class="
        card
        error-card
    ">

        <div class="error-icon">
            !
        </div>

        <div class="error-title">
            {{ title }}
        </div>

        <div class="error-text">
            {{ text }}
        </div>

        <a
            class="back"
            href="/"
        >
            ← Kembali
        </a>

    </div>

</div>

</body>

</html>
""",

    style=STYLE,
    title=title,
    text=text

    )


# =========================
# RUN
# =========================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )


    app.run(
        host="0.0.0.0",
        port=port
    )
