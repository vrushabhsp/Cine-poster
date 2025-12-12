import logging
import urllib.parse
import re
import os
from threading import Thread
from flask import Flask

from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    InlineQueryResultPhoto, 
    InlineQueryResultArticle, 
    InputTextMessageContent,
    WebAppInfo,
    CallbackQuery
)
from pymongo import MongoClient
from bson.objectid import ObjectId

# --- CONFIGURATION ---
MONGO_URI = "mongodb+srv://orgdriphy:ttkCwzgb3yqCdAXN@cluster0.soas0.mongodb.net/?retryWrites=true&w=majority"
WEB_APP_BASE = "https://cinehuntsapp.vercel.app/search/"
BOT_TOKEN = "7142601197:AAEc9A-yL-wjuSm67qzDiOI1CG-zjwnLDcI"
API_ID = 23547013
API_HASH = "ab5590a345a6df439123cfd685abe35b"
BOT_USERNAME = "cinehuntsbot"
ADMIN_USER_ID = 6887525311

# Destination Channels
CHANNEL_IDS = {
    "movies": -1001821878700,
    "series": -1001547506866,
    "anime": -1002068837332,
    "updates1": -1002276569937,
    "updates2": -1002285116071
} 

# --- GLOBAL CACHE ---
BULK_CACHE = {}

# --- DATABASE ---
cluster = MongoClient(MONGO_URI)
poster_col = cluster["Testing"]["Movies"]

# --- BOT ---
app = Client("cinehunts_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# --- HELPER: STAR RATING ---
def get_star_rating(rating):
    try:
        score = float(rating)
        full_stars = int(score)
        return "⭐" * full_stars + f" ({rating}/5)"
    except:
        return "N/A"

# --- HELPER: PREMIUM CAPTION ---
def generate_premium_caption(doc):
    title = doc.get("title", "Unknown Title").title()
    platform = doc.get("platform", "Unknown").replace("jiohotstar", "JioHotstar").title()
    type_ = doc.get("type", "Content").upper()
    year = doc.get("release_year", "N/A")
    rating = doc.get("user_rating", "N/A")
    genres_list = doc.get("genres", [])
    
    if isinstance(genres_list, list):
        genres = " | ".join(genres_list)
    else:
        genres = str(genres_list)

    stars = get_star_rating(rating)
    safe_title = re.sub(r'\W+', '', title)
    hashtags = f"#{safe_title} #{platform.replace(' ', '')} #{type_.replace(' ', '')} #CineHunts"

    caption = f"""
🎬 <b>{title}</b>

📅 <b>Year:</b> <code>{year}</code>
🌟 <b>Rating:</b> {stars}
🎭 <b>Genre:</b> {genres}
📺 <b>Platform:</b> <code>{platform}</code>
🎞 <b>Type:</b> <code>{type_}</code>

━━━━━━━━━━━━━━━━━━━━
👇 <b><i>Click below to watch or download</i></b>
━━━━━━━━━━━━━━━━━━━━

{hashtags}
"""
    return caption

# --- HELPER: SEARCH FILTER ---
def build_search_filter(query):
    query = query.strip()
    mongo_filter = {}
    year_match = re.search(r'\b(19|20)\d{2}\b', query)
    
    if year_match:
        year = int(year_match.group(0))
        mongo_filter["release_year"] = year
        title_part = query.replace(str(year), "").strip()
    else:
        title_part = query

    if title_part:
        mongo_filter["title"] = {"$regex": title_part, "$options": "i"}
    return mongo_filter

# --- 1. USER SEARCH (/search) ---
@app.on_message(filters.command("search"))
async def search_command(client, message):
    query = " ".join(message.command[1:]).strip()
    if not query:
        return await message.reply("🔍 <b>Usage:</b> <code>/search Movie Name</code>", parse_mode=enums.ParseMode.HTML)

    search_filter = build_search_filter(query)
    results = list(poster_col.find(search_filter).limit(5))

    if not results:
        return await message.reply("❌ <b>No results found.</b>", parse_mode=enums.ParseMode.HTML)

    await message.reply(f"🔎 <b>Found {len(results)} results for:</b> <code>{query}</code>", parse_mode=enums.ParseMode.HTML)

    for doc in results:
        caption = generate_premium_caption(doc)
        # PRIVATE CHAT: Use WebAppInfo (Opens Popup)
        web_link = WEB_APP_BASE + urllib.parse.quote(doc.get("title", ""))
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Download / Watch Now", web_app=WebAppInfo(url=web_link))]])
        
        poster = doc.get("image")
        if poster:
            try:
                await message.reply_photo(photo=poster, caption=caption, parse_mode=enums.ParseMode.HTML, reply_markup=buttons)
            except:
                await message.reply(caption, parse_mode=enums.ParseMode.HTML, reply_markup=buttons)
        else:
            await message.reply(caption, parse_mode=enums.ParseMode.HTML, reply_markup=buttons)

# --- 2. ADMIN SINGLE POST (/post) ---
@app.on_message(filters.command("post") & filters.user(ADMIN_USER_ID))
async def post_command(client, message):
    query = " ".join(message.command[1:]).strip()
    if not query:
        return await message.reply("⚠️ Usage: `/post Movie Name`")

    search_filter = build_search_filter(query)
    doc = poster_col.find_one(search_filter)

    if not doc:
        return await message.reply("❌ Content not found in Database.")

    doc_id = str(doc["_id"])
    caption = generate_premium_caption(doc)
    poster = doc.get("image")

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Movies", callback_data=f"tog|movies|{doc_id}"), InlineKeyboardButton("❌ Series", callback_data=f"tog|series|{doc_id}")],
        [InlineKeyboardButton("❌ Anime", callback_data=f"tog|anime|{doc_id}"), InlineKeyboardButton("❌ Upd 1", callback_data=f"tog|updates1|{doc_id}"), InlineKeyboardButton("❌ Upd 2", callback_data=f"tog|updates2|{doc_id}")],
        [InlineKeyboardButton("🚀 SEND TO SELECTED", callback_data=f"send|{doc_id}")]
    ])

    await message.reply_photo(photo=poster, caption=f"<b>📢 SINGLE POST PREVIEW</b>\n\n{caption}", parse_mode=enums.ParseMode.HTML, reply_markup=buttons)

# --- 3. ADMIN BULK POST (/bulk) ---
@app.on_message(filters.command("bulk") & filters.user(ADMIN_USER_ID))
async def bulk_post_command(client, message):
    text = message.text.replace("/bulk", "").strip()
    if not text:
        return await message.reply("⚠️ Usage: `/bulk Iron Man, Thor, Hulk` (comma separated)")

    names = [n.strip() for n in text.split(",") if n.strip()]
    found_docs = []
    not_found_names = []
    
    for name in names:
        search_filter = build_search_filter(name)
        doc = poster_col.find_one(search_filter)
        if doc:
            found_docs.append(doc)
        else:
            not_found_names.append(name)
            
    if not found_docs:
        return await message.reply("❌ None of those movies were found.")

    found_titles = [f"✅ {d.get('title')}" for d in found_docs]
    preview_text = "<b>📢 BULK POST MANAGER</b>\n\n" + "\n".join(found_titles)
    
    if not_found_names:
        preview_text += "\n\n❌ <b>Not Found:</b>\n" + "\n".join(not_found_names)

    preview_text += "\n\n👇 <i>Select channels below to send ALL valid posters:</i>"

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Movies", callback_data="bulk_tog|movies"), InlineKeyboardButton("❌ Series", callback_data="bulk_tog|series")],
        [InlineKeyboardButton("❌ Anime", callback_data="bulk_tog|anime"), InlineKeyboardButton("❌ Upd 1", callback_data="bulk_tog|updates1"), InlineKeyboardButton("❌ Upd 2", callback_data="bulk_tog|updates2")],
        [InlineKeyboardButton(f"🚀 SEND ALL ({len(found_docs)})", callback_data="bulk_send")]
    ])

    sent_msg = await message.reply(preview_text, reply_markup=buttons, parse_mode=enums.ParseMode.HTML)
    BULK_CACHE[sent_msg.id] = found_docs

# --- 4. CALLBACK HANDLER (LOGIC CORE) ---
@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    data = callback_query.data.split("|")
    action = data[0]

    # === TOGGLE CHECKBOXES ===
    if action in ["tog", "bulk_tog"]:
        current_keyboard = callback_query.message.reply_markup.inline_keyboard
        new_keyboard = []
        for row in current_keyboard:
            new_row = []
            for btn in row:
                if btn.callback_data == callback_query.data:
                    new_text = btn.text.replace("❌", "✅") if "❌" in btn.text else btn.text.replace("✅", "❌")
                    new_row.append(InlineKeyboardButton(new_text, callback_data=btn.callback_data))
                else:
                    new_row.append(btn)
            new_keyboard.append(new_row)
        await callback_query.message.edit_reply_markup(InlineKeyboardMarkup(new_keyboard))
        await callback_query.answer()

    # === SINGLE SEND (TO CHANNELS) ===
    elif action == "send":
        doc_id = data[1]
        doc = poster_col.find_one({"_id": ObjectId(doc_id)})
        
        selected_channels = []
        for row in callback_query.message.reply_markup.inline_keyboard:
            for btn in row:
                if "✅" in btn.text:
                    key = btn.callback_data.split("|")[1]
                    if key in CHANNEL_IDS: selected_channels.append(CHANNEL_IDS[key])

        if not selected_channels: return await callback_query.answer("⚠️ No channels selected!", show_alert=True)
        if not doc: return await callback_query.answer("Error: Data lost.", show_alert=True)

        await callback_query.answer("🚀 Sending...", show_alert=False)
        caption = generate_premium_caption(doc)
        
        # FIX: Use STANDARD URL for Channels so the specific movie loads
        web_link = WEB_APP_BASE + urllib.parse.quote(doc["title"])
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Download / Watch Now", url=web_link)]])
        
        for chat_id in selected_channels:
            try:
                if doc.get("image"):
                    await client.send_photo(chat_id, doc["image"], caption=caption, parse_mode=enums.ParseMode.HTML, reply_markup=markup)
                else:
                    await client.send_message(chat_id, caption, parse_mode=enums.ParseMode.HTML, reply_markup=markup)
            except Exception as e:
                print(f"Failed to send to {chat_id}: {e}")
        
        await callback_query.message.edit_caption("✅ <b>Sent Successfully!</b>", parse_mode=enums.ParseMode.HTML)

    # === BULK SEND (TO CHANNELS) ===
    elif action == "bulk_send":
        msg_id = callback_query.message.id
        docs_to_send = BULK_CACHE.get(msg_id)

        if not docs_to_send: return await callback_query.answer("⚠️ Session expired.", show_alert=True)

        selected_channels = []
        for row in callback_query.message.reply_markup.inline_keyboard:
            for btn in row:
                if "✅" in btn.text:
                    key = btn.callback_data.split("|")[1]
                    if key in CHANNEL_IDS: selected_channels.append(CHANNEL_IDS[key])

        if not selected_channels: return await callback_query.answer("⚠️ No channels selected!", show_alert=True)

        await callback_query.answer(f"🚀 Sending {len(docs_to_send)} posts...", show_alert=False)
        await callback_query.message.edit_text("⏳ <b>Sending...</b>", parse_mode=enums.ParseMode.HTML)

        count = 0
        for doc in docs_to_send:
            caption = generate_premium_caption(doc)
            
            # FIX: Use STANDARD URL for Channels so the specific movie loads
            web_link = WEB_APP_BASE + urllib.parse.quote(doc["title"])
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Download / Watch Now", url=web_link)]])
            
            for chat_id in selected_channels:
                try:
                    if doc.get("image"):
                        await client.send_photo(chat_id, doc["image"], caption=caption, parse_mode=enums.ParseMode.HTML, reply_markup=markup)
                    else:
                        await client.send_message(chat_id, caption, parse_mode=enums.ParseMode.HTML, reply_markup=markup)
                except Exception as e:
                    print(f"Failed bulk send: {e}")
            count += 1
        
        del BULK_CACHE[msg_id]
        await callback_query.message.edit_text(f"✅ <b>Sent {count} posts!</b>", parse_mode=enums.ParseMode.HTML)

# --- 5. INLINE SEARCH (ANY CHAT) ---
@app.on_inline_query()
async def inline_search(client, inline_query):
    query = inline_query.query.strip()
    if not query: return
    search_filter = build_search_filter(query)
    db_results = list(poster_col.find(search_filter).limit(20))
    results = []
    for doc in db_results:
        title = doc.get("title", "Unknown")
        poster = doc.get("image")
        caption = generate_premium_caption(doc)
        
        # INLINE: Use WebAppInfo (Opens Popup)
        web_link = WEB_APP_BASE + urllib.parse.quote(title)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Download Now", web_app=WebAppInfo(url=web_link))]])
        
        if poster:
            results.append(InlineQueryResultPhoto(title=title, photo_url=poster, thumb_url=poster, caption=caption, parse_mode=enums.ParseMode.HTML, reply_markup=keyboard))
        else:
            results.append(InlineQueryResultArticle(title=title, input_message_content=InputTextMessageContent(caption, parse_mode=enums.ParseMode.HTML), reply_markup=keyboard))
    await inline_query.answer(results, cache_time=10)

# --- FAKE WEB SERVER FOR RENDER ---
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "Bot is running!"

def run_web_server():
    # Render assigns the port automatically in the PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# Start the web server in a separate thread so it doesn't block the bot
if __name__ == "__main__":
    t = Thread(target=run_web_server)
    t.daemon = True
    t.start()
    
    print("✅ Bot is starting on Render...")
    app.run()
