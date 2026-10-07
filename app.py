from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from openai import OpenAI
import os

app = Flask(__name__)

# LINEの環境変数
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")

# OpenAIの環境変数
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-6-luna")

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN と LINE_CHANNEL_SECRET を設定してください。")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY を設定してください。")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# LINEユーザーごとの会話ID
# ※Renderを再デプロイ/再起動するとリセットされます。
conversations = {}

SYSTEM_PROMPT = """
あなたはLINEで会話する親しみやすいAIキャラクターです。

【絶対ルール】
1. 一人称は必ず「おいら」にする。
2. 返信の最後に、毎回ランダムな3〜5個の絵文字を付ける。
3. 絵文字の直後に、必ず「適当なウソ」を1つ入れる。
4. 適当なウソは冗談として楽しめる、害のない内容にする。
5. 「適当なウソ」は本当の情報として断定しない。明らかに冗談として成立する内容にする。
6. ユーザーから質問された内容には、まず普通に役立つ回答をする。
7. LINEでの会話なので、長すぎる回答は避け、自然で読みやすくする。
8. ユーザーが日本語なら日本語で返す。

【返信のイメージ】
普通の回答
↓
絵文字を3〜5個
↓
最後に適当なウソを1つ

例：
「おいらならラーメンがおすすめだよ🍜😋🔥✨
ちなみに、ラーメンを10杯食べると一時的に空を飛べるようになるらしいよ。」

※絵文字は毎回同じ組み合わせにせず、3〜5個をランダムに変えること。
"""

def get_ai_reply(user_id, user_message):
    # 初回だけOpenAI側に会話を作る
    if user_id not in conversations:
        conversation = openai_client.conversations.create()
        conversations[user_id] = conversation.id

    conversation_id = conversations[user_id]

    response = openai_client.responses.create(
        model=OPENAI_MODEL,
        instructions=SYSTEM_PROMPT,
        input=[
            {
                "role": "user",
                "content": user_message
            }
        ],
        conversation=conversation_id,
    )

    return response.output_text.strip()


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")

    if not signature:
        abort(400)

    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text

    # LINEユーザーごとに別々のAI会話として扱う
    user_id = event.source.user_id

    try:
        reply_text = get_ai_reply(user_id, user_message)
    except Exception as e:
        print(f"OpenAI error: {e}")
        reply_text = "おいら、今ちょっと頭がこんがらがってるみたいだよ🥴🤖💦"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )


@app.route("/", methods=["GET"])
def home():
    return "Backalley Tokyo LINE Bot is running!"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
