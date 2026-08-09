from flask import Flask, request, send_file, render_template_string
import subprocess
import tempfile
import os
import sys
import json
import shutil
from urllib.parse import urlparse

app = Flask(__name__)


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


BASE_STYLE = """
<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    min-height: 100vh;
    background:
        radial-gradient(circle at top, #252525 0%, #111 45%, #080808 100%);
    color: white;
    font-family: Arial, sans-serif;
    padding: 22px;
}

.wrapper {
    width: 100%;
    max-width: 460px;
    margin: 60px auto;
}

.logo {
    text-align: center;
    font-size: 46px;
    margin-bottom: 5px;
}

h1 {
    text-align: center;
    font-size: 32px;
    margin: 5px 0 10px;
}

.subtitle {
    text-align: center;
    color: #999;
    line-height: 1.5;
    margin-bottom: 30px;
}

.card {
    background: rgba(28, 28, 28, .95);
    border: 1px solid #2d2d2d;
    border-radius: 22px;
    padding: 22px;
}

input {
    width: 100%;
    padding: 17px;
    border-radius: 13px;
    border: 1px solid #393939;
    background: #242424;
    color: white;
    font-size: 15px;
    outline: none;
}

input:focus {
    border-color: #fe2c55;
}

button {
    width: 100%;
    margin-top: 12px;
    padding: 17px;
    border: none;
    border-radius: 13px;
    background: #fe2c55;
    color: white;
    font-size: 16px;
    font-weight: bold;
    cursor: pointer;
}

button:active {
    transform: scale(.98);
}

.thumbnail {
    width: 100%;
    max-height: 500px;
    object-fit: cover;
    border-radius: 17px;
    background: #222;
}

.info {
    margin-top: 18px;
}

.username {
    color: #fe2c55;
    font-weight: bold;
    font-size: 15px;
}

.caption {
    margin-top: 8px;
    line-height: 1.5;
    color: #eee;
}

.meta {
    margin-top: 12px;
    color: #888;
    font-size: 13px;
}

.back {
    display: block;
    text-align: center;
    color: #aaa;
    text-decoration: none;
    margin-top: 18px;
}

.error {
    text-align: center;
}

.error h2 {
    color: #fe2c55;
}

.loading {
    display: none;
    margin-top: 20px;
    text-align: center;
    color: #aaa;
}

.spinner {
    width: 32px;
    height: 32px;
    border: 3px solid #333;
    border-top: 3px solid #fe2c55;
    border-radius: 50%;
    margin: 0 auto 12px;

    animation: spin .8s linear infinite;
}

@keyframes spin {
    to {
        transform: rotate(360deg);
    }
}

.footer {
    text-align: center;
    margin-top: 25px;
    color: #555;
    font-size: 12px;
}

</style>
"""


@app.route("/")
def home():

    return render_template_string("""
<!DOCTYPE html>

<html lang="id">

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1.0">

<title>TikTok Downloader</title>

{{ style|safe }}

</head>

<body>

<div class="wrapper">

    <div class="logo">
        ♪
    </div>

    <h1>
        TikTok Downloader
    </h1>

    <div class="subtitle">
        Paste link TikTok untuk melihat preview
        lalu download videonya.
    </div>

    <div class="card">

        <form
            id="previewForm"
            action="/preview"
            method="POST"
        >

            <input
                type="url"
                name="url"
                placeholder="Paste link TikTok di sini..."
                required
            >

            <button type="submit">
                Preview Video
            </button>

        </form>

        <div
            id="loading"
            class="loading"
        >

            <div class="spinner"></div>

            Mengambil informasi video...

        </div>

    </div>

    <div class="footer">
        Gunakan hanya untuk konten yang kamu punya
        izin untuk mengunduh.
    </div>

</div>


<script>

const form =
    document.getElementById("previewForm");

form.addEventListener(
    "submit",
    function () {

        document.getElementById(
            "loading"
        ).style.display = "block";

        const button =
            form.querySelector("button");

        button.disabled = true;

        button.innerText =
            "Memproses...";

    }
);

</script>

</body>

</html>
""", style=BASE_STYLE)


@app.route("/preview", methods=["POST"])
def preview():

    url = request.form.get(
        "url",
        ""
    ).strip()

    if not valid_tiktok_url(url):

        return render_template_string("""
        {{ style|safe }}

        <div class="wrapper">

            <div class="card error">

                <h2>
                    Link tidak valid
                </h2>

                <p>
                    Masukkan link TikTok yang benar.
                </p>

                <a
                    class="back"
                    href="/"
                >
                    ← Kembali
                </a>

            </div>

        </div>
        """, style=BASE_STYLE), 400


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


    try:

        result = subprocess.run(

            command,

            capture_output=True,

            text=True,

            timeout=60

        )


        if result.returncode != 0:

            return render_template_string("""
            {{ style|safe }}

            <div class="wrapper">

                <div class="card error">

                    <h2>
                        Video tidak bisa diproses
                    </h2>

                    <p>
                        TikTok mungkin membatasi video ini,
                        link sudah tidak aktif,
                        atau video tidak tersedia secara publik.
                    </p>

                    <a
                        class="back"
                        href="/"
                    >
                        ← Coba link lain
                    </a>

                </div>

            </div>
            """, style=BASE_STYLE), 500


        info = json.loads(
            result.stdout
        )


        thumbnail = (
            info.get("thumbnail")
            or ""
        )

        title = (
            info.get("description")
            or info.get("title")
            or "Video TikTok"
        )

        uploader = (
            info.get("uploader")
            or info.get("creator")
            or info.get("channel")
            or "TikTok User"
        )

        duration = info.get(
            "duration"
        )


        if duration:

            minutes = int(
                duration // 60
            )

            seconds = int(
                duration % 60
            )

            duration_text = (
                f"{minutes}:{seconds:02d}"
            )

        else:

            duration_text = "-"


        return render_template_string("""
<!DOCTYPE html>

<html lang="id">

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1.0">

<title>Preview TikTok</title>

{{ style|safe }}

</head>

<body>

<div class="wrapper">

    <div class="card">

        {% if thumbnail %}

        <img
            class="thumbnail"
            src="{{ thumbnail }}"
            alt="TikTok thumbnail"
        >

        {% endif %}

        <div class="info">

            <div class="username">
                @{{ uploader }}
            </div>

            <div class="caption">
                {{ title }}
            </div>

            <div class="meta">
                Durasi: {{ duration }}
            </div>

        </div>


        <form
            id="downloadForm"
            action="/download"
            method="POST"
        >

            <input
                type="hidden"
                name="url"
                value="{{ url }}"
            >

            <button type="submit">
                Download Video
            </button>

        </form>


        <div
            id="loading"
            class="loading"
        >

            <div class="spinner"></div>

            Menyiapkan file video...

        </div>


        <a
            class="back"
            href="/"
        >
            ← Masukkan link lain
        </a>

    </div>

</div>


<script>

const form =
    document.getElementById(
        "downloadForm"
    );

form.addEventListener(
    "submit",
    function () {

        document.getElementById(
            "loading"
        ).style.display = "block";

        const button =
            form.querySelector("button");

        button.disabled = true;

        button.innerText =
            "Menyiapkan download...";

    }
);

</script>

</body>

</html>
""",

        style=BASE_STYLE,
        thumbnail=thumbnail,
        title=title,
        uploader=uploader,
        duration=duration_text,
        url=url

        )


    except subprocess.TimeoutExpired:

        return """
        <h2>Server terlalu lama memproses video.</h2>
        """

    except Exception as e:

        print(
            "Preview error:",
            e
        )

        return """
        <h2>Terjadi kesalahan saat membaca video.</h2>
        """, 500


@app.route("/download", methods=["POST"])
def download():

    url = request.form.get(
        "url",
        ""
    ).strip()


    if not valid_tiktok_url(url):

        return "Link TikTok tidak valid.", 400


    folder = tempfile.mkdtemp()


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


    try:

        result = subprocess.run(

            command,

            capture_output=True,

            text=True,

            timeout=120

        )


        if result.returncode != 0:

            shutil.rmtree(
                folder,
                ignore_errors=True
            )

            return render_template_string("""
            {{ style|safe }}

            <div class="wrapper">

                <div class="card error">

                    <h2>
                        Download gagal
                    </h2>

                    <p>
                        TikTok tidak memberikan file video
                        untuk link ini.
                    </p>

                    <a
                        class="back"
                        href="/"
                    >
                        ← Coba Lagi
                    </a>

                </div>

            </div>
            """, style=BASE_STYLE), 500


        files = [

            f for f in os.listdir(folder)

            if not f.endswith(".part")

        ]


        if not files:

            shutil.rmtree(
                folder,
                ignore_errors=True
            )

            return (
                "File video tidak ditemukan.",
                500
            )


        filepath = os.path.join(
            folder,
            files[0]
        )


        extension = os.path.splitext(
            filepath
        )[1]


        return send_file(

            filepath,

            as_attachment=True,

            download_name=(
                "tiktok-video"
                + extension
            )

        )


    except subprocess.TimeoutExpired:

        shutil.rmtree(
            folder,
            ignore_errors=True
        )

        return """
        <h2>
        Download terlalu lama.
        </h2>
        """, 504


    except Exception as e:

        shutil.rmtree(
            folder,
            ignore_errors=True
        )

        print(
            "Download error:",
            e
        )

        return """
        <h2>
        Terjadi kesalahan pada server.
        </h2>
        """, 500


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
