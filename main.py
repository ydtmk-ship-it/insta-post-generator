import base64
import os
import requests
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from openai import OpenAI

app = FastAPI()

# ✅ Apps Script（新URL）
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxBsC21vQ6px7FdojwuWN0hySPz8gDIAdMNsF6M5iH6RBwIbpObiVoriXi0-2l2tdPb/exec"

# ✅ OpenAI（APIキーは環境変数 OPENAI_API_KEY から読む）
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# 画像対応モデル（このままでOK。もしエラーになったら後で調整します）
MODEL = "gpt-4.1-mini"

FORM_HTML = """
<html>
  <body>
    <h2>施工例→Instagram投稿文 生成</h2>
    <form action="/generate" method="post" enctype="multipart/form-data">
      <p>施工例画像：<input type="file" name="image" accept="image/*" required></p>
      <p>空間タイプ（任意）：<input type="text" name="space" placeholder="例：LDK、洗面"></p>
      <p>トーン（任意）：<input type="text" name="tone" placeholder="例：やさしい、上品"></p>
      <button type="submit">生成してシートに追加</button>
    </form>
  </body>
</html>
"""

def build_prompt(space: str, tone: str) -> str:
    return f"""
あなたはハウスメーカーの広報担当です。
以下の施工例写真をもとにInstagram投稿文を作成してください。

【文章ルール】
・文体：やさしい／上品／暮らしが想像できる
・営業感・売り込み感は出さない
・冒頭に必ず「. . 𖥧 𖥧 .」を入れる
・4〜6行程度
・改行は保持
・絵文字は使わない
・空間タイプ/トーンの指定があれば反映する

【指定（あれば反映）】
空間タイプ：{space}
トーン：{tone}

【固定フッター】※必ずこのまま入れる
-----------------------

全国のハグ オーナーさまの暮らしをもっと見たい方は
プロフィールよりWEBをご覧ください！
@hughouse_official

ご質問ご相談等はDM・コメントへ
お気軽にどうぞ！

-----------------------
""".strip()

@app.get("/", response_class=HTMLResponse)
def index():
    return FORM_HTML

@app.post("/generate", response_class=HTMLResponse)
async def generate(
    image: UploadFile = File(...),
    space: str = Form(""),
    tone: str = Form(""),
):
    # 1) 画像をbase64化
    img_bytes = await image.read()
    b64 = base64.b64encode(img_bytes).decode("utf-8")

    # 2) AIで投稿文生成
    prompt = build_prompt(space, tone)
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
    post_text = resp.output_text.strip()

    # 3) Apps ScriptへPOST（スプレッドシートに追記）
    payload = {
        "filename": image.filename,
        "post_text": post_text,
        "space": space,
        "tone": tone,
        "status": "未確認"
    }
    r = requests.post(WEBHOOK_URL, json=payload, timeout=30)
    r.raise_for_status()

    # 4) 画面にも表示
    return f"""
    <html>
      <body>
        <h3>✅ 追加しました</h3>
        <p>スプレッドシートに1行追記しました。</p>
        <pre style="white-space:pre-wrap;">{post_text}</pre>
        <p><a href="/">戻る</a></p>
      </body>
    </html>
    """
