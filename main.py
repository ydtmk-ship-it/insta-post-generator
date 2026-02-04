import base64
import os
import requests
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from openai import OpenAI

app = FastAPI()

# ★ 最新の Apps Script Webhook URL（あなたが貼ってくれたもの）
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbyhn8ocRNYNwitowJeDTfeez6V2rk1ZfVFQLqs5vfDoAzXML63tZysSg8LCtoazXwtu/exec"

# OpenAI
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODEL = "gpt-4.1-mini"

# ---------- 画面 ----------
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

# ---------- プロンプト ----------
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
・営業感、誇張表現は禁止
・冒頭は必ず「. . 𖥧 𖥧 .」
・本文は4〜6行、改行を保持
・絵文字は使わない

【指定】
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

def generate_one(b64: str, space: str, tone: str, variant: str) -> str:
    prompt = build_prompt(space, tone, variant)
    resp = client.responses.create(
        model=MODEL,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}"}
            ]
        }]
    )
    return resp.output_text.strip()

# ---------- ルーティング ----------
@app.get("/", response_class=HTMLResponse)
def index():
    return FORM_HTML

@app.post("/generate", response_class=HTMLResponse)
async def generate(
    image: UploadFile = File(...),
    space: str = Form(""),
    tone: str = Form(""),
):
    # 画像を base64 に
    img_bytes = await image.read()
    b64 = base64.b64encode(img_bytes).decode("utf-8")

    # 3案生成
    post_a = generate_one(b64, space, tone, "A")
    post_b = generate_one(b64, space, tone, "B")
    post_c = generate_one(b64, space, tone, "C")

    # Apps Script へ送信
    payload = {
        "filename": image.filename,
        "space": space,
        "tone": tone,
        "image_base64": b64,
        "post_a": post_a,
        "post_b": post_b,
        "post_c": post_c,
        "status": "未確認"
    }

    r = requests.post(WEBHOOK_URL, json=payload, timeout=60)
    apps_script_reply = r.text[:300]
    r.raise_for_status()

    # 画面表示
    return f"""
    <html>
      <body>
        <h3>✅ スプレッドシートに追加しました</h3>
        <p><b>WEBHOOK_URL:</b> {WEBHOOK_URL}</p>
        <p><b>Apps Script reply:</b> {apps_script_reply}</p>

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
