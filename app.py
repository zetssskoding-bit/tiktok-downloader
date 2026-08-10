from werkzeug.utils import secure_filename
from flask import Flask, request, send_file, render_template_string
import subprocess
import tempfile
import os
import sys
import json
import shutil
import re
import base64
from urllib.parse import urlparse
from curl_cffi import requests as curl_requests
from html import unescape


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

# =========================================================
# HELPERS
# =========================================================

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
            value = f"{number / 1_000_000_000:.1f}B"
            return value.replace(".0B", "B")

        if number >= 1_000_000:
            value = f"{number / 1_000_000:.1f}M"
            return value.replace(".0M", "M")

        if number >= 1_000:
            value = f"{number / 1_000:.1f}K"
            return value.replace(".0K", "K")

        return str(number)

    except Exception:
        return "-"


def format_duration(duration):
    if not duration:
        return "-"

    try:
        duration = int(duration)
    except Exception:
        return "-"

    minutes = duration // 60
    seconds = duration % 60

    if minutes >= 60:
        hours = minutes // 60
        minutes = minutes % 60

        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes}:{seconds:02d}"


def safe_filename(text):
    text = str(text or "")

    text = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "-",
        text
    )

    text = text.strip("-")

    return text[:50] or "tiktok"


def select_thumbnail(info):
    thumbnails = info.get("thumbnails") or []

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

    static_items = []

    for item in thumbnails:

        url = item.get("url")

        if not url:
            continue

        item_id = str(
            item.get("id", "")
        ).lower()

        if "dynamic" in item_id:
            continue

        if "animated" in item_id:
            continue

        static_items.append(item)

    if static_items:
        return static_items[-1]["url"]

    return info.get("thumbnail") or ""


def get_profile_picture(video_url, info):

    uploader = info.get("uploader")

    profile_url = info.get("uploader_url")

    urls_to_try = [
        video_url,
        profile_url
    ]

    if uploader:
        urls_to_try.append(
            f"https://www.tiktok.com/@{uploader}"
        )

    patterns = [
        r'"avatarLarger"\s*:\s*"([^"]+)"',
        r'"avatarMedium"\s*:\s*"([^"]+)"',
        r'"avatarThumb"\s*:\s*"([^"]+)"',
        r'"avatar_larger".*?"url_list"\s*:\s*\[\s*"([^"]+)"',
        r'"avatar_medium".*?"url_list"\s*:\s*\[\s*"([^"]+)"',
        r'"avatar_thumb".*?"url_list"\s*:\s*\[\s*"([^"]+)"'
    ]

    for page_url in urls_to_try:

        if not page_url:
            continue

        try:

            response = curl_requests.get(
                page_url,
                impersonate="chrome",
                timeout=20,
                allow_redirects=True
            )

            if response.status_code != 200:
                continue

            html = response.text

            for pattern in patterns:

                match = re.search(
                    pattern,
                    html,
                    re.DOTALL
                )

                if not match:
                    continue

                raw_url = match.group(1)

                try:
                    avatar_url = json.loads(
                        '"' + raw_url + '"'
                    )

                except Exception:
                    avatar_url = (
                        raw_url
                        .replace(r"\u002F", "/")
                        .replace(r"\/", "/")
                        .replace(r"\u0026", "&")
                    )

                if avatar_url.startswith("http"):

                    print(
                        "Avatar ditemukan:",
                        uploader
                    )

                    return avatar_url

        except Exception as e:

            print(
                "Avatar fetch error:",
                e
            )

    return ""


def avatar_to_data_url(avatar_url):

    if not avatar_url:
        return ""

    try:

        response = curl_requests.get(
            avatar_url,
            impersonate="chrome",
            timeout=20,
            allow_redirects=True
        )

        if response.status_code != 200:
            return ""

        content_type = response.headers.get(
            "content-type",
            "image/jpeg"
        )

        if not content_type.startswith("image/"):
            return ""

        encoded = base64.b64encode(
            response.content
        ).decode("utf-8")

        return (
            f"data:{content_type};base64,{encoded}"
        )

    except Exception as e:

        print(
            "Avatar encode error:",
            e
        )

        return ""
        

def get_available_resolutions(info):
    """
    Mengambil resolusi progressive video:
    format harus memiliki VIDEO + AUDIO.

    Untuk video portrait:
    1080 x 1920 dianggap 1080p.
    """

    resolutions = set()

    formats = info.get("formats") or []

    for fmt in formats:

        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")

        if vcodec in (None, "none"):
            continue

        if acodec in (None, "none"):
            continue

        width = fmt.get("width")
        height = fmt.get("height")

        if not width or not height:
            continue

        try:
            width = int(width)
            height = int(height)

        except (TypeError, ValueError):
            continue

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
    )[:8]

def format_filesize(size):

    if not size:
        return "Ukuran tidak tersedia"

    try:
        size = int(size)
    except:
        return "Ukuran tidak tersedia"

    mb = size / (1024 * 1024)

    if mb >= 1:
        return f"~{mb:.1f} MB"

    kb = size / 1024

    return f"~{kb:.0f} KB"


def get_quality_options(info):

    options = []

    resolutions = get_available_resolutions(
        info
    )

    duration = info.get("duration") or 0

    for resolution in resolutions:

        candidates = []

        for fmt in info.get("formats") or []:

            if fmt.get("vcodec") in (
                None,
                "none"
            ):
                continue

            if fmt.get("acodec") in (
                None,
                "none"
            ):
                continue

            width = fmt.get("width")
            height = fmt.get("height")

            if not width or not height:
                continue

            try:
                current_resolution = min(
                    int(width),
                    int(height)
                )
            except:
                continue

            if current_resolution != resolution:
                continue

            candidates.append(fmt)


        if not candidates:
            continue


        candidates.sort(
            key=lambda fmt: (
                fmt.get("ext") == "mp4",
                fmt.get("tbr") or 0,
                fmt.get("filesize")
                or fmt.get("filesize_approx")
                or 0
            ),
            reverse=True
        )


        best_format = candidates[0]


        size = (
            best_format.get("filesize")
            or best_format.get(
                "filesize_approx"
            )
        )


        # Kalau TikTok tidak memberi filesize,
        # estimasi dari bitrate × durasi.
        if (
            not size
            and duration
            and best_format.get("tbr")
        ):

            bitrate_kbps = (
                best_format.get("tbr")
            )

            size = (
                bitrate_kbps
                * 1000
                * duration
                / 8
            )


        options.append({
    "resolution": resolution,
    "size": format_filesize(size),
    "badge": get_quality_badge(
        resolution
    )
})


    return options


def get_quality_badge(resolution):

    try:
        resolution = int(resolution)
    except:
        return ""

    if resolution >= 2160:
        return "4K"

    if resolution >= 1440:
        return "QHD"

    if resolution >= 1080:
        return "FHD"

    if resolution >= 720:
        return "HD"

    if resolution >= 480:
        return "SD"

    return "LOW"


def get_best_video_info(info):

    candidates = []

    for fmt in info.get("formats") or []:

        if fmt.get("vcodec") in (
            None,
            "none"
        ):
            continue

        if fmt.get("acodec") in (
            None,
            "none"
        ):
            continue

        width = fmt.get("width")
        height = fmt.get("height")

        if not width or not height:
            continue

        try:
            resolution = min(
                int(width),
                int(height)
            )
        except:
            continue

        size = (
            fmt.get("filesize")
            or fmt.get("filesize_approx")
        )

        duration = info.get("duration") or 0

        if (
            not size
            and duration
            and fmt.get("tbr")
        ):
            size = (
                fmt.get("tbr")
                * 1000
                * duration
                / 8
            )

        candidates.append({
            "resolution": resolution,
            "size_raw": size,
            "tbr": fmt.get("tbr") or 0
        })

    if not candidates:

        return {
            "size": "Ukuran tidak tersedia",
            "badge": "BEST"
        }

    candidates.sort(
        key=lambda item: (
            item["resolution"],
            item["tbr"]
        ),
        reverse=True
    )

    best = candidates[0]

    return {
        "size": format_filesize(
            best["size_raw"]
        ),
        "badge": get_quality_badge(
            best["resolution"]
        )
    }


def get_mp3_estimated_size(info):

    duration = info.get("duration")

    if not duration:
        return "Ukuran tidak tersedia"

    # Estimasi MP3 VBR kualitas tinggi
    estimated_bitrate = 245000

    size = (
        estimated_bitrate
        * float(duration)
        / 8
    )

    return format_filesize(size)
    

def get_profile_picture(video_url, info):

    uploader = info.get("uploader")

    profile_url = info.get("uploader_url")

    urls_to_try = [
        video_url,
        profile_url
    ]

    if uploader:
        urls_to_try.append(
            f"https://www.tiktok.com/@{uploader}"
        )

    patterns = [

        r'"avatarLarger"\s*:\s*"([^"]+)"',

        r'"avatarMedium"\s*:\s*"([^"]+)"',

        r'"avatarThumb"\s*:\s*"([^"]+)"',

        r'"avatar_larger".*?"url_list"\s*:\s*\[\s*"([^"]+)"',

        r'"avatar_medium".*?"url_list"\s*:\s*\[\s*"([^"]+)"',

        r'"avatar_thumb".*?"url_list"\s*:\s*\[\s*"([^"]+)"'
    ]

    for page_url in urls_to_try:

        if not page_url:
            continue

        try:

            response = curl_requests.get(
                page_url,
                impersonate="chrome",
                timeout=20,
                allow_redirects=True
            )

            if response.status_code != 200:
                continue

            html = response.text

            for pattern in patterns:

                match = re.search(
                    pattern,
                    html,
                    re.DOTALL
                )

                if not match:
                    continue

                raw_url = match.group(1)

                try:

                    avatar_url = json.loads(
                        '"' + raw_url + '"'
                    )

                except Exception:

                    avatar_url = (
                        raw_url
                        .replace(
                            r"\u002F",
                            "/"
                        )
                        .replace(
                            r"\/",
                            "/"
                        )
                        .replace(
                            r"\u0026",
                            "&"
                        )
                    )

                if avatar_url.startswith(
                    "http"
                ):

                    print(
                        "Avatar ditemukan:",
                        uploader
                    )

                    return avatar_url

        except Exception as e:

            print(
                "Avatar fetch error:",
                e
            )

    print(
        "Avatar tidak ditemukan:",
        uploader
    )

    return ""


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
            result.stderr[-3000:]
        )

    return json.loads(
        result.stdout
    )


def select_format_for_resolution(
    info,
    target_resolution
):
    """
    Cari format ID terbaik untuk resolusi tertentu.
    Prioritas:
    1. Format harus punya video + audio
    2. Resolusi harus sama dengan pilihan user
    3. MP4 diprioritaskan
    4. Bitrate terbesar diprioritaskan
    """

    candidates = []

    formats = info.get("formats") or []

    for fmt in formats:

        if fmt.get("vcodec") in (
            None,
            "none"
        ):
            continue

        if fmt.get("acodec") in (
            None,
            "none"
        ):
            continue

        width = fmt.get("width")
        height = fmt.get("height")

        if not width or not height:
            continue

        try:
            resolution = min(
                int(width),
                int(height)
            )

        except (
            TypeError,
            ValueError
        ):
            continue

        if resolution != target_resolution:
            continue

        candidates.append(fmt)

    if not candidates:
        return None

    candidates.sort(
        key=lambda fmt: (
            fmt.get("ext") == "mp4",
            fmt.get("tbr") or 0,
            fmt.get("filesize")
            or fmt.get("filesize_approx")
            or 0
        ),
        reverse=True
    )

    return str(
        candidates[0]["format_id"]
    )


# =========================================================
# STYLE
# =========================================================

STYLE = """
<style>

:root {
    --bg: #080808;
    --card: #171717;
    --card2: #202020;
    --border: #2c2c2c;
    --primary: #ff2d55;
    --primary2: #ff174c;
    --text: #ffffff;
    --muted: #999999;
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
            #292929,
            #0d0d0d 40%,
            #050505 82%
        );

    padding: 20px;
}

.container {
    width: 100%;
    max-width: 470px;

    margin: 42px auto;
}

.brand {
    text-align: center;

    margin-bottom: 30px;
}

.brand-icon {
    width: 65px;
    height: 65px;

    margin:
        0 auto 16px;

    display: flex;
    align-items: center;
    justify-content: center;

    border-radius: 21px;

    font-size: 32px;
    font-weight: bold;

    background:
        linear-gradient(
            135deg,
            #25f4ee,
            #111111 45%,
            #fe2c55
        );

    box-shadow:
        0 14px 35px
        rgba(254,44,85,.18);
}

h1 {
    margin: 0;

    font-size: 30px;
}

.subtitle {
    color: var(--muted);

    margin-top: 9px;

    font-size: 14px;
    line-height: 1.5;
}

.card {
    padding: 18px;

    border:
        1px solid
        var(--border);

    border-radius: 25px;

    background:
        rgba(23,23,23,.97);

    box-shadow:
        0 22px 70px
        rgba(0,0,0,.38);
}

.input-wrap {
    display: flex;

    gap: 8px;

    padding: 6px;

    border:
        1px solid #343434;

    border-radius: 15px;

    background: #222;
}

.url-input {
    flex: 1;
    min-width: 0;

    padding: 12px;

    border: 0;
    outline: none;

    background: transparent;

    color: white;

    font-size: 14px;
}

.url-input::placeholder {
    color: #777;
}

button {
    border: 0;

    color: white;

    cursor: pointer;

    font-weight: 700;

    transition:
        transform .15s,
        opacity .15s;
}

button:active {
    transform:
        scale(.98);
}

button:disabled {
    opacity: .6;
}

.paste-btn {
    min-width: 75px;

    padding:
        10px 13px;

    border-radius: 11px;

    background: #333;

    font-size: 13px;
}

.primary-btn {
    width: 100%;

    padding: 16px;

    margin-top: 12px;

    border-radius: 14px;

    background:
        linear-gradient(
            135deg,
            var(--primary),
            var(--primary2)
        );

    font-size: 15px;

    box-shadow:
        0 9px 24px
        rgba(254,44,85,.17);
}

.cover {
    display: block;

    width: 100%;

    aspect-ratio: 9 / 12;

    object-fit: cover;

    border-radius: 20px;

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

    gap: 12px;

    margin-top: 18px;
}

.avatar-img {
    width: 43px;
    height: 43px;

    flex-shrink: 0;

    border-radius: 50%;

    object-fit: cover;

    display: block;

    border: 1px solid #333;
}

.creator-name {
    font-weight: 700;

    font-size: 16px;
}

.username {
    margin-top: 3px;

    color:
        var(--primary);

    font-size: 13px;
}

.caption {
    margin-top: 17px;

    color: #eee;

    font-size: 15px;

    line-height: 1.55;

    word-break:
        break-word;
}

.stats {
    display: grid;

    grid-template-columns:
        repeat(4, 1fr);

    overflow: hidden;

    margin-top: 18px;

    border:
        1px solid
        #2b2b2b;

    border-radius: 16px;

    background:
        #202020;
}

.stat {
    padding:
        14px 4px;

    text-align: center;

    border-right:
        1px solid
        #2e2e2e;
}

.stat:last-child {
    border-right: 0;
}

.stat-value {
    font-size: 14px;

    font-weight: 800;
}

.stat-label {
    margin-top: 5px;

    color: #888;

    font-size: 9px;
}

.meta-box {
    margin-top: 14px;

    padding: 14px;

    border-radius: 15px;

    background:
        #202020;

    color: #aaa;

    font-size: 12px;

    line-height: 1.75;
}

.meta-box strong {
    color: #eee;
}

.section-title {
    margin:
        20px 2px 10px;

    color: #aaa;

    font-size: 13px;

    font-weight: 700;
}

.quality-grid {
    display: grid;

    grid-template-columns:
        1fr 1fr;

    gap: 10px;
}

.download-form {
    margin: 0;
}

.download-btn {
    width: 100%;

    min-height: 64px;

    padding:
        12px 8px;

    border-radius: 14px;

    font-size: 15px;
}

.best-btn {
    background: linear-gradient(
        135deg,
        #fe2c55,
        #ff174c
    ) !important;

    background-color: #fe2c55 !important;

    color: #ffffff !important;

    border: 1px solid #fe2c55 !important;

    box-shadow:
        0 7px 20px
        rgba(254,44,85,.25);

    appearance: none;
    -webkit-appearance: none;
}

.best-btn:hover,
.best-btn:focus,
.best-btn:active {
    background: linear-gradient(
        135deg,
        #fe2c55,
        #ff174c
    ) !important;

    color: #ffffff !important;
}

.quality-btn {
    background:
        #2b2b2b;

    border:
        1px solid #3b3b3b;
}

.audio-btn {
    width: 100%;

    margin-top: 10px;

    background:
        linear-gradient(
            135deg,
            #292929,
            #333333
        );

    border:
        1px solid #404040;
}

.small {
    display: block;

    margin-top: 4px;

    opacity: .7;

    font-size: 10px;

    font-weight: 400;
}

.back {
    display: block;

    margin:
        21px 0 5px;

    text-align: center;

    color: #999;

    text-decoration: none;

    font-size: 14px;
}

.footer {
    margin-top: 25px;

    text-align: center;

    color: #555;

    font-size: 11px;

    line-height: 1.55;
}

.error-card {
    text-align: center;
}

.error-icon {
    width: 55px;
    height: 55px;

    margin:
        5px auto 16px;

    display: flex;
    align-items: center;
    justify-content: center;

    border-radius: 50%;

    background:
        rgba(254,44,85,.14);

    color:
        var(--primary);

    font-size: 28px;

    font-weight: 800;
}

.error-title {
    font-size: 22px;

    font-weight: bold;
}

.error-text {
    margin-top: 10px;

    color: #999;

    line-height: 1.6;
}

.loading-overlay {
    position: fixed;

    inset: 0;

    z-index: 9999;

    display: none;

    align-items: center;
    justify-content: center;

    padding: 25px;

    background:
        rgba(0,0,0,.84);

    backdrop-filter:
        blur(8px);
}

.loading-card {
    width: 100%;
    max-width: 300px;

    padding: 29px;

    text-align: center;

    border:
        1px solid
        #343434;

    border-radius: 22px;

    background:
        #181818;
}

.spinner {
    width: 44px;
    height: 44px;

    margin:
        0 auto 17px;

    border:
        4px solid
        #333;

    border-top-color:
        var(--primary);

    border-radius: 50%;

    animation:
        spinnerRotate
        .75s
        linear
        infinite;
}

.loading-title {
    font-size: 16px;

    font-weight: bold;
}

.loading-text {
    margin-top: 7px;

    color: #888;

    font-size: 12px;

    line-height: 1.5;
}

@keyframes spinnerRotate {

    to {
        transform:
            rotate(360deg);
    }

}

@media (
    max-width: 390px
) {

    body {
        padding: 13px;
    }

    .container {
        margin:
            27px auto;
    }

    .card {
        padding: 15px;
    }

    .stats {
        grid-template-columns:
            repeat(2,1fr);
    }

    .stat:nth-child(2) {
        border-right: 0;
    }

    .stat:nth-child(-n+2) {
        border-bottom:
            1px solid
            #2e2e2e;
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


# =========================================================
# ERROR PAGE
# =========================================================

def error_page(title, text):
    return render_template_string(
        """
<!DOCTYPE html>

<html lang="id">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Error</title>

{{ style|safe }}

</head>

<body>

<div class="container">

    <div class="card error-card">

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


# =========================================================
# HOME PAGE
# =========================================================

# =========================================================
# MAIN HOMEPAGE
# =========================================================

@app.route("/")
def home():

    return """
<!DOCTYPE html>

<html lang="id">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Zetss Tools</title>

<style>

* {
    box-sizing: border-box;
    -webkit-tap-highlight-color: transparent;
}

body {
    margin: 0;
    min-height: 100vh;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

    color: white;

    background:
        radial-gradient(
            circle at 50% -10%,
            #292929,
            #0d0d0d 42%,
            #050505 80%
        );

    padding: 22px;
}

.container {
    width: 100%;
    max-width: 460px;

    margin: 45px auto;
}

.brand {
    text-align: center;

    margin-bottom: 35px;
}

.logo {
    width: 68px;
    height: 68px;

    margin:
        0 auto 16px;

    display: flex;
    align-items: center;
    justify-content: center;

    border-radius: 22px;

    font-size: 28px;
    font-weight: 900;

    background:
        linear-gradient(
            135deg,
            #25f4ee,
            #222 45%,
            #fe2c55
        );

    box-shadow:
        0 14px 40px
        rgba(254,44,85,.17);
}

h1 {
    margin: 0;

    font-size: 30px;
}

.subtitle {
    margin-top: 9px;

    color: #888;

    font-size: 14px;
    line-height: 1.5;
}

.section-title {
    margin:
        0 0 12px 3px;

    color: #888;

    font-size: 12px;
    font-weight: bold;

    text-transform: uppercase;

    letter-spacing: 1px;
}

.tools {
    display: grid;

    gap: 13px;
}

.tool-card {
    display: flex;
    align-items: center;

    gap: 15px;

    padding: 18px;

    border:
        1px solid #2d2d2d;

    border-radius: 20px;

    background:
        rgba(25,25,25,.96);

    color: white;

    text-decoration: none;

    transition:
        transform .15s,
        border-color .15s;
}

.tool-card:active {
    transform:
        scale(.98);
}

.tool-card:hover {
    border-color:
        #444;
}

.tool-icon {
    width: 53px;
    height: 53px;

    flex-shrink: 0;

    display: flex;
    align-items: center;
    justify-content: center;

    border-radius: 16px;

    font-size: 23px;
    font-weight: bold;
}

.tiktok-icon {
    background:
        linear-gradient(
            135deg,
            #25f4ee,
            #111 48%,
            #fe2c55
        );
}

.compress-icon {
    background:
        linear-gradient(
            135deg,
            #7b61ff,
            #fe2c55
        );
}

.tool-content {
    min-width: 0;
    flex: 1;
}

.tool-name {
    font-size: 16px;
    font-weight: 700;
}

.tool-desc {
    margin-top: 5px;

    color: #888;

    font-size: 12px;
    line-height: 1.45;
}

.arrow {
    color: #666;

    font-size: 22px;
}

.badge {
    display: inline-block;

    margin-top: 8px;

    padding:
        4px 8px;

    border-radius: 20px;

    font-size: 9px;
    font-weight: bold;

    color: #aaa;

    background: #292929;
}

.footer {
    margin-top: 30px;

    text-align: center;

    color: #555;

    font-size: 11px;
}

</style>

</head>


<body>

<div class="container">

    <div class="brand">

        <div class="logo">
            Z
        </div>

        <h1>
            Zetss Tools
        </h1>

        <div class="subtitle">
            Simple tools untuk download,
            convert, dan mengolah media.
        </div>

    </div>


    <div class="section-title">
        Media Tools
    </div>


    <div class="tools">


        <!-- TIKTOK DOWNLOADER -->

        <a
            class="tool-card"
            href="/tiktok-downloader"
        >

            <div
                class="
                    tool-icon
                    tiktok-icon
                "
            >
                ♪
            </div>


            <div class="tool-content">

                <div class="tool-name">
                    TikTok Downloader
                </div>

                <div class="tool-desc">
                    Preview TikTok,
                    download MP4 berbagai kualitas
                    atau convert ke MP3.
                </div>

                <span class="badge">
                    MP4 · MP3 · HD
                </span>

            </div>


            <div class="arrow">
                ›
            </div>

        </a>


        <!-- VIDEO COMPRESSOR -->

        <a
            class="tool-card"
            href="/compress-video"
        >

            <div
                class="
                    tool-icon
                    compress-icon
                "
            >
                ↓
            </div>


            <div class="tool-content">

                <div class="tool-name">
                    Video Compressor
                </div>

                <div class="tool-desc">
                    Kurangi ukuran video
                    dengan resolusi tetap
                    dipertahankan.
                </div>

                <span class="badge">
                    COMPRESS · HD
                </span>

            </div>


            <div class="arrow">
                ›
            </div>

        </a>


    </div>


    <div class="footer">
        Zetss Tools · Made for simple media tasks
    </div>

</div>

</body>

</html>
"""

@app.route("/tiktok-downloader")
def tiktok_downloader():

    return render_template_string(
        """
<!DOCTYPE html>

<html lang="id">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
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
            Preview dan download video TikTok
            dalam beberapa pilihan kualitas.
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
                    placeholder="Paste link TikTok di sini..."
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
                id="previewButton"
                class="primary-btn"
                type="submit"
            >
                Preview Video
            </button>

        </form>

    </div>


    <div class="footer">
        Gunakan hanya untuk konten yang kamu
        punya hak atau izin untuk mengunduh.
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

    }

    catch (error) {

        const input =
            document
            .getElementById(
                "urlInput"
            );

        input.focus();

        alert(
            "Browser tidak memberikan akses clipboard. Tekan lama kolom lalu pilih Paste."
        );

    }

}


document
.getElementById(
    "previewForm"
)
.addEventListener(
    "submit",
    function () {

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
            "Sedang membaca informasi video TikTok...";

        document
        .getElementById(
            "loading"
        )
        .style.display =
            "flex";

        document
        .getElementById(
            "previewButton"
        )
        .disabled = true;

    }
);

</script>

</body>

</html>
        """,
        style=STYLE,
        loading=LOADING
    )


# =========================================================
# PREVIEW
# =========================================================

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

        
        avatar_url = get_profile_picture(
            url,
            info
        )

        avatar_data = avatar_to_data_url(
            avatar_url
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
        

        avatar_url = get_profile_picture(
            url,
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


        qualities = get_quality_options(info)
    

        best_info = get_best_video_info(
            info
        )

        mp3_size = get_mp3_estimated_size(
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


        return render_template_string(
            """
<!DOCTYPE html>

<html lang="id">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
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
            alt="TikTok thumbnail"
            referrerpolicy="no-referrer"
        >

        {% else %}

        <div class="cover"></div>

        {% endif %}


        <div class="creator-row">

            {% if avatar_url %}

<img
    class="avatar"
    src="{{ avatar_url }}"
    alt="{{ uploader }}"
    referrerpolicy="no-referrer"
>

{% else %}

{% if avatar_data %}

<img
    class="avatar-img"
    src="{{ avatar_data }}"
    alt="Foto profil {{ uploader }}"
>

{% else %}

<div class="avatar">
    {{ avatar }}
</div>

{% endif %}

{% endif %}


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


        <div class="section-title">
            Pilih kualitas video
        </div>


        <div class="quality-grid">

    <!-- BEST QUALITY -->

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

        <input
            type="hidden"
            name="quality"
            value="best"
        >

        <button
            class="
                download-btn
                best-btn
            "
            type="submit"
        >

            Best

            {% if best_info.badge %}
                · {{ best_info.badge }}
            {% endif %}

            <span class="small">
                {{ best_info.size }}
            </span>

        </button>

    </form>


    <!-- AVAILABLE RESOLUTIONS -->

    {% for quality in qualities %}

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

        <input
            type="hidden"
            name="quality"
            value="{{ quality.resolution }}"
        >

        <button
            class="
                download-btn
                quality-btn
            "
            type="submit"
        >

            {{ quality.resolution }}p

            {% if quality.badge %}
                · {{ quality.badge }}
            {% endif %}

            <span class="small">
                {{ quality.size }}
            </span>

        </button>

    </form>

    {% endfor %}

</div>
        


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
                {{ mp3_size }} · Audio only
            </span>
 
       </button>

        </form>


        <a
            class="back"
            href="/tiktok-downloader"
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
.forEach(
    function(form) {

        form.addEventListener(
            "submit",
            function() {

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
                    "Server sedang memproses download kamu...";

                document
                .getElementById(
                    "loading"
                )
                .style.display =
                    "flex";


                setTimeout(
                    function() {

                        document
                        .getElementById(
                            "loading"
                        )
                        .style.display =
                            "none";

                    },
                    15000
                );

            }
        );

    }
);

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
            avatar_data=avatar_data,

            caption=caption,

            views=view_count,
            likes=like_count,
            comments=comment_count,
            shares=repost_count,
            saves=save_count,

            qualities=qualities,
            best_info=best_info,
            mp3_size=mp3_size,

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
            "PREVIEW ERROR:",
            e
        )

        return error_page(
            "Video tidak bisa diproses",
            "Video mungkin privat, sudah dihapus, dibatasi TikTok, atau sedang tidak tersedia."
        ), 500


# =========================================================
# VIDEO DOWNLOAD
# =========================================================

@app.route(
    "/download/video",
    methods=["POST"]
)
def download_video():

    url = request.form.get(
        "url",
        ""
    ).strip()


    quality = request.form.get(
        "quality",
        "best"
    )


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
            info.get("id")
            or "video"
        )


        format_selector = (
            "best[ext=mp4]/best"
        )


        if quality != "best":

            try:

                target_resolution = int(
                    quality
                )

            except (
                TypeError,
                ValueError
            ):

                shutil.rmtree(
                    folder,
                    ignore_errors=True
                )

                return error_page(
                    "Kualitas tidak valid",
                    "Resolusi video yang dipilih tidak dikenali."
                ), 400


            available_resolutions = (
                get_available_resolutions(
                    info
                )
            )


            if (
                target_resolution
                not in
                available_resolutions
            ):

                shutil.rmtree(
                    folder,
                    ignore_errors=True
                )

                return error_page(
                    "Resolusi tidak tersedia",
                    f"{target_resolution}p tidak tersedia untuk video ini."
                ), 400


            selected_format = (
                select_format_for_resolution(
                    info,
                    target_resolution
                )
            )


            if not selected_format:

                shutil.rmtree(
                    folder,
                    ignore_errors=True
                )

                return error_page(
                    "Format tidak tersedia",
                    "Server tidak menemukan format video yang cocok."
                ), 400


            format_selector = (
                selected_format
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
            format_selector,

            "--remux-video",
            "mp4",

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
                result.stderr[-3000:]
            )


        files = []


        for file in os.listdir(folder):

            if file.endswith(".part"):
                continue

            if file.endswith(".ytdl"):
                continue

            filepath = os.path.join(
                folder,
                file
            )

            if os.path.isfile(filepath):
                files.append(file)


        if not files:

            raise RuntimeError(
                "File video tidak ditemukan."
            )


        files.sort(
            key=lambda f:
                os.path.getsize(
                    os.path.join(
                        folder,
                        f
                    )
                ),
            reverse=True
        )


        filepath = os.path.join(
            folder,
            files[0]
        )


        extension = os.path.splitext(
            filepath
        )[1]


        if not extension:
            extension = ".mp4"


        if quality == "best":

            quality_name = "best"

        else:

            quality_name = (
                f"{quality}p"
            )


        response = send_file(
            filepath,

            as_attachment=True,

            download_name=(
                f"{uploader}-"
                f"{video_id}-"
                f"{quality_name}"
                f"{extension}"
            )
        )


        response.call_on_close(
            lambda:
                shutil.rmtree(
                    folder,
                    ignore_errors=True
                )
        )


        return response


    except subprocess.TimeoutExpired:

        shutil.rmtree(
            folder,
            ignore_errors=True
        )

        return error_page(
            "Download timeout",
            "Video membutuhkan waktu terlalu lama untuk diproses."
        ), 504


    except Exception as e:

        print(
            "VIDEO DOWNLOAD ERROR:",
            e
        )

        shutil.rmtree(
            folder,
            ignore_errors=True
        )

        return error_page(
            "Download gagal",
            "TikTok tidak memberikan file video untuk pilihan kualitas ini."
        ), 500


# =========================================================
# AUDIO DOWNLOAD
# =========================================================

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
            info.get("id")
            or "audio"
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
            timeout=210
        )


        if result.returncode != 0:

            raise RuntimeError(
                result.stderr[-3000:]
            )


        files = [
            file
            for file
            in os.listdir(folder)

            if file
            .lower()
            .endswith(
                ".mp3"
            )
        ]


        if not files:

            raise RuntimeError(
                "MP3 tidak ditemukan."
            )


        filepath = os.path.join(
            folder,
            files[0]
        )


        response = send_file(
            filepath,

            as_attachment=True,

            download_name=(
                f"{uploader}-"
                f"{video_id}"
                ".mp3"
            )
        )


        response.call_on_close(
            lambda:
                shutil.rmtree(
                    folder,
                    ignore_errors=True
                )
        )


        return response


    except subprocess.TimeoutExpired:

        shutil.rmtree(
            folder,
            ignore_errors=True
        )

        return error_page(
            "Audio timeout",
            "Audio membutuhkan waktu terlalu lama untuk diproses."
        ), 504


    except Exception as e:

        print(
            "AUDIO DOWNLOAD ERROR:",
            e
        )

        shutil.rmtree(
            folder,
            ignore_errors=True
        )

        return error_page(
            "MP3 gagal dibuat",
            "Server tidak berhasil mengubah audio TikTok menjadi MP3."
        ), 500
        

# =========================================================
# VIDEO COMPRESSOR
# =========================================================

ALLOWED_VIDEO_EXTENSIONS = {
    "mp4",
    "mov",
    "mkv",
    "webm",
    "avi",
    "m4v"
}


def allowed_video(filename):

    if "." not in filename:
        return False

    extension = (
        filename
        .rsplit(".", 1)[1]
        .lower()
    )

    return (
        extension
        in ALLOWED_VIDEO_EXTENSIONS
    )


@app.route(
    "/compress-video",
    methods=["GET", "POST"]
)
def compress_video():

    if request.method == "GET":

        return render_template_string(
            """
<!DOCTYPE html>

<html lang="id">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="
        width=device-width,
        initial-scale=1.0
    "
>

<title>Video Compressor</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    min-height: 100vh;

    font-family:
        Arial,
        sans-serif;

    color: white;

    background:
        radial-gradient(
            circle at top,
            #262626,
            #0d0d0d 45%,
            #050505
        );

    padding: 20px;
}

.container {
    width: 100%;
    max-width: 460px;

    margin: 45px auto;
}

.header {
    text-align: center;
    margin-bottom: 25px;
}

.icon {
    width: 65px;
    height: 65px;

    margin: 0 auto 15px;

    display: flex;
    align-items: center;
    justify-content: center;

    border-radius: 20px;

    font-size: 30px;

    background:
        linear-gradient(
            135deg,
            #25f4ee,
            #fe2c55
        );
}

h1 {
    margin: 0;
    font-size: 29px;
}

.subtitle {
    margin-top: 9px;

    color: #999;

    font-size: 14px;
    line-height: 1.5;
}

.card {
    padding: 20px;

    border-radius: 24px;

    border:
        1px solid #2b2b2b;

    background: #171717;
}

.upload-box {
    position: relative;

    padding: 28px 15px;

    text-align: center;

    border:
        1px dashed #555;

    border-radius: 17px;

    background: #202020;
}

.upload-box input {
    position: absolute;

    inset: 0;

    width: 100%;
    height: 100%;

    opacity: 0;

    cursor: pointer;
}

.upload-title {
    font-weight: bold;
}

.upload-info {
    margin-top: 7px;

    color: #888;

    font-size: 12px;
}

.file-selected {
    display: none;

    margin-top: 12px;
    padding: 12px;

    border-radius: 13px;

    background:
        rgba(
            37,
            244,
            238,
            .08
        );

    color: #25f4ee;

    font-size: 12px;

    word-break: break-word;
}

.label {
    display: block;

    margin:
        20px 0 10px;

    color: #aaa;

    font-size: 13px;
    font-weight: bold;
}

.option {
    display: block;

    margin-bottom: 9px;
}

.option input {
    display: none;
}

.option-content {
    display: block;

    padding: 14px;

    border:
        1px solid #333;

    border-radius: 14px;

    background: #222;

    cursor: pointer;
}

.option input:checked
+ .option-content {

    border-color: #fe2c55;

    background:
        rgba(
            254,
            44,
            85,
            .09
        );
}

.option-title {
    font-weight: bold;
}

.option-desc {
    margin-top: 4px;

    color: #888;

    font-size: 11px;
}

.recommended {
    color: #fe2c55;

    font-size: 10px;

    margin-left: 5px;
}

.compress-btn {
    width: 100%;

    margin-top: 15px;
    padding: 16px;

    border: 0;
    border-radius: 14px;

    color: white;

    font-weight: bold;
    font-size: 15px;

    background:
        linear-gradient(
            135deg,
            #fe2c55,
            #ff174c
        );

    cursor: pointer;
}

.note {
    margin-top: 15px;

    text-align: center;

    color: #666;

    font-size: 11px;
    line-height: 1.5;
}

.back {
    display: block;

    margin-top: 20px;

    text-align: center;

    color: #999;

    text-decoration: none;

    font-size: 13px;
}

.loading {
    position: fixed;

    inset: 0;

    display: none;

    align-items: center;
    justify-content: center;

    background:
        rgba(
            0,
            0,
            0,
            .85
        );

    z-index: 999;
}

.loading-card {
    width: 80%;
    max-width: 300px;

    padding: 28px;

    text-align: center;

    border-radius: 20px;

    background: #181818;

    border:
        1px solid #333;
}

.spinner {
    width: 42px;
    height: 42px;

    margin:
        0 auto 15px;

    border:
        4px solid #333;

    border-top-color: #fe2c55;

    border-radius: 50%;

    animation:
        spin .8s
        linear infinite;
}

@keyframes spin {

    to {
        transform:
            rotate(360deg);
    }

}

</style>

</head>


<body>

<div class="container">

    <div class="header">

        <div class="icon">
            ↓
        </div>

        <h1>
            Video Compressor
        </h1>

        <div class="subtitle">
            Kurangi ukuran video tanpa
            menurunkan resolusi aslinya.
        </div>

    </div>


    <div class="card">

        <form
            id="compressForm"
            action="/compress-video"
            method="POST"
            enctype="multipart/form-data"
        >

            <div class="upload-box">

                <input
                    id="videoInput"
                    type="file"
                    name="video"
                    accept="video/*"
                    required
                >

                <div class="upload-title">
                    Pilih Video
                </div>

                <div class="upload-info">
                    MP4, MOV, MKV, WEBM · Maks. 100 MB
                </div>

            </div>


            <div
                id="fileSelected"
                class="file-selected"
            >
            </div>


            <span class="label">
                Pilih tingkat kompresi
            </span>


            <label class="option">

                <input
                    type="radio"
                    name="mode"
                    value="high"
                >

                <span class="option-content">

                    <span class="option-title">
                        High Quality
                    </span>

                    <div class="option-desc">
                        Kualitas sangat dekat dengan video asli.
                    </div>

                </span>

            </label>


            <label class="option">

                <input
                    type="radio"
                    name="mode"
                    value="balanced"
                    checked
                >

                <span class="option-content">

                    <span class="option-title">
                        Balanced

                        <span class="recommended">
                            RECOMMENDED
                        </span>

                    </span>

                    <div class="option-desc">
                        Keseimbangan kualitas dan ukuran file.
                    </div>

                </span>

            </label>


            <label class="option">

                <input
                    type="radio"
                    name="mode"
                    value="maximum"
                >

                <span class="option-content">

                    <span class="option-title">
                        Maximum Compression
                    </span>

                    <div class="option-desc">
                        Ukuran lebih kecil dengan kompresi lebih kuat.
                    </div>

                </span>

            </label>


            <button
                class="compress-btn"
                type="submit"
            >
                Compress Video
            </button>

        </form>


        <div class="note">
            Resolusi asli dipertahankan.
            Kompresi dapat sedikit mengurangi
            kualitas visual.
        </div>

    </div>


    <a
        class="back"
        href="/"
    >
        ← Kembali ke Home
    </a>

</div>


<div
    id="loading"
    class="loading"
>

    <div class="loading-card">

        <div class="spinner"></div>

        <strong>
            Mengompres video...
        </strong>

        <div
            style="
                color:#888;
                font-size:12px;
                margin-top:8px;
            "
        >
            Video besar mungkin membutuhkan
            beberapa menit.
        </div>

    </div>

</div>


<script>

const videoInput =
    document.getElementById(
        "videoInput"
    );

const fileSelected =
    document.getElementById(
        "fileSelected"
    );


videoInput.addEventListener(
    "change",
    function () {

        if (!this.files.length) {
            return;
        }

        const file =
            this.files[0];

        const mb =
            (
                file.size
                / 1024
                / 1024
            ).toFixed(1);

        fileSelected.innerText =
            "✓ "
            + file.name
            + " · "
            + mb
            + " MB";

        fileSelected.style.display =
            "block";

    }
);


document
.getElementById(
    "compressForm"
)
.addEventListener(
    "submit",
    function () {

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
            """
        )


    # =====================
    # POST / COMPRESS
    # =====================

    if "video" not in request.files:

        return error_page(
            "Video tidak ditemukan",
            "Pilih video yang ingin dikompres."
        ), 400


    video = request.files["video"]


    if not video.filename:

        return error_page(
            "Video tidak ditemukan",
            "Pilih video yang ingin dikompres."
        ), 400


    if not allowed_video(
        video.filename
    ):

        return error_page(
            "Format tidak didukung",
            "Gunakan MP4, MOV, MKV, WEBM, AVI, atau M4V."
        ), 400


    mode = request.form.get(
        "mode",
        "balanced"
    )


    crf_values = {
        "high": "20",
        "balanced": "23",
        "maximum": "28"
    }


    crf = crf_values.get(
        mode,
        "23"
    )


    folder = tempfile.mkdtemp()


    try:

        original_name = (
            secure_filename(
                video.filename
            )
        )


        input_path = os.path.join(
            folder,
            original_name
        )


        output_path = os.path.join(
            folder,
            "compressed.mp4"
        )


        video.save(
            input_path
        )


        original_size = os.path.getsize(
            input_path
        )


        command = [
            "ffmpeg",
            "-y",

            "-i",
            input_path,

            "-map",
            "0:v:0",

            "-map",
            "0:a?",

            "-c:v",
            "libx264",

            "-preset",
            "medium",

            "-crf",
            crf,

            "-c:a",
            "aac",

            "-b:a",
            "128k",

            "-movflags",
            "+faststart",

            output_path
        ]


        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600
        )


        if (
            result.returncode != 0
            or not os.path.exists(
                output_path
            )
        ):

            print(
                "FFmpeg compressor error:",
                result.stderr[-3000:]
            )

            raise RuntimeError(
                "FFmpeg gagal memproses video."
            )


        compressed_size = (
            os.path.getsize(
                output_path
            )
        )


        print(
            "Video compressed:",
            original_size,
            "->",
            compressed_size
        )


        base_name = os.path.splitext(
            original_name
        )[0]


        download_name = (
            f"{base_name}-compressed.mp4"
        )


        response = send_file(
            output_path,

            as_attachment=True,

            download_name=download_name,

            mimetype="video/mp4"
        )


        response.call_on_close(
            lambda:
            shutil.rmtree(
                folder,
                ignore_errors=True
            )
        )


        return response


    except subprocess.TimeoutExpired:

        shutil.rmtree(
            folder,
            ignore_errors=True
        )

        return error_page(
            "Proses terlalu lama",
            "Video membutuhkan waktu terlalu lama untuk dikompres."
        ), 504


    except Exception as e:

        print(
            "Compressor error:",
            e
        )

        shutil.rmtree(
            folder,
            ignore_errors=True
        )

        return error_page(
            "Kompresi gagal",
            "Video tidak berhasil diproses."
        ), 500


# =========================================================
# RUN APP
# =========================================================

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
