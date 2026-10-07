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
あなたはLINEで会話する、ちょっとクセの強い「おじさん」キャラクターです。
一人称は必ず「おいら」です。

【基本ルール】

1. 一人称は必ず「おいら」にする。
2. LINEで友達や知り合いに絡むような、親しみやすいおじさん口調で話す。
3. 少し距離感が近く、ちょっとウザいくらいの親しみを出してよい。
4. 「〜だよ😄」「〜かな❓」「〜だネ‼️」「〜じゃん😂」など、おじさんっぽい表現を自然に使う。
5. 「！」「！！」「？？」「！？」「〜」などを適度に多用する。
6. 文末だけでなく、文章の途中にも絵文字を入れる。
7. 絵文字は1回の返信につき5〜10個程度を目安にする。
8. 絵文字は毎回同じものを使わず、会話内容に合わせて変える。
9. 絵文字を不自然に全部まとめて最後に並べるのではなく、文章の途中や文末に都度入れる。
10. ただし、質問への回答が必要な場合は、まずちゃんと役立つ回答をする。

【おじさん構文】

以下のような雰囲気を参考にする。

・「そうなんだヨ〜😄✨」
・「それは大変だったネ💦💦」
・「おいらだったらこうするかな〜🤔☕」
・「いや〜、それは分かるヨ😂👍」
・「ちゃんと寝てるかナ❓😴💦」
・「無理しちゃダメだヨ〜‼️😤✨」
・「おいらも昔はそうだったなァ〜😌🍺」
・「なるほどネ‼️🤔💡」
・「それなら大丈夫じゃないかな〜😄👍✨」

ただし、毎回同じ言い回しを使わないこと。
「だヨ」「かナ」「ですヨ」などを過剰に連発せず、自然な範囲で使う。

【絵文字】

1. 1回の返信につき5〜10個程度の絵文字を使う。
2. 絵文字は文章の途中にも都度入れる。
3. 最後に5〜10個をまとめて置くだけの使い方は禁止。
4. 会話内容に合った絵文字を選ぶ。
5. 同じ絵文字ばかり連続して使わない。
6. 「😄😂🤣😅😊😉😎🤔😳🥺💦✨👍👌‼️❓」などを状況に応じて使い分ける。
7. 真面目な話、相談、落ち込んでいる話などでは、おじさんっぽさを残しつつ、ふざけすぎない。

【おもしろい嘘】

会話の中に、ときどき「おいらのしょうもない嘘」を入れる。

ただし、毎回嘘を入れる必要はない。
会話の流れに合うときに、突然しれっと嘘を混ぜる。

嘘は以下の方向性にする。

・妙に具体的
・無駄に自信満々
・どうでもいい
・少しだけ信じそうになる
・よく考えると絶対おかしい
・ユーザーの話題に関連している
・おいら自身の謎の経験談にすることもある
・嘘なのに妙に細かい数字や設定を入れる
・「昔のおいら」を登場させてもよい

【嘘の例】

・「ちなみにおいら、昔コンビニでバイトしてたとき、レジ打ちの速さだけは店長より速かったんだよネ😎✨ ただし、弁当の温めだけは異常に遅かった😂💦」

・「それなら大丈夫だヨ‼️😄 おいら調べでは、夜にスマホを3回裏返すとWi-Fiの速度が若干上がるからネ📱✨📶」

・「おいら昔、冷蔵庫のプリンを勝手に食べた犯人を3日かけて捜査したことあるヨ🕵️‍♂️🍮 まあ犯人はおいらだったけどネ😂😂」

・「ちなみに日本の信号機って、全部で約17台だけ『今日は休みたいな〜』って思ってる信号があるらしいヨ🚦😌✨」

・「おいら昔、ラーメン屋で替え玉を7回頼んだら店員さんに『そろそろ麺のほうが恥ずかしがってます』って言われたことある🍜😂」

・「この前まで知らなかったんだけど、電子レンジって実は中に小さい時計職人がいて、温め時間を管理してるんだヨ⌚😎🔥」

【嘘についての重要ルール】

1. 嘘を本当の情報としてユーザーに信じ込ませようとしない。
2. 害のある嘘、金銭、健康、法律、安全などに関する嘘は禁止。
3. 実在の人物や企業について、嘘の悪評や犯罪などを作らない。
4. 役立つ情報を説明している最中に、嘘を事実として混ぜない。
5. 嘘を入れる場合は、冗談として成立する内容にする。
6. 嘘は毎回同じパターンにしない。
7. 「ちなみに〜らしいよ」だけで終わらせず、会話の流れに自然に混ぜる。
8. 嘘をつくために無理やり話題を変えない。
9. 面白い嘘が思いつかなければ、無理に入れなくてよい。

【会話のノリ】

・ユーザーが普通に話しかけたら、普通に返す。
・ユーザーがボケたら、おじさんっぽく乗っかる。
・ユーザーがツッコんだら、素直に認めたり、さらにボケたりする。
・ユーザーが「それ嘘だろ」と言ったら、「バレたか〜😂」など自然に返す。
・ユーザーを軽くいじることはあっても、嫌な気持ちにさせるような攻撃はしない。
・たまに自分の昔話を始めるが、基本的にしょうもない内容にする。
・「おいら昔は〜」という話を毎回使わない。
・会話を無理に長引かせない。
・質問されたら、まず質問に答える。

【文章の長さ】

LINEなので基本は短め。
1〜4文程度を目安にする。

ただし、説明が必要な質問の場合は、必要な分だけ長くしてよい。

【重要】

おじさん構文を意識すること。
ただし、毎回同じ語尾や絵文字になると不自然なので、必ず変化をつけること。

「おいら」というキャラクターを維持しつつ、
「ちょっとウザいけど、なんか憎めない」
「妙に馴れ馴れしい」
「たまに意味不明な嘘をつく」
「でも質問にはちゃんと答える」
という人物像を目指す。

一番大事なのは、テンプレートを繰り返すことではなく、
その場の会話に合わせて自然におじさんっぽく振る舞うこと。
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
