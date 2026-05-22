import os
import json
import logging
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN    = os.getenv("BOT_TOKEN", "8653082594:AAGvap2Z7L_v308Wej6Jk3yWYaQDdei9_F0")
SUPER_ADMIN  = 7512529826
DATA_FILE    = "data.json"

# conversation states
REVIEW_TEXT  = 1
USER_MSG     = 2
REPLY_TEXT   = 3

# ──────────────────────────────────────────────────────────────────────────────
# DATA
# ──────────────────────────────────────────────────────────────────────────────
def load() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "reviews": [], "admins": [SUPER_ADMIN], "banned": []}

def save(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def reg(user) -> dict:
    data = load()
    uid  = str(user.id)
    old  = data["users"].get(uid, {})
    data["users"][uid] = {
        "id":         user.id,
        "username":   user.username  or old.get("username",  ""),
        "first_name": user.first_name or old.get("first_name", ""),
        "joined":     old.get("joined", datetime.now().isoformat()),
    }
    save(data)
    return data

def is_admin(uid: int) -> bool:
    return uid == SUPER_ADMIN or uid in load().get("admins", [])

def is_banned(uid: int) -> bool:
    return uid in load().get("banned", [])

# ──────────────────────────────────────────────────────────────────────────────
# KEYBOARDS
# ──────────────────────────────────────────────────────────────────────────────
def main_kb(uid: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("⭐ Оставить отзыв"), KeyboardButton("📋 Частые вопросы")],
        [KeyboardButton("🌐 Контакты и соцсети"), KeyboardButton("📩 Написать админу")],
    ]
    if is_admin(uid):
        rows.append([KeyboardButton("🔧 Панель админа")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def stars_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(s, callback_data=f"rate_{i}")
        for i, s in enumerate(["⭐","⭐⭐","⭐⭐⭐","⭐⭐⭐⭐","⭐⭐⭐⭐⭐"], 1)
    ]])

def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Все пользователи",  callback_data="adm_users")],
        [InlineKeyboardButton("📊 Все отзывы",        callback_data="adm_reviews")],
        [InlineKeyboardButton("📢 Рассылка",          callback_data="adm_broadcast")],
        [InlineKeyboardButton("🚫 Забаненные",        callback_data="adm_banned")],
        [InlineKeyboardButton("➕ Добавить админа",   callback_data="adm_addadmin"),
         InlineKeyboardButton("➖ Удалить админа",    callback_data="adm_removeadmin")],
        [InlineKeyboardButton("👮 Список админов",    callback_data="adm_listadmins")],
    ])

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="adm_back")]])

# ──────────────────────────────────────────────────────────────────────────────
# /start
# ──────────────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reg(user)
    if is_banned(user.id):
        await update.message.reply_text("🚫 Вы заблокированы.")
        return
    await update.message.reply_text(
        f"👋 Привет, {user.first_name or 'друг'}!\n\n"
        "Здесь ты можешь:\n"
        "• Оставить отзыв о нас ⭐\n"
        "• Посмотреть частые вопросы 📋\n"
        "• Связаться с нами 📩\n"
        "• Перейти в наш Telegram-канал 🌐\n\n"
        "Выбери нужный пункт в меню ниже 👇",
        parse_mode="HTML",
        reply_markup=main_kb(user.id),
    )

# ──────────────────────────────────────────────────────────────────────────────
# BAN GUARD (middleware helper)
# ──────────────────────────────────────────────────────────────────────────────
async def ban_check(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    if uid and is_banned(uid) and not is_admin(uid):
        if update.message:
            await update.message.reply_text("🚫 Вы заблокированы и не можете пользоваться ботом.")
        return True
    return False

# ──────────────────────────────────────────────────────────────────────────────
# REVIEW
# ──────────────────────────────────────────────────────────────────────────────
async def review_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if await ban_check(update): return
    reg(update.effective_user)
    await update.message.reply_text(
        "⭐ <b>Оставить отзыв</b>\n\nВыбери оценку:",
        parse_mode="HTML", reply_markup=stars_kb()
    )

async def review_rating_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    rating = int(q.data.split("_")[1])
    ctx.user_data["rating"] = rating
    await q.edit_message_text(
        f"Ты выбрал: {'⭐'*rating}\n\nТеперь напиши свой отзыв текстом:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="review_cancel")]])
    )
    return REVIEW_TEXT

async def review_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    text   = update.message.text.strip()
    rating = ctx.user_data.get("rating", 5)
    data   = reg(user)
    data["reviews"].append({
        "user_id": user.id, "username": user.username or user.first_name,
        "rating": rating, "text": text, "date": datetime.now().isoformat()
    })
    save(data)
    await update.message.reply_text(
        f"✅ Спасибо за отзыв!\n\nОценка: {'⭐'*rating}\n📝 «{text}»",
        reply_markup=main_kb(user.id)
    )
    for adm in data.get("admins", []):
        try:
            await ctx.bot.send_message(adm,
                f"📬 <b>Новый отзыв!</b>\n"
                f"👤 {user.first_name} (@{user.username or '—'}) | <code>{user.id}</code>\n"
                f"{'⭐'*rating}\n💬 {text}", parse_mode="HTML")
        except: pass
    return ConversationHandler.END

async def review_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("❌ Отзыв отменён.")
    return ConversationHandler.END

# ──────────────────────────────────────────────────────────────────────────────
# FAQ
# ──────────────────────────────────────────────────────────────────────────────
async def faq(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if await ban_check(update): return
    reg(update.effective_user)
    await update.message.reply_text(
        "📋 <b>Частые вопросы</b>\n\n"
        "❓ <b>Как с вами связаться?</b>\n"
        "Нажми «📩 Написать админу» и напиши свой вопрос — мы ответим в ближайшее время.\n\n"
        "❓ <b>Как оставить отзыв?</b>\n"
        "Нажми «⭐ Оставить отзыв» в меню.\n\n"
        "❓ <b>Где вы находитесь?</b>\n"
        "Мы работаем онлайн и принимаем клиентов со всего мира.\n\n"
        "❓ <b>Как отписаться от рассылки?</b>\n"
        "Напиши админу «отписаться» — мы исключим тебя из рассылок.",
        parse_mode="HTML", reply_markup=main_kb(update.effective_user.id)
    )

# ──────────────────────────────────────────────────────────────────────────────
# CONTACTS
# ──────────────────────────────────────────────────────────────────────────────
async def contacts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if await ban_check(update): return
    reg(update.effective_user)
    await update.message.reply_text(
        "🌐 <b>Контакты и соцсети</b>\n\nВыбери нужную платформу:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📣 Telegram-канал", url="https://t.me/macanxyecocina")
        ]])
    )

# ──────────────────────────────────────────────────────────────────────────────
# WRITE TO ADMIN
# ──────────────────────────────────────────────────────────────────────────────
async def user_msg_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if await ban_check(update): return
    reg(update.effective_user)
    await update.message.reply_text(
        "📩 Напиши своё сообщение — мы передадим его администратору:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="msg_cancel")]])
    )
    return USER_MSG

async def user_msg_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    data = reg(user)

    # Send to all admins with Reply + Ban buttons
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("↩️ Ответить", callback_data=f"reply_{user.id}"),
        InlineKeyboardButton("🚫 Заблокировать", callback_data=f"ban_{user.id}"),
    ]])
    forwarded = (
        f"📩 <b>Сообщение от пользователя</b>\n"
        f"👤 {user.first_name} (@{user.username or '—'}) | ID: <code>{user.id}</code>\n\n"
        f"💬 {text}"
    )
    sent = False
    for adm in data.get("admins", []):
        try:
            await ctx.bot.send_message(adm, forwarded, parse_mode="HTML", reply_markup=kb)
            sent = True
        except: pass

    reply = "✅ Сообщение отправлено! Мы ответим в ближайшее время." if sent else "⚠️ Не удалось отправить. Попробуй позже."
    await update.message.reply_text(reply, reply_markup=main_kb(user.id))
    return ConversationHandler.END

async def msg_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("❌ Отменено.")
    return ConversationHandler.END

# ──────────────────────────────────────────────────────────────────────────────
# ADMIN REPLY TO USER  (↩️ Ответить)
# ──────────────────────────────────────────────────────────────────────────────
async def reply_btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True); return ConversationHandler.END

    target_id = int(q.data.split("_", 1)[1])
    ctx.user_data["reply_to"] = target_id

    # extract original message text for context
    orig = ""
    if q.message and q.message.text:
        for line in q.message.text.splitlines():
            if line.startswith("💬"):
                orig = line[2:].strip(); break

    ctx.user_data["reply_orig"] = orig
    prompt = f"✏️ Напиши ответ пользователю <code>{target_id}</code>"
    if orig:
        prompt += f"\n<i>Их сообщение: {orig}</i>"

    await q.message.reply_text(
        prompt, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="reply_cancel")]])
    )
    return REPLY_TEXT

async def reply_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    target_id = ctx.user_data.get("reply_to")
    orig      = ctx.user_data.get("reply_orig", "")
    text      = update.message.text.strip()

    if not target_id:
        await update.message.reply_text("⚠️ Ошибка: получатель не найден.")
        return ConversationHandler.END

    msg_to_user = (
        "📬 <b>Вам пришёл ответ от администратора</b>\n\n"
        + (f"<i>Ваш вопрос: {orig}</i>\n\n" if orig else "")
        + f"💬 {text}"
    )
    try:
        await ctx.bot.send_message(target_id, msg_to_user, parse_mode="HTML")
        await update.message.reply_text("✅ Ответ отправлен!", reply_markup=main_kb(update.effective_user.id))
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось отправить: {e}", reply_markup=main_kb(update.effective_user.id))

    ctx.user_data.pop("reply_to",   None)
    ctx.user_data.pop("reply_orig", None)
    return ConversationHandler.END

async def reply_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("❌ Ответ отменён.")
    ctx.user_data.pop("reply_to",   None)
    ctx.user_data.pop("reply_orig", None)
    return ConversationHandler.END

# ──────────────────────────────────────────────────────────────────────────────
# BAN / UNBAN  (inline button + admin panel)
# ──────────────────────────────────────────────────────────────────────────────
async def ban_btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True); return

    target_id = int(q.data.split("_", 1)[1])
    data      = load()

    if target_id == SUPER_ADMIN or is_admin(target_id):
        await q.answer("⛔ Нельзя забанить админа", show_alert=True); return

    if target_id not in data.get("banned", []):
        data.setdefault("banned", []).append(target_id)
        save(data)
        # notify user
        try:
            await ctx.bot.send_message(target_id,
                "🚫 <b>Вы были заблокированы администратором.</b>\n"
                "Если считаете это ошибкой — обратитесь в поддержку.", parse_mode="HTML")
        except: pass
        await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("↩️ Ответить", callback_data=f"reply_{target_id}"),
            InlineKeyboardButton("✅ Разбанить", callback_data=f"unban_{target_id}"),
        ]]))
        await q.message.reply_text(f"🚫 Пользователь <code>{target_id}</code> заблокирован.", parse_mode="HTML")
    else:
        await q.answer("Пользователь уже заблокирован", show_alert=True)

async def unban_btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id):
        await q.answer("⛔ Нет доступа", show_alert=True); return

    target_id = int(q.data.split("_", 1)[1])
    data = load()
    if target_id in data.get("banned", []):
        data["banned"].remove(target_id)
        save(data)
        try:
            await ctx.bot.send_message(target_id,
                "✅ <b>Вы были разблокированы.</b>\nТеперь вы снова можете пользоваться ботом.", parse_mode="HTML")
        except: pass
        await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("↩️ Ответить", callback_data=f"reply_{target_id}"),
            InlineKeyboardButton("🚫 Заблокировать", callback_data=f"ban_{target_id}"),
        ]]))
        await q.message.reply_text(f"✅ Пользователь <code>{target_id}</code> разблокирован.", parse_mode="HTML")
    else:
        await q.answer("Пользователь не заблокирован", show_alert=True)

# ──────────────────────────────────────────────────────────────────────────────
# ADMIN PANEL
# ──────────────────────────────────────────────────────────────────────────────
async def admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа."); return
    await update.message.reply_text("🔧 <b>Панель админа</b>", parse_mode="HTML", reply_markup=admin_kb())

async def admin_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not is_admin(q.from_user.id):
        await q.edit_message_text("⛔ Нет доступа."); return

    action = q.data
    data   = load()

    # ── users ──
    if action == "adm_users":
        users = data.get("users", {})
        banned = data.get("banned", [])
        if not users:
            await q.edit_message_text("👥 Пользователей пока нет.", reply_markup=back_kb()); return
        lines = [f"👥 <b>Все пользователи ({len(users)}):</b>\n"]
        for uid, u in list(users.items()):
            name  = f"@{u['username']}" if u.get("username") else u.get("first_name") or "—"
            ban_m = " 🚫" if u["id"] in banned else ""
            lines.append(f"• {name} | <code>{u['id']}</code>{ban_m}")
        # telegram message limit ~4096 chars — split if needed
        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:4000] + "\n…(список обрезан)"
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=back_kb())

    # ── reviews ──
    elif action == "adm_reviews":
        reviews = data.get("reviews", [])
        if not reviews:
            await q.edit_message_text("📊 Отзывов пока нет.", reply_markup=back_kb()); return
        avg   = sum(r["rating"] for r in reviews) / len(reviews)
        lines = [f"📊 <b>Отзывы ({len(reviews)}) | Средняя: {avg:.1f}⭐</b>\n"]
        for r in reviews[-20:][::-1]:
            lines.append(f"{'⭐'*r['rating']} @{r['username']}\n💬 {r['text'][:100]}\n")
        text = "\n".join(lines)
        if len(text) > 4000: text = text[:4000] + "\n…"
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=back_kb())

    # ── broadcast ──
    elif action == "adm_broadcast":
        ctx.user_data["adm_action"] = "broadcast"
        await q.edit_message_text(
            "📢 Введи текст рассылки (отправится всем пользователям):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="adm_back")]])
        )

    # ── banned list ──
    elif action == "adm_banned":
        banned = data.get("banned", [])
        users  = data.get("users", {})
        if not banned:
            await q.edit_message_text("✅ Забаненных пользователей нет.", reply_markup=back_kb()); return
        lines = [f"🚫 <b>Забаненные ({len(banned)}):</b>\n"]
        for bid in banned:
            u = users.get(str(bid), {})
            name = f"@{u['username']}" if u.get("username") else u.get("first_name") or "—"
            lines.append(f"• {name} | <code>{bid}</code>")
        await q.edit_message_text("\n".join(lines), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="adm_back")]]))

    # ── add admin ──
    elif action == "adm_addadmin":
        ctx.user_data["adm_action"] = "addadmin"
        await q.edit_message_text("➕ Введи Telegram ID нового админа:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="adm_back")]]))

    # ── remove admin ──
    elif action == "adm_removeadmin":
        ctx.user_data["adm_action"] = "removeadmin"
        await q.edit_message_text("➖ Введи Telegram ID админа для удаления:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="adm_back")]]))

    # ── list admins ──
    elif action == "adm_listadmins":
        admins = data.get("admins", [])
        lines  = ["👮 <b>Список админов:</b>\n"]
        for aid in admins:
            mark = " 👑" if aid == SUPER_ADMIN else ""
            lines.append(f"• <code>{aid}</code>{mark}")
        await q.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=back_kb())

    # ── back ──
    elif action == "adm_back":
        await q.edit_message_text("🔧 <b>Панель админа</b>", parse_mode="HTML", reply_markup=admin_kb())

async def admin_free_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handles broadcast / addadmin / removeadmin free-text input."""
    if not is_admin(update.effective_user.id): return
    action = ctx.user_data.get("adm_action")
    if not action: return

    text = update.message.text.strip()
    data = load()

    if action == "broadcast":
        users = data.get("users", {})
        ok = fail = 0
        for uid in users:
            if int(uid) in data.get("banned", []): continue
            try:
                await ctx.bot.send_message(int(uid),
                    f"📢 <b>Сообщение от администрации:</b>\n\n{text}", parse_mode="HTML")
                ok += 1
            except: fail += 1
        ctx.user_data.pop("adm_action", None)
        await update.message.reply_text(
            f"✅ Рассылка завершена.\n📤 Отправлено: {ok} | ❌ Ошибок: {fail}",
            reply_markup=main_kb(update.effective_user.id))

    elif action == "addadmin":
        try:
            nid = int(text)
            if nid not in data["admins"]:
                data["admins"].append(nid); save(data)
                await update.message.reply_text(f"✅ <code>{nid}</code> назначен админом.", parse_mode="HTML",
                    reply_markup=main_kb(update.effective_user.id))
            else:
                await update.message.reply_text("⚠️ Уже является админом.",
                    reply_markup=main_kb(update.effective_user.id))
        except ValueError:
            await update.message.reply_text("❌ Введи числовой Telegram ID.")
        ctx.user_data.pop("adm_action", None)

    elif action == "removeadmin":
        try:
            rid = int(text)
            if rid == SUPER_ADMIN:
                await update.message.reply_text("⛔ Нельзя удалить супер-админа.",
                    reply_markup=main_kb(update.effective_user.id))
            elif rid in data["admins"]:
                data["admins"].remove(rid); save(data)
                await update.message.reply_text(f"✅ <code>{rid}</code> удалён из админов.", parse_mode="HTML",
                    reply_markup=main_kb(update.effective_user.id))
            else:
                await update.message.reply_text("⚠️ Не найден в списке админов.",
                    reply_markup=main_kb(update.effective_user.id))
        except ValueError:
            await update.message.reply_text("❌ Введи числовой Telegram ID.")
        ctx.user_data.pop("adm_action", None)

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    review_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^⭐ Оставить отзыв$"), review_start),
                      CallbackQueryHandler(review_rating_cb, pattern="^rate_[1-5]$")],
        states={
            REVIEW_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, review_save),
                          CallbackQueryHandler(review_cancel, pattern="^review_cancel$")],
        },
        fallbacks=[CallbackQueryHandler(review_cancel, pattern="^review_cancel$")],
        per_message=False,
    )

    user_msg_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📩 Написать админу$"), user_msg_start)],
        states={
            USER_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_msg_send),
                       CallbackQueryHandler(msg_cancel, pattern="^msg_cancel$")],
        },
        fallbacks=[CallbackQueryHandler(msg_cancel, pattern="^msg_cancel$")],
        per_message=False,
    )

    reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reply_btn, pattern="^reply_\\d+$")],
        states={
            REPLY_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, reply_send),
                         CallbackQueryHandler(reply_cancel, pattern="^reply_cancel$")],
        },
        fallbacks=[CallbackQueryHandler(reply_cancel, pattern="^reply_cancel$")],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(review_conv)
    app.add_handler(user_msg_conv)
    app.add_handler(reply_conv)
    app.add_handler(MessageHandler(filters.Regex("^📋 Частые вопросы$"),     faq))
    app.add_handler(MessageHandler(filters.Regex("^🌐 Контакты и соцсети$"), contacts))
    app.add_handler(MessageHandler(filters.Regex("^🔧 Панель админа$"),      admin_panel))
    app.add_handler(CallbackQueryHandler(admin_cb,   pattern="^adm_"))
    app.add_handler(CallbackQueryHandler(ban_btn,    pattern="^ban_\\d+$"))
    app.add_handler(CallbackQueryHandler(unban_btn,  pattern="^unban_\\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_free_text))

    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
