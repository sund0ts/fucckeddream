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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8653082594:AAGvap2Z7L_v308Wej6Jk3yWYaQDdei9_F0")
SUPER_ADMIN_ID = 7512529826
DATA_FILE = "data.json"

# Conversation states
REVIEW_WAITING_TEXT = 1
ADMIN_MSG_WAITING   = 2
BROADCAST_WAITING   = 3

# ─── DATA HELPERS ─────────────────────────────────────────────────────────────
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "reviews": [], "admins": [SUPER_ADMIN_ID]}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def register_user(user):
    data = load_data()
    uid = str(user.id)
    if uid not in data["users"]:
        data["users"][uid] = {
            "id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
            "joined": datetime.now().isoformat()
        }
        save_data(data)
    return data

def is_admin(user_id: int) -> bool:
    data = load_data()
    return user_id == SUPER_ADMIN_ID or user_id in data.get("admins", [])

# ─── KEYBOARDS ────────────────────────────────────────────────────────────────
def main_menu_kb(user_id: int) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton("⭐ Оставить отзыв"), KeyboardButton("📋 Частые вопросы")],
        [KeyboardButton("🌐 Контакты и соцсети"), KeyboardButton("📩 Написать админу")],
    ]
    if is_admin(user_id):
        buttons.append([KeyboardButton("🔧 Панель админа")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def stars_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⭐", callback_data="rate_1"),
        InlineKeyboardButton("⭐⭐", callback_data="rate_2"),
        InlineKeyboardButton("⭐⭐⭐", callback_data="rate_3"),
        InlineKeyboardButton("⭐⭐⭐⭐", callback_data="rate_4"),
        InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data="rate_5"),
    ]])

def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Все пользователи", callback_data="adm_users")],
        [InlineKeyboardButton("📊 Все отзывы", callback_data="adm_reviews")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="adm_broadcast")],
        [InlineKeyboardButton("➕ Добавить админа", callback_data="adm_addadmin")],
        [InlineKeyboardButton("➖ Удалить админа", callback_data="adm_removeadmin")],
        [InlineKeyboardButton("👮 Список админов", callback_data="adm_listadmins")],
    ])

# ─── /start ───────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    name = user.first_name or "друг"
    await update.message.reply_text(
        f"👋 Привет, {name}!\n\n"
        "Я — бот хостинга <b>Railway</b>. Здесь ты можешь:\n"
        "• Оставить отзыв о нас ⭐\n"
        "• Посмотреть частые вопросы 📋\n"
        "• Связаться с нами 📩\n"
        "• Перейти в наш Telegram-канал 🌐\n\n"
        "Выбери нужный пункт в меню ниже 👇",
        parse_mode="HTML",
        reply_markup=main_menu_kb(user.id)
    )

# ─── REVIEW FLOW ──────────────────────────────────────────────────────────────
async def review_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⭐ <b>Оставить отзыв</b>\n\nВыбери оценку:",
        parse_mode="HTML",
        reply_markup=stars_kb()
    )

async def review_rating_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rating = int(query.data.split("_")[1])
    ctx.user_data["review_rating"] = rating
    stars = "⭐" * rating
    await query.edit_message_text(
        f"Ты выбрал: {stars}\n\nТеперь напиши свой отзыв текстом:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отмена", callback_data="review_cancel")
        ]])
    )
    return REVIEW_WAITING_TEXT

async def review_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    rating = ctx.user_data.get("review_rating", 5)
    stars = "⭐" * rating

    data = load_data()
    data["reviews"].append({
        "user_id": user.id,
        "username": user.username or user.first_name,
        "rating": rating,
        "text": text,
        "date": datetime.now().isoformat()
    })
    save_data(data)

    await update.message.reply_text(
        f"✅ Спасибо за отзыв!\n\nТвоя оценка: {stars}\n📝 «{text}»",
        reply_markup=main_menu_kb(user.id)
    )

    # Notify admins
    admin_text = (
        f"📬 <b>Новый отзыв!</b>\n"
        f"👤 @{user.username or user.first_name} (ID: {user.id})\n"
        f"Оценка: {stars}\n"
        f"💬 {text}"
    )
    for admin_id in data.get("admins", []):
        try:
            await ctx.bot.send_message(admin_id, admin_text, parse_mode="HTML")
        except Exception:
            pass

    return ConversationHandler.END

async def review_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Отзыв отменён.")
    return ConversationHandler.END

# ─── FAQ ──────────────────────────────────────────────────────────────────────
async def faq_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 <b>Частые вопросы</b>\n\n"
        "❓ <b>Как с вами связаться?</b>\n"
        "Нажми «📩 Написать админу» и напиши свой вопрос — мы ответим в ближайшее время.\n\n"
        "❓ <b>Как оставить отзыв?</b>\n"
        "Нажми «⭐ Оставить отзыв» в меню.\n\n"
        "❓ <b>Где вы находитесь?</b>\n"
        "Мы работаем онлайн и принимаем клиентов со всего мира.\n\n"
        "❓ <b>Как отписаться от рассылки?</b>\n"
        "Напиши админу «отписаться» — мы исключим тебя из рассылок."
    )
    await update.message.reply_text(text, parse_mode="HTML",
                                    reply_markup=main_menu_kb(update.effective_user.id))

# ─── CONTACTS ─────────────────────────────────────────────────────────────────
async def contacts_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📣 Telegram-канал", url="https://t.me/macanxyecocina")
    ]])
    await update.message.reply_text(
        "🌐 <b>Контакты и соцсети</b>\n\nВыбери нужную платформу:",
        parse_mode="HTML",
        reply_markup=kb
    )

# ─── WRITE TO ADMIN ───────────────────────────────────────────────────────────
async def write_admin_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📩 Напиши своё сообщение, и мы передадим его администратору:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отмена", callback_data="msg_cancel")
        ]])
    )
    return ADMIN_MSG_WAITING

async def write_admin_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    data = load_data()

    msg = (
        f"📩 <b>Сообщение от пользователя</b>\n"
        f"👤 @{user.username or user.first_name} (ID: <code>{user.id}</code>)\n\n"
        f"💬 {text}"
    )
    sent = False
    for admin_id in data.get("admins", []):
        try:
            await ctx.bot.send_message(admin_id, msg, parse_mode="HTML")
            sent = True
        except Exception:
            pass

    if sent:
        await update.message.reply_text(
            "✅ Сообщение отправлено! Мы ответим в ближайшее время.",
            reply_markup=main_menu_kb(user.id)
        )
    else:
        await update.message.reply_text(
            "⚠️ Не удалось отправить сообщение. Попробуй позже.",
            reply_markup=main_menu_kb(user.id)
        )
    return ConversationHandler.END

async def msg_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Отменено.")
    return ConversationHandler.END

# ─── ADMIN PANEL ──────────────────────────────────────────────────────────────
async def admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await update.message.reply_text(
        "🔧 <b>Панель админа</b>",
        parse_mode="HTML",
        reply_markup=admin_panel_kb()
    )

async def admin_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("⛔ Нет доступа.")
        return

    action = query.data

    if action == "adm_users":
        data = load_data()
        users = data.get("users", {})
        if not users:
            await query.edit_message_text("👥 Пользователей пока нет.")
            return
        lines = [f"👥 <b>Все пользователи ({len(users)}):</b>\n"]
        for uid, u in list(users.items())[:50]:  # limit 50
            uname = f"@{u['username']}" if u.get("username") else u.get("first_name", "—")
            lines.append(f"• {uname} (ID: <code>{u['id']}</code>)")
        await query.edit_message_text(
            "\n".join(lines), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="adm_back")
            ]])
        )

    elif action == "adm_reviews":
        data = load_data()
        reviews = data.get("reviews", [])
        if not reviews:
            await query.edit_message_text(
                "📊 Отзывов пока нет.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="adm_back")
                ]])
            )
            return
        avg = sum(r["rating"] for r in reviews) / len(reviews)
        lines = [f"📊 <b>Отзывы ({len(reviews)}) | Средняя оценка: {avg:.1f}⭐</b>\n"]
        for r in reviews[-20:][::-1]:
            stars = "⭐" * r["rating"]
            lines.append(f"{stars} @{r['username']}\n💬 {r['text'][:80]}\n")
        await query.edit_message_text(
            "\n".join(lines), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="adm_back")
            ]])
        )

    elif action == "adm_broadcast":
        ctx.user_data["adm_action"] = "broadcast"
        await query.edit_message_text(
            "📢 Введи текст рассылки (отправится всем пользователям):",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data="adm_back")
            ]])
        )
        return  # will be handled by broadcast_text handler

    elif action == "adm_addadmin":
        ctx.user_data["adm_action"] = "addadmin"
        await query.edit_message_text(
            "➕ Введи Telegram ID нового админа:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data="adm_back")
            ]])
        )

    elif action == "adm_removeadmin":
        ctx.user_data["adm_action"] = "removeadmin"
        await query.edit_message_text(
            "➖ Введи Telegram ID админа для удаления:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Отмена", callback_data="adm_back")
            ]])
        )

    elif action == "adm_listadmins":
        data = load_data()
        admins = data.get("admins", [])
        lines = ["👮 <b>Список админов:</b>\n"]
        for aid in admins:
            marker = " 👑 (супер)" if aid == SUPER_ADMIN_ID else ""
            lines.append(f"• <code>{aid}</code>{marker}")
        await query.edit_message_text(
            "\n".join(lines), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="adm_back")
            ]])
        )

    elif action == "adm_back":
        await query.edit_message_text(
            "🔧 <b>Панель админа</b>",
            parse_mode="HTML",
            reply_markup=admin_panel_kb()
        )

async def admin_text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handles free-text input for admin actions (broadcast, add/remove admin)."""
    if not is_admin(update.effective_user.id):
        return

    action = ctx.user_data.get("adm_action")
    if not action:
        return

    text = update.message.text.strip()
    data = load_data()

    if action == "broadcast":
        users = data.get("users", {})
        ok = fail = 0
        for uid in users:
            try:
                await ctx.bot.send_message(int(uid), f"📢 <b>Сообщение от администрации:</b>\n\n{text}", parse_mode="HTML")
                ok += 1
            except Exception:
                fail += 1
        ctx.user_data.pop("adm_action", None)
        await update.message.reply_text(
            f"✅ Рассылка завершена.\n📤 Отправлено: {ok}\n❌ Ошибок: {fail}",
            reply_markup=main_menu_kb(update.effective_user.id)
        )

    elif action == "addadmin":
        try:
            new_id = int(text)
            if new_id not in data["admins"]:
                data["admins"].append(new_id)
                save_data(data)
                await update.message.reply_text(f"✅ Пользователь <code>{new_id}</code> назначен админом.", parse_mode="HTML",
                                                reply_markup=main_menu_kb(update.effective_user.id))
            else:
                await update.message.reply_text("⚠️ Этот пользователь уже админ.",
                                                reply_markup=main_menu_kb(update.effective_user.id))
        except ValueError:
            await update.message.reply_text("❌ Неверный ID. Введи числовой Telegram ID.")
        ctx.user_data.pop("adm_action", None)

    elif action == "removeadmin":
        try:
            rem_id = int(text)
            if rem_id == SUPER_ADMIN_ID:
                await update.message.reply_text("⛔ Нельзя удалить супер-админа.",
                                                reply_markup=main_menu_kb(update.effective_user.id))
            elif rem_id in data["admins"]:
                data["admins"].remove(rem_id)
                save_data(data)
                await update.message.reply_text(f"✅ Пользователь <code>{rem_id}</code> удалён из админов.", parse_mode="HTML",
                                                reply_markup=main_menu_kb(update.effective_user.id))
            else:
                await update.message.reply_text("⚠️ Этого пользователя нет в списке админов.",
                                                reply_markup=main_menu_kb(update.effective_user.id))
        except ValueError:
            await update.message.reply_text("❌ Неверный ID.")
        ctx.user_data.pop("adm_action", None)

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Review conversation
    review_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^⭐ Оставить отзыв$"), review_start),
            CallbackQueryHandler(review_rating_cb, pattern="^rate_[1-5]$"),
        ],
        states={
            REVIEW_WAITING_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, review_text),
                CallbackQueryHandler(review_cancel, pattern="^review_cancel$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(review_cancel, pattern="^review_cancel$")],
        per_message=False,
    )

    # Write to admin conversation
    msg_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📩 Написать админу$"), write_admin_start),
        ],
        states={
            ADMIN_MSG_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, write_admin_text),
                CallbackQueryHandler(msg_cancel, pattern="^msg_cancel$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(msg_cancel, pattern="^msg_cancel$")],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(review_conv)
    app.add_handler(msg_conv)
    app.add_handler(MessageHandler(filters.Regex("^📋 Частые вопросы$"), faq_handler))
    app.add_handler(MessageHandler(filters.Regex("^🌐 Контакты и соцсети$"), contacts_handler))
    app.add_handler(MessageHandler(filters.Regex("^🔧 Панель админа$"), admin_panel))
    app.add_handler(CallbackQueryHandler(admin_cb, pattern="^adm_"))
    app.add_handler(CallbackQueryHandler(review_rating_cb, pattern="^rate_[1-5]$"))

    # Catch admin free-text actions
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler))

    logger.info("Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
