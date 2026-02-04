import base64
import io
import os
import requests
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from openai import OpenAI
from PIL import Image  # ★ 追加（requirements.txt に pillow が必要）

app = FastAPI()

# ★ あなたの最新 Apps Script Webhook URL
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbys5XkMqr437ymQDoV_JB0Ij8oTnjqVWa2xzDBLs4DGRHCZSwDKjjEj1bA2ipe_Rzfx/exec"

# OpenAI
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODEL = "gpt-4.1-mini"

FORM_HTML = """
<html>
  <body>
    <h2>施工例 → Instagram投稿文（3案生成）</h2>
    <form action="/generate" method="post" enctype="multipart/form-data">
      <p>施工例画像：<input type="file" name="image" accept="image/*" required></p>
      <p>空間タイプ：<input type="text" name="space" placeholder="例：LDK、洗面"></p>
      <p>トーン：<input type="text" name="tone" placeholder="例：やさしい、上品"></p>
      <button type="submit">生成してスプレッドシートへ</button>
    </form>
  </body>
</html>
"""

def compress_image_bytes(img_bytes: bytes, max_side: int = 1280, quality: int = 72) -> bytes:
    """
    Apps Script 側へ base64 で送る前に、画像を軽くしてサイズ制限に引っかかりにくくする。
    - max_side: 長辺の最大ピクセル
    - quality: JPEG品質（低いほど軽い）
    """
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()

def build_prompt(space: str, tone: str, variant: str) -> str:
    style_map = {
        "A": "暮らしの情景重視（朝・夜・家族の動き）",
        "B": "空間ディテール重視（素材・色・光・質感）",
        "C": "短く余韻重視（言葉少なめで印象的）",
    }

    return f"""
あなたはハウスメーカーの広報担当です。
施工例写真を観察し、Instagram投稿文を作成してください。

【今回のバリエーション】
{variant}：{style_map.get(variant, "")}

【文章ルール】
・やさしく上品、暮らしが想像できる文体
・営業感、誇張表現は禁止（最安/No.1/絶対 など）
・冒頭は必ず「. . 𖥧 𖥧 .」
・本文は4〜6行、改行を保持
・絵文字は使わない

【指定（あれば反映）】
空間タイプ：{space}
トーン：{tone}

【固定フッター】※必ずこのまま
-----------------------

全国のハグ オーナーさまの暮らしをもっと見たい方は
プロフィールよりWEBをご覧ください！
@hughouse_official

ご質問ご相談等はDM・コメントへ
お気軽にどうぞ！

-----------------------
""".strip()

def generate_one(b64_for_vision: str, space: str, tone: str, variant: str) -> str:
    prompt = build_prompt(space, tone, variant)

    resp = client.responses.create(
        model=MODEL,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64_for_vision}"}
            ]
        }]
    )
    return resp.output_text.strip()

@app.get("/", response_class=HTMLResponse)
def index():
    return FORM_HTML

@app.post("/generate", response_class=HTMLResponse)
async def generate(
    image: UploadFile = File(...),
    space: str = Form(""),
    tone: str = Form(""),
):
    try:
        # 1) 画像読み込み
        raw_bytes = await image.read()

        # 2) Apps Script用に圧縮（軽量化）
        compressed_bytes = compress_image_bytes(raw_bytes, max_side=1280, quality=72)

        # 3) OpenAI Visionへ渡すbase64（圧縮後を使う：安定＆速い）
        b64 = base64.b64encode(compressed_bytes).decode("utf-8")

        # 4) 3案生成
        post_a = generate_one(b64, space, tone, "A")
        post_b = generate_one(b64, space, tone, "B")
        post_c = generate_one(b64, space, tone, "C")

        # 5) Apps Scriptへ送信（画像も送る）
        payload = {
            "filename": image.filename,
            "space": space,
            "tone": tone,
            "image_base64": b64,  # ★ 圧縮後base64
            "post_a": post_a,
            "post_b": post_b,
            "post_c": post_c,
            "status": "未確認"
        }

        r = requests.post(WEBHOOK_URL, json=payload, timeout=90)
        apps_script_reply = (r.text or "")[:600]
        r.raise_for_status()

        return f"""
        <html>
          <body>
            <h3>✅ スプレッドシートに追加しました</h3>

            <p><b>WEBHOOK_URL:</b> {WEBHOOK_URL}</p>
            <p><b>Apps Script reply:</b> <pre>{apps_script_reply}</pre></p>

            <p><b>raw bytes:</b> {len(raw_bytes)}</p>
            <p><b>compressed bytes:</b> {len(compressed_bytes)}</p>
            <p><b>base64 chars:</b> {len(b64)}</p>

            <h4>A案</h4>
            <pre style="white-space:pre-wrap;">{post_a}</pre>

            <h4>B案</h4>
            <pre style="white-space:pre-wrap;">{post_b}</pre>

            <h4>C案</h4>
            <pre style="white-space:pre-wrap;">{post_c}</pre>

            <p><a href="/">戻る</a></p>
          </body>
        </html>
        """
    except Exception as e:
        return f"""
        <html>
          <body>
            <h3>❌ ERROR</h3>
            <p>{str(e)}</p>
            <p><b>WEBHOOK_URL:</b> {WEBHOOK_URL}</p>
            <p><a href="/">戻る</a></p>
          </body>
        </html>
        """
