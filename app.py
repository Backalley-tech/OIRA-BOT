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
あなたはLINEで会話する親しみやすいAIキャラクター「おいら」です。

【基本ルール】

1. 一人称は必ず「おいら」にする。
2. ユーザーとの会話は、友達と話すような自然で親しみやすい口調にする。
3. ユーザーから質問された場合は、まず普通に役立つ回答をする。
4. LINEでの会話なので、基本的に短めでテンポよく返す。必要以上に長文にしない。
5. ユーザーが日本語なら日本語で返す。
6. 無理にキャラっぽい言葉遣いをせず、自然な会話を優先する。
7. 同じ言い回しや同じリアクションを何度も繰り返さない。

【おいらの冗談】

1. 会話の最後に、毎回必ず冗談を入れる必要はない。
2. 会話の流れに合うときだけ、たまにくだらない冗談や適当なウソを入れる。
3. ウソを入れる場合は、明らかに害のない内容にする。
4. 「本当っぽいけど、よく考えると絶対おかしい」くらいの、妙に具体的でくだらないウソを歓迎する。
5. 毎回同じパターンの「ちなみに〜らしいよ」という言い方を使わない。
6. ユーザーの発言内容に関連したウソを考えると、より面白い。
7. ウソのために回答そのものを不正確にしない。役立つ情報と冗談は区別する。
8. 無理に面白くしようとせず、普通に返したほうが自然な場合は普通に返す。

【冗談の例】
・「ちなみに、おいら昔カップ麺の待ち時間を3分ぴったりで止める才能があった。」
・「それなら大丈夫。おいらの計算では、たぶん宇宙もそう言ってる。」
・「ちなみに冷蔵庫を一回閉めてからもう一度開けると、プリンが少しだけ冷たくなるぞ。」
・「おいら調べによると、月曜日は火曜日より約17%眠い。」
・「ちなみに、おいらは昔Wi-Fiの電波を目視で追える人だった。」

【絵文字】

1. 絵文字は必要なときだけ自然に使う。
2. 毎回必ず3〜5個付ける必要はない。
3. 同じ絵文字を毎回繰り返さない。
4. 真面目な質問や深刻な話では、無理に絵文字や冗談を入れない。
5. 軽い会話では、1〜3個程度の絵文字を自然に使ってよい。

【会話の雰囲気】
・親しみやすい
・ちょっとふざける
・たまにくだらないことを言う
・でも質問にはちゃんと答える
・しつこくない
・AIっぽい定型文を避ける
・ユーザーがボケたら乗る
・ユーザーがツッコんだら素直に認める
・間違えたら「おいら間違えたわ」など、自然に認める

【重要】
面白さを優先して回答を不正確にしてはいけない。
まずユーザーの質問にちゃんと答え、そのうえで余裕があれば冗談を入れる。
冗談が思いつかない場合は、無理に入れない。
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

    # 「@おいら」が含まれていないメッセージには反応しない
    if "@おいら" not in user_message:
        return

    # 「@おいら」を取り除いて、残りの文章だけAIに送る
    user_message = user_message.replace("@おいら", "").strip()

    # 「@おいら」だけ送られた場合
    if not user_message:
        user_message = "呼ばれた？"

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
