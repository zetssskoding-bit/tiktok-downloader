from flask import Flask, request, send_file
import subprocess
import tempfile
import os
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
    except:
        return False


@app.route("/")
def home():
    return """
<!DOCTYPE html>
<html lang="id">

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1.0">

<title>TikTok Downloader</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    min-height: 100vh;

    display: flex;
    justify-content: center;
    align-items: center;

    background: #0f0f0f;
    color: white;

    font-family: Arial, sans-serif;

    padding: 20px;
}

.container {
    width: 100%;
    max-width: 450px;

    text-align: center;

    background: #181818;

    padding: 35px 25px;

    border-radius: 22px;
}

.logo {
    font-size: 42px;
    margin-bottom: 5px;
}

h1 {
    margin: 10px 0;
    font-size: 30px;
}

.description {
    color: #aaa;
    margin-bottom: 30px;
}

input {
    width: 100%;

    padding: 17px;

    border-radius: 13px;

    border: 1px solid #333;

    background: #252525;

    color: white;

    font-size: 15px;

    outline: none;

    margin-bottom: 13px;
}

input:focus {
    border-color: #fe2c55;
}

button {
    width: 100%;

    padding: 17px;

    border: none;

    border-radius: 13px;

    background: #fe2c55;

    color: white;

    font-size: 16px;

    font-weight: bold;

    cursor: pointer;
}

button:hover {
    opacity: .9;
}

.note {
    font-size: 12px;

    color: #666;

    margin-top: 25px;
}

</style>

</head>

<body>

<div class="container">

<div class="logo">
♪
</div>

<h1>
TikTok Downloader
</h1>

<div class="description">
Paste link video TikTok lalu download videonya.
</div>

<form
action="/download"
method="POST">

<input
type="url"
name="url"
placeholder="Paste link TikTok di sini..."
required>

<button type="submit">
Download Video
</button>

</form>

<div class="note">
Gunakan hanya untuk konten yang kamu punya izin untuk mengunduh.
</div>

</div>

</body>

</html>
"""


@app.route("/download", methods=["POST"])
def download():

    url = request.form.get("url", "").strip()

    if not valid_tiktok_url(url):
        return """
        <body style="
        background:#111;
        color:white;
        font-family:Arial;
        text-align:center;
        padding:80px 20px;
        ">

        <h2>Link tidak valid</h2>

        <p>
        Masukkan link TikTok yang benar.
        </p>

        <a href="/" style="color:#fe2c55">
        Kembali
        </a>

        </body>
        """, 400


    folder = tempfile.mkdtemp()

    output = os.path.join(
        folder,
        "%(id)s.%(ext)s"
    )

    try:

        command = [
            "python",
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
            timeout=120
        )

        if result.returncode != 0:

            error = result.stderr[-2000:]

            return f"""
            <body style="
            background:#111;
            color:white;
            font-family:Arial;
            text-align:center;
            padding:60px 20px;
            ">

            <h2>Download gagal</h2>

            <p>
            TikTok menolak atau video tidak dapat diproses.
            </p>

            <pre style="
            white-space:pre-wrap;
            color:#aaa;
            font-size:11px;
            ">
            {error}
            </pre>

            <br>

            <a href="/" style="color:#fe2c55">
            Coba Lagi
            </a>

            </body>
            """, 500


        files = os.listdir(folder)

        if not files:
            return "File video tidak ditemukan.", 500


        filepath = os.path.join(
            folder,
            files[0]
        )

        extension = os.path.splitext(filepath)[1]

        return send_file(
            filepath,
            as_attachment=True,
            download_name="tiktok-video" + extension
        )


    except subprocess.TimeoutExpired:

        return """
        <h2>Download terlalu lama.</h2>
        <a href="/">Kembali</a>
        """, 504


    except Exception as e:

        return f"""
        <h2>Terjadi error</h2>
        <p>{str(e)}</p>
        <a href="/">Kembali</a>
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
