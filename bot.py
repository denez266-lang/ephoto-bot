import os, asyncio, logging, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from Ephoto360 import Ephoto360
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

logging.basicConfig(level=logging.INFO)
for _n in ("httpx", "httpcore"):
    logging.getLogger(_n).setLevel(logging.WARNING)
TOKEN = os.environ["BOT_TOKEN"]
PAGE = 8
client = Ephoto360()
EFFECTS = client.list_effects()  # 433 effects bundled in the library


def find(q):
    q = q.strip().lower()
    if not q:
        return EFFECTS
    return [e for e in EFFECTS if all(w in e.name.lower() for w in q.split())]


def kb(results, page, q):
    rows = []
    for e in results[page * PAGE:(page + 1) * PAGE]:
        idx = EFFECTS.index(e)
        rows.append([InlineKeyboardButton(e.name[:60], callback_data=f"e:{idx}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"p:{page-1}"))
    if (page + 1) * PAGE < len(results):
        nav.append(InlineKeyboardButton("➡️", callback_data=f"p:{page+1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(rows)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً! /effects لعرض التأثيرات، أو /search كلمة للبحث (بالإنجليزي). مثال: /search blood\n"
        "Send /effects to browse or /search <word>.")


async def show(update: Update, ctx, q=""):
    ctx.user_data["q"] = q
    res = find(q)
    if not res:
        await update.message.reply_text("ما لقيت شي. جرب كلمة ثانية.")
        return
    await update.message.reply_text(f"{len(res)} تأثير:", reply_markup=kb(res, 0, q))


async def effects(update, ctx):
    await show(update, ctx, "")


async def search(update, ctx):
    await show(update, ctx, " ".join(ctx.args))


async def buttons(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query
    await cq.answer()
    kind, val = cq.data.split(":")
    if kind == "p":
        res = find(ctx.user_data.get("q", ""))
        await cq.edit_message_reply_markup(kb(res, int(val), ""))
    else:
        e = EFFECTS[int(val)]
        ctx.user_data["effect"] = int(val)
        ctx.user_data["texts"] = []
        labels = ", ".join(e.text_labels)
        await cq.message.reply_text(
            f"اخترت: {e.name}\nأرسل النص ({e.text_count} حقل: {labels}). كل حقل برسالة.")


async def text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if "effect" not in ctx.user_data:
        await update.message.reply_text("اختار تأثير أول: /effects")
        return
    e = EFFECTS[ctx.user_data["effect"]]
    ctx.user_data["texts"].append(update.message.text)
    left = e.text_count - len(ctx.user_data["texts"])
    if left > 0:
        await update.message.reply_text(f"باقي {left} حقل. أرسل التالي: {e.text_labels[len(ctx.user_data['texts'])]}")
        return
    texts = ctx.user_data["texts"]
    ctx.user_data["texts"] = []
    msg = await update.message.reply_text("⏳ جاري الصنع...")
    r = await asyncio.to_thread(client.create, e.slug, list(texts))
    if r.ok:
        await update.message.reply_photo(r.url)
    else:
        await update.message.reply_text(f"فشل: {r.error}")
    await msg.delete()


def health():  # lets free "web service" hosts keep the process alive
    port = int(os.environ.get("PORT", 0))
    if not port:
        return
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    threading.Thread(target=HTTPServer(("", port), H).serve_forever, daemon=True).start()


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("effects", effects))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if url:  # Render: webhook, so Telegram messages wake the sleeping service
        port = int(os.environ.get("PORT", 10000))
        app.run_webhook(listen="0.0.0.0", port=port, url_path=TOKEN,
                        webhook_url=f"{url}/{TOKEN}")
    else:  # local / Termux
        app.run_polling()


if __name__ == "__main__":
    main()
