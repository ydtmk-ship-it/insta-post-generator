import base64
import os
import requests
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from openai import OpenAI

app = FastAPI()

WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbyhn8ocRNYNwitowJeDTfeez6V2rk1ZfVFQLqs5vfDoAzXML63tZysSg8LCtoazXwtu/exec"

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODEL = "gpt-4.1-mini"

FORM_HTML = """
<html>
  <body>
    <h2>施工例→Instagram投稿文 3案生成</h2>
    <form action="/generate" method="post" enctype="multipart/form-data">
      <p>施工例画像：<input type="file" name="image" accept="image/*" required></p>
      <p>空間タイプ（任意）：<input type="text" name="space" placeholder="例：LDK、洗面"></p>
      <p>トーン（任意）：<input type="text" name="tone" placeholder="例：やさしい、上品"></p>
      <button type="submit">3案生成してシートに追加</button>
    </form>
  </body>
</html>
"""

def build_prompt(space: str, tone: str, variant: str) -> str:
    # variant: "A" "B" "C"
    style_map = {
        "A": "暮らしの情景重視（朝/夜/家族の動き）",
        "B": "空間ディテール重視（素材/色/光/質感）",
        "C": "短めで余韻重視（少ない言葉で印象的に）",
    }
    return f"""
あなたはハウスメーカーの広報担当です。施工例写真をもとにInstagram投稿文を作成してください。

【今回のバリエーション】{variant}
{style_map.get(variant, "")}

【文章ルール】
・文体：やさしい／上品／暮らしが想像できる
・営業感・売り込み感は出さない（誇張禁止）
・冒頭に必ず「. . 𖥧 𖥧 .」を入れる
・本文は4〜6行程度（改行を保持）
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

def gen_one(b64: str, space: str, tone: str, variant: str) -> str:
    prompt = build_prompt(space, tone, variant)
    resp = client.responses.create(
        model=MODEL,
        input=[{
            "role":"user",
            "content":[
                {"type":"input_text","text":prompt},
                {"type":"input_image","image_url":f"data:image/jpeg;base64,{b64}"}
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
    img_bytes = await image.read()
    b64 = base64.b64encode(img_bytes).decode("utf-8")

    post_a = gen_one(b64, space, tone, "A")
    post_b = gen_one(b64, space, tone, "B")
    post_c = gen_one(b64, space, tone, "C")

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
    r.raise_for_status()

    return f"""
    <html>
      <body>
        <h3>✅ 3案を追加しました</h3>
        <p>スプレッドシートに1行追記しました。</p>

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
