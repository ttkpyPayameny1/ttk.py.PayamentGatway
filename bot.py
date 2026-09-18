"""
NIKAN EARN - DEMO/SIMULATION TELEGRAM BOT
Framework: aiogram 3.x
Database: SQLite

IMPORTANT:
- This build is a DEMO/SIMULATION.
- It does not process real money, real bKash/Nagad payments, or real crypto transfers.
- Replace BOT_TOKEN with your BotFather token.
- ADMIN_ID is set to 2037461288 as requested.
"""

import asyncio
import re
import sqlite3
from datetime import datetime, timedelta, time
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    Message
)

BOT_TOKEN = "8983512458:AAGUw0goCNIUSUeJxzYSX1qKnDjz9GdzmiA"
ADMIN_ID = 2037461288
DB_FILE = "nikan_demo.db"

# Demo configuration
DEPOSIT_GATEWAY_URL = "https://example.com/payment-gateway"
BINANCE_DEMO_ADDRESS = "0xade76b7f023c3ded14850293ea26e477edbdd048"
USDT_RATE = 125
DEPOSIT_MIN = 50
DEPOSIT_MAX = 10000
WITHDRAW_MIN = 100
WITHDRAW_MAX = 25000
BONUS_DAILY = 5

PLANS = {
    1: 300, 2: 500, 3: 1000, 4: 2000, 5: 3000, 6: 5000,
    7: 7500, 8: 10000, 9: 15000, 10: 20000, 11: 30000, 12: 50000
}

db = sqlite3.connect(DB_FILE)
db.row_factory = sqlite3.Row

def init_db():
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        name TEXT,
        username TEXT,
        main_balance REAL DEFAULT 0,
        deposit_balance REAL DEFAULT 0,
        bonus_balance REAL DEFAULT 0,
        referral_balance REAL DEFAULT 0,
        total_earnings REAL DEFAULT 0,
        banned INTEGER DEFAULT 0,
        last_bonus TEXT,
        referrer_id INTEGER
    );

    CREATE TABLE IF NOT EXISTS deposits(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        method TEXT,
        amount REAL,
        txid TEXT,
        order_no TEXT,
        status TEXT DEFAULT 'PENDING',
        reason TEXT DEFAULT '',
        created_at TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS withdrawals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        method TEXT,
        account TEXT,
        amount REAL,
        status TEXT DEFAULT 'PENDING',
        reason TEXT DEFAULT '',
        created_at TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS plans(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        vip INTEGER,
        amount REAL,
        activated_at TEXT,
        expires_at TEXT,
        last_claim_date TEXT,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS earnings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        plan_id INTEGER,
        amount REAL,
        claim_date TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS bonus_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        created_at TEXT
    );
    """)
    db.commit()

def now():
    return datetime.now()

def get_user(user_id):
    return db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

def ensure_user(user_id, name, username, referrer_id=None):
    u = get_user(user_id)
    if not u:
        db.execute(
            "INSERT INTO users(id,name,username,referrer_id) VALUES(?,?,?,?)",
            (user_id, name or "", username or "", referrer_id)
        )
        db.commit()
    else:
        db.execute(
            "UPDATE users SET name=?, username=? WHERE id=?",
            (name or "", username or "", user_id)
        )
        db.commit()
    return get_user(user_id)

def money(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 ফান্ড ডিপোজিট", callback_data="deposit")],
        [InlineKeyboardButton(text="👤 একাউন্ট", callback_data="account"),
         InlineKeyboardButton(text="💸 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton(text="👥 Referral", callback_data="referral"),
         InlineKeyboardButton(text="📊 Daily Earnings", callback_data="earnings")],
        [InlineKeyboardButton(text="🎁 Bonus Center", callback_data="bonus"),
         InlineKeyboardButton(text="💎 Available Plans", callback_data="plans")],
        [InlineKeyboardButton(text="🧾 Transaction History", callback_data="history")],
        [InlineKeyboardButton(text="🆘 Help & Support", callback_data="help")]
    ])

class DepositState(StatesGroup):
    amount = State()
    binance_amount = State()
    txid = State()

class WithdrawState(StatesGroup):
    account = State()
    amount = State()

def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ বাতিল", callback_data="cancel")]
    ])

def plan_kb():
    rows = []
    row = []
    for i in range(1, 13):
        row.append(InlineKeyboardButton(text=f"VIP {i}", callback_data=f"plan:{i}"))
        if len(row) == 4:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_deposit_kb(dep_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Approve ✅", callback_data=f"da:{dep_id}")],
        [InlineKeyboardButton(text="Reject ❌", callback_data=f"dr:{dep_id}")]
    ])

def admin_withdraw_kb(wid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Approve ✅", callback_data=f"wa:{wid}")],
        [InlineKeyboardButton(text="Reject ❌", callback_data=f"wr:{wid}")]
    ])

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: Message):
    # Optional referral: /start 123456
    ref = None
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2 and parts[1].isdigit():
        ref = int(parts[1])
        if ref == message.from_user.id:
            ref = None
    ensure_user(
        message.from_user.id,
        message.from_user.full_name,
        message.from_user.username,
        ref
    )
    await message.answer(
        "🚀 <b>NIKAN</b>\n\nস্বাগতম! নিচের মেনু থেকে একটি অপশন নির্বাচন করুন।",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )

@dp.message(Command("menu"))
async def menu_cmd(message: Message):
    ensure_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await message.answer("🏠 <b>Main Menu</b>", reply_markup=main_menu(), parse_mode="HTML")

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await show_help(message)

@dp.callback_query(F.data == "menu")
async def menu_cb(c: CallbackQuery):
    await c.message.edit_text("🏠 <b>Main Menu</b>", reply_markup=main_menu(), parse_mode="HTML")
    await c.answer()

@dp.callback_query(F.data == "cancel")
async def cancel_cb(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text("❌ অপারেশন বাতিল করা হয়েছে।", reply_markup=main_menu())
    await c.answer()

# ---------- Deposit ----------
@dp.callback_query(F.data == "deposit")
async def deposit_cb(c: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 বিকাশ", callback_data="dep:bKash"),
         InlineKeyboardButton(text="💠 নগদ", callback_data="dep:Nagad")],
        [InlineKeyboardButton(text="🟡 Binance", callback_data="dep:Binance")],
        [InlineKeyboardButton(text="❌ বাতিল", callback_data="cancel")]
    ])
    await c.message.edit_text(
        "🔐 <b>ফান্ড ডিপোজিট</b>\n━━━━━━━━━━━━━━━━━━\n"
        "📲 নিচের অপশন থেকে একটি মেথড নির্বাচন করুন।👇",
        reply_markup=kb, parse_mode="HTML"
    )
    await c.answer()

@dp.callback_query(F.data.in_({"dep:bKash", "dep:Nagad"}))
async def fiat_dep(c: CallbackQuery, state: FSMContext):
    method = c.data.split(":")[1]
    await state.update_data(method=method)
    await state.set_state(DepositState.amount)
    await c.message.edit_text(
        f"💳 <b>{method}</b>\n\n"
        "ডিপোজিট লিমিট রয়েছে: 0/3\n\n"
        "আপনি কত টাকা ডিপোজিট করতে চান?\n"
        "সর্বনিম্ন ৫০ — সর্বোচ্চ ১০০০০\n"
        "অনুগ্রহ করে টাকার পরিমাণ লিখুন:",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await c.answer()

@dp.message(DepositState.amount)
async def fiat_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
    except ValueError:
        await message.answer("⚠️ শুধু সংখ্যায় টাকার পরিমাণ লিখুন।", reply_markup=cancel_kb())
        return
    if not DEPOSIT_MIN <= amount <= DEPOSIT_MAX:
        await message.answer(
            f"❌ ডিপোজিট পরিমাণ সঠিক নয়।\nসর্বনিম্ন: ৳{DEPOSIT_MIN}\nসর্বোচ্চ: ৳{DEPOSIT_MAX}",
            reply_markup=cancel_kb()
        )
        return
    data = await state.get_data()
    method = data["method"]
    await state.clear()
    await message.answer(
        f"আপনার পেমেন্ট পরিমাণ: ৳{money(amount)}\n\n"
        "আপনার পেমেন্ট সম্পন্ন করতে নিচের লিংকে প্রবেশ করুন।",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Payment Gateway", url=DEPOSIT_GATEWAY_URL)],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu")]
        ])
    )

@dp.callback_query(F.data == "dep:Binance")
async def binance_dep(c: CallbackQuery, state: FSMContext):
    await state.set_state(DepositState.binance_amount)
    await c.message.edit_text(
        "🟡 <b>Binance</b>\n\n"
        "আপনি কত ডলার ডিপোজিট করবেন নিচে টাইপ করে পাঠান।\n"
        "উদাহরণ: 1\n\n"
        "সর্বনিম্ন ১ ডলার এবং সর্বোচ্চ ৫০ ডলার।",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await c.answer()

@dp.message(DepositState.binance_amount)
async def binance_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
    except ValueError:
        await message.answer("⚠️ শুধু সংখ্যায় USDT পরিমাণ লিখুন।", reply_markup=cancel_kb())
        return
    if not 1 <= amount <= 50:
        await message.answer(
            "❌ দুঃখিত! সর্বনিম্ন ১ ডলার এবং সর্বোচ্চ ৫০ ডলার ডিপোজিট করতে পারবেন।",
            reply_markup=cancel_kb()
        )
        return
    await state.update_data(usdt=amount)
    await state.set_state(DepositState.txid)
    await message.answer(
        "🟡 <b>USDT — BEP20 ডিপোজিট</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"💱 ডিপোজিট রেট: 1 USDT = ৳{USDT_RATE}\n"
        f"💰 আপনার ডিপোজিট: {money(amount)} USDT = ৳{money(amount*USDT_RATE)}\n\n"
        "📌 ডেমো নির্দেশনা:\n"
        f"① BEP20 Address: <code>{BINANCE_DEMO_ADDRESS}</code>\n"
        "② Network: BEP20 (BSC)\n"
        "③ আপনার Transaction Hash / TxID লিখে পাঠান।\n\n"
        "⚠️ এই সংস্করণটি DEMO; বাস্তব blockchain verification করা হচ্ছে না।",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )

@dp.message(DepositState.txid)
async def binance_txid(message: Message, state: FSMContext):
    txid = message.text.strip()
    if not re.fullmatch(r"0x[a-fA-F0-9]{64}", txid):
        await message.answer(
            "❌ Transaction Hash সঠিক নয়।\n"
            "উদাহরণ: 0x + 64টি hexadecimal character দিন।",
            reply_markup=cancel_kb()
        )
        return
    data = await state.get_data()
    usdt = data["usdt"]
    amount = usdt * USDT_RATE
    order = "RC" + datetime.now().strftime("%Y%m%d%H%M%S%f")
    created = now().isoformat()
    cur = db.execute(
        """INSERT INTO deposits(user_id,method,amount,txid,order_no,status,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (message.from_user.id, "Binance", amount, txid, order, "PENDING", created, created)
    )
    db.commit()
    dep_id = cur.lastrowid
    await state.clear()
    await message.answer(
        "✅ <b>আপনার ডিপোজিটের অনুরোধ জমা করা হয়েছে।</b>\n"
        "অনুমোদনের জন্য অপেক্ষা করুন।", parse_mode="HTML"
    )
    u = get_user(message.from_user.id)
    admin_text = (
        "📥 <b>নতুন ডিপোজিট রিকোয়েস্ট!</b>\n\n"
        f"👤 নাম: {escape(u['name'])}\n"
        f"🔗 ইউজারনেম: @{escape(u['username']) if u['username'] else 'N/A'}\n"
        f"🆔 ইউজার আইডি: <code>{u['id']}</code>\n"
        "⚙️ মেথড: Binance\n"
        f"💰 অ্যামাউন্ট: {money(amount)} BDT\n"
        f"🆔 TxID: <code>{txid}</code>\n"
        f"📝 Order No: <code>{order}</code>\n\nঅ্যাকশন নিন:"
    )
    await bot.send_message(ADMIN_ID, admin_text, reply_markup=admin_deposit_kb(dep_id), parse_mode="HTML")

# ---------- Account ----------
@dp.callback_query(F.data == "account")
async def account(c: CallbackQuery):
    u = get_user(c.from_user.id)
    plans = db.execute(
        "SELECT vip,expires_at FROM plans WHERE user_id=? AND active=1 AND expires_at>?",
        (c.from_user.id, now().isoformat())
    ).fetchall()
    plan_lines = "\n".join(
        f"• VIP {p['vip']} — {max(0, (datetime.fromisoformat(p['expires_at'])-now()).days)} দিন"
        for p in plans
    ) or "• কোনো Active Plan নেই"
    text = (
        "👤 <b>আমার অ্যাকাউন্টের তথ্য</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 ব্যবহারকারীর নাম: {escape(u['name'])}\n"
        f"🔗 ইউজারনেম: @{escape(u['username']) if u['username'] else 'N/A'}\n"
        f"🆔 ইউজার আইডি: <code>{u['id']}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n💰 <b>BALANCE DETAILS</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 মোট ব্যালেন্স: {money(u['main_balance']+u['deposit_balance']+u['bonus_balance']+u['referral_balance'])} টাকা\n"
        f"📥 ডিপোজিট ব্যালেন্স: {money(u['deposit_balance'])} টাকা\n"
        f"🎁 ডিপোজিট বোনাস: {money(u['bonus_balance'])} টাকা\n"
        f"🫂 রেফার ব্যালেন্স: {money(u['referral_balance'])} টাকা\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n👑 <b>ACCOUNT STATUS</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏳ Active Plans:\n" + plan_lines +
        f"\n🚫 নিষিদ্ধ: {'হ্যাঁ' if u['banned'] else 'না'}"
    )
    await c.message.edit_text(text, reply_markup=main_menu(), parse_mode="HTML")
    await c.answer()

# ---------- Withdraw ----------
@dp.callback_query(F.data == "withdraw")
async def withdraw(c: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 bKash", callback_data="wd:bKash"),
         InlineKeyboardButton(text="🪙 Nagad", callback_data="wd:Nagad")],
        [InlineKeyboardButton(text="❌ বাতিল", callback_data="cancel")]
    ])
    await c.message.edit_text(
        "💸 <b>Withdraw</b>\n\nআপনার উপলব্ধ Balance থেকে Withdraw Request করতে নিচের অপশন নির্বাচন করুন।👇",
        reply_markup=kb, parse_mode="HTML"
    )
    await c.answer()

@dp.callback_query(F.data.in_({"wd:bKash", "wd:Nagad"}))
async def wd_method(c: CallbackQuery, state: FSMContext):
    method = c.data.split(":")[1]
    await state.update_data(method=method)
    await state.set_state(WithdrawState.account)
    await c.message.edit_text(
        f"💳 আপনি <b>{method}</b> সিলেক্ট করেছেন।\n"
        f"📱 অনুগ্রহ করে আপনার সঠিক ১১ সংখ্যার {method} নম্বরটি লিখে পাঠান।\n"
        "উদাহরণ: 017XXXXXXXX",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await c.answer()

@dp.message(WithdrawState.account)
async def wd_account(message: Message, state: FSMContext):
    account = message.text.strip()
    if not re.fullmatch(r"01\d{9}", account):
        data = await state.get_data()
        await message.answer(
            f"⚠️ আপনি ভুল নাম্বার দিয়েছেন। সঠিক ১১ ডিজিটের {data.get('method','')} নম্বর দিন।",
            reply_markup=cancel_kb()
        )
        return
    await state.update_data(account=account)
    await state.set_state(WithdrawState.amount)
    u = get_user(message.from_user.id)
    await message.answer(
        f"💰 আপনার বর্তমান ব্যালেন্স: {money(u['main_balance'])}৳\n"
        "💸 উইথড্র সীমা:\n▫️ সর্বনিম্ন: 100৳\n▫️ সর্বোচ্চ: 25000৳\n\n"
        "🏦 নম্বর: সফলভাবে গ্রহণ করা হয়েছে।\n\n"
        "✍️ এখন আপনি কত টাকা উইথড্র করতে চান, শুধু টাকার পরিমাণটি সংখ্যায় লিখে পাঠান।",
        reply_markup=cancel_kb()
    )

@dp.message(WithdrawState.amount)
async def wd_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
    except ValueError:
        await message.answer("⚠️ শুধু সংখ্যায় পরিমাণ লিখুন।", reply_markup=cancel_kb())
        return
    u = get_user(message.from_user.id)
    if not WITHDRAW_MIN <= amount <= WITHDRAW_MAX or amount > u["main_balance"]:
        await message.answer(
            f"⚠️ <b>উইথড্র পরিমাণ সঠিক নয়!</b>\n"
            f"💰 সীমা: {WITHDRAW_MIN:,}৳ — {WITHDRAW_MAX:,}৳\n"
            f"আপনার বর্তমান ব্যালেন্স: {money(u['main_balance'])}৳",
            reply_markup=cancel_kb(), parse_mode="HTML"
        )
        return
    data = await state.get_data()
    # Reserve the main balance while pending.
    db.execute("UPDATE users SET main_balance=main_balance-? WHERE id=?", (amount, message.from_user.id))
    cur = db.execute(
        """INSERT INTO withdrawals(user_id,method,account,amount,status,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?)""",
        (message.from_user.id, data["method"], data["account"], amount, "PENDING", now().isoformat(), now().isoformat())
    )
    db.commit()
    wid = cur.lastrowid
    await state.clear()
    await message.answer(
        f"আপনার 💸 <b>{money(amount)}৳</b> উইথড্র রিকোয়েস্ট সফলভাবে জমা হয়েছে!\n"
        "⏳ অনুমোদন সম্পন্ন হওয়া পর্যন্ত অপেক্ষা করুন।",
        parse_mode="HTML"
    )
    u = get_user(message.from_user.id)
    await bot.send_message(
        ADMIN_ID,
        "📤 <b>নতুন Withdraw Request</b>\n\n"
        f"👤 {escape(u['name'])}\n🆔 <code>{u['id']}</code>\n"
        f"💳 Method: {data['method']}\n📱 Account: <code>{data['account']}</code>\n"
        f"💰 Amount: {money(amount)}৳\n🆔 Request ID: {wid}",
        reply_markup=admin_withdraw_kb(wid), parse_mode="HTML"
    )

# ---------- Referral ----------
@dp.callback_query(F.data == "referral")
async def referral(c: CallbackQuery):
    u = get_user(c.from_user.id)
    count = db.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?", (c.from_user.id,)).fetchone()[0]
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={c.from_user.id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Share করুন", switch_inline_query=link),
         InlineKeyboardButton(text="📋 Rules", callback_data="ref_rules")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu")]
    ])
    await c.message.edit_text(
        "👥 <b>Referral</b>\n\n😊 রেফারেল প্রোগ্রামে আপনাকে স্বাগতম!\n"
        "বন্ধুদের আপনার Referral Link দিয়ে Join করান।\n\n"
        f"🔗 Your Referral Link: {link}\n"
        f"👤 Total Referrals: {count} জন\n"
        f"💰 Referral Earnings: {money(u['referral_balance'])}৳\n\n"
        "📢 আপনার Referral Link শেয়ার করতে নিচের অপশন ব্যবহার করুন।",
        reply_markup=kb, parse_mode="HTML"
    )
    await c.answer()

@dp.callback_query(F.data == "ref_rules")
async def ref_rules(c: CallbackQuery):
    await c.message.edit_text(
        "📋 <b>Referral Rules</b>\n\n"
        "আপনার রেফার করা কোনো ব্যক্তি ডিপোজিট করলে, তার ডিপোজিটের "
        "<b>৫%</b> Referral Commission প্রযোজ্য হতে পারে।\n\n"
        "⚠️ কমিশন ও অন্যান্য শর্ত সেবার নিয়ম অনুযায়ী পরিবর্তনযোগ্য।",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="referral")]
        ]), parse_mode="HTML"
    )
    await c.answer()

# ---------- Bonus ----------
@dp.callback_query(F.data == "bonus")
async def bonus(c: CallbackQuery):
    u = get_user(c.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Claim ৳5", callback_data="bonus_claim")],
        [InlineKeyboardButton(text="▶️ Next", callback_data="bonus_next")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu")]
    ])
    await c.message.edit_text(
        "🎁 <b>Bonus Center</b>\n\n"
        f"🎁 Available Bonus: {money(u['bonus_balance'])}৳\n"
        "🏆 Active Rewards\n"
        "📜 Bonus History\n\n"
        "প্রতিদিন নির্ধারিত bonus claim করা যায়। Bonus Balance সরাসরি withdraw বা Plan activation-এ ব্যবহার করা যায় না।",
        reply_markup=kb, parse_mode="HTML"
    )
    await c.answer()

@dp.callback_query(F.data == "bonus_claim")
async def bonus_claim(c: CallbackQuery):
    u = get_user(c.from_user.id)
    today = now().date().isoformat()
    if u["last_bonus"] == today:
        await c.answer("আজকের Bonus ইতিমধ্যে Claim করা হয়েছে।", show_alert=True)
        return
    db.execute("UPDATE users SET bonus_balance=bonus_balance+?, last_bonus=? WHERE id=?",
               (BONUS_DAILY, today, c.from_user.id))
    db.execute("INSERT INTO bonus_history(user_id,amount,created_at) VALUES(?,?,?)",
               (c.from_user.id, BONUS_DAILY, now().isoformat()))
    db.commit()
    await c.message.edit_text(
        "🎉 অভিনন্দন!\nআজকের ৳5 Bonus আপনার Bonus Balance-এ যোগ হয়েছে।",
        reply_markup=main_menu()
    )
    await c.answer()

# ---------- Plans / Earnings ----------
@dp.callback_query(F.data == "plans")
async def plans(c: CallbackQuery):
    await c.message.edit_text(
        "💎 <b>Available Plans</b>\n\nউপলব্ধ Plans দেখতে নিচের অপশন নির্বাচন করুন।👇\n\n"
        "⚠️ এই বটের Plan/return অংশটি DEMO/SIMULATION হিসেবে ব্যবহারের জন্য।",
        reply_markup=plan_kb(), parse_mode="HTML"
    )
    await c.answer()

@dp.callback_query(F.data.startswith("plan:"))
async def plan_detail(c: CallbackQuery):
    vip = int(c.data.split(":")[1])
    amount = PLANS[vip]
    active_count = db.execute(
        "SELECT COUNT(*) FROM plans WHERE user_id=? AND vip=? AND active=1 AND expires_at>?",
        (c.from_user.id, vip, now().isoformat())
    ).fetchone()[0]
    daily = amount * 0.34
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Plan Buy 💸", callback_data=f"buy:{vip}")],
        [InlineKeyboardButton(text="🔙 Plans", callback_data="plans")]
    ])
    await c.message.edit_text(
        f"💎 <b>VIP {vip} — Ingka</b>\n\n"
        f"💰 Amount: ৳{money(amount)}\n📅 Duration: 4 দিন\n"
        f"📊 Demo daily calculation: ৳{money(daily)}\n"
        f"📦 Active: {active_count}/2\n\n"
        "⚠️ এটি বাস্তব বা নিশ্চিত বিনিয়োগ রিটার্ন নয়; DEMO configuration।",
        reply_markup=kb, parse_mode="HTML"
    )
    await c.answer()

@dp.callback_query(F.data.startswith("buy:"))
async def buy_plan(c: CallbackQuery):
    vip = int(c.data.split(":")[1])
    amount = PLANS[vip]
    u = get_user(c.from_user.id)
    active = db.execute(
        "SELECT COUNT(*) FROM plans WHERE user_id=? AND vip=? AND active=1 AND expires_at>?",
        (c.from_user.id, vip, now().isoformat())
    ).fetchone()[0]
    if active >= 2:
        await c.answer("⚠️ এই Plan-এর সর্বোচ্চ ২টি Active রাখা যাবে।", show_alert=True)
        return
    eligible = u["main_balance"] + u["deposit_balance"]
    if eligible < amount:
        await c.message.edit_text(
            "❌ আপনার ডিপোজিট ও মেইন balance এ পর্যাপ্ত টাকা নেই।\n"
            "দয়া করে আগে যোগ করুন, পরে আবার চেষ্টা করুন। ধন্যবাদ। ❤️",
            reply_markup=main_menu()
        )
        await c.answer()
        return
    # Demo activation: consume main balance first, then deposit balance.
    main_use = min(u["main_balance"], amount)
    dep_use = amount - main_use
    activated = now()
    expires = activated + timedelta(days=4)
    db.execute(
        "UPDATE users SET main_balance=main_balance-?, deposit_balance=deposit_balance-? WHERE id=?",
        (main_use, dep_use, c.from_user.id)
    )
    db.execute(
        """INSERT INTO plans(user_id,vip,amount,activated_at,expires_at)
           VALUES(?,?,?,?,?)""",
        (c.from_user.id, vip, amount, activated.isoformat(), expires.isoformat())
    )
    db.commit()
    await c.message.edit_text(
        f"🎊 <b>অভিনন্দন!</b> আপনার VIP {vip} Plan সফলভাবে সক্রিয় হয়েছে। ✅\n\n"
        f"💎 Plan: VIP {vip}\n💰 Amount: ৳{money(amount)}\n📅 মেয়াদ: 4 দিন\n"
        f"📊 Demo daily amount: ৳{money(amount*0.34)}\n\n"
        "📊 Daily Earnings থেকে claim করা যাবে।\n"
        "⏳ Plan-এর মেয়াদ সক্রিয় হওয়ার সময় থেকে গণনা হবে।\n\n"
        "⚠️ এটি DEMO/SIMULATION; বাস্তব নিশ্চিত লাভ নয়।",
        reply_markup=main_menu(), parse_mode="HTML"
    )
    await c.answer()

def claim_window_open():
    t = now().time()
    return time(8,0) <= t <= time(23,59,59)

@dp.callback_query(F.data == "earnings")
async def earnings(c: CallbackQuery):
    # Expire old plans
    db.execute("UPDATE plans SET active=0 WHERE expires_at<=?", (now().isoformat(),))
    db.commit()
    u = get_user(c.from_user.id)
    plans = db.execute(
        "SELECT * FROM plans WHERE user_id=? AND active=1 ORDER BY expires_at",
        (c.from_user.id,)
    ).fetchall()
    lines = []
    for p in plans:
        lines.append(f"💎 VIP {p['vip']} — ৳{money(p['amount'])} — expires {p['expires_at'][:16].replace('T',' ')}")
    text = (
        "📊 <b>Daily Earnings</b>\n\n"
        f"📈 Total Earnings: {money(u['total_earnings'])}৳\n"
        "📅 Earnings History\n\n"
        + ("\n".join(lines) if lines else "❌ বর্তমানে কোনো Active Plan নেই।")
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧮 Today Earnings Claim", callback_data="claim_earn")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu")]
    ])
    await c.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await c.answer()

@dp.callback_query(F.data == "claim_earn")
async def claim_earn(c: CallbackQuery):
    if not claim_window_open():
        await c.answer("⏰ Earnings Claim প্রতিদিন সকাল ৮টা থেকে রাত ১২টা পর্যন্ত।", show_alert=True)
        return
    db.execute("UPDATE plans SET active=0 WHERE expires_at<=?", (now().isoformat(),))
    db.commit()
    today = now().date().isoformat()
    plans = db.execute(
        "SELECT * FROM plans WHERE user_id=? AND active=1",
        (c.from_user.id,)
    ).fetchall()
    if not plans:
        await c.message.edit_text("❌ আপনার বর্তমানে কোনো Plans Active নেই।", reply_markup=main_menu())
        await c.answer()
        return
    total = 0
    for p in plans:
        if p["last_claim_date"] == today:
            continue
        amount = p["amount"] * 0.34  # demo calculation
        total += amount
        db.execute(
            "INSERT INTO earnings(user_id,plan_id,amount,claim_date,created_at) VALUES(?,?,?,?,?)",
            (c.from_user.id, p["id"], amount, today, now().isoformat())
        )
        db.execute("UPDATE plans SET last_claim_date=? WHERE id=?", (today, p["id"]))
    if total <= 0:
        await c.answer("আজকের Earnings ইতিমধ্যে Claim করা হয়েছে।", show_alert=True)
        return
    db.execute(
        "UPDATE users SET main_balance=main_balance+?, total_earnings=total_earnings+? WHERE id=?",
        (total, total, c.from_user.id)
    )
    db.commit()
    await c.message.edit_text(
        f"🎁 অভিনন্দন!\nআপনার সকল Active Plans থেকে আজকের DEMO earnings বাবদ "
        f"<b>{money(total)}৳</b> Main Balance-এ যোগ করা হয়েছে। ✅",
        reply_markup=main_menu(), parse_mode="HTML"
    )
    await c.answer()

# ---------- History ----------
@dp.callback_query(F.data == "history")
async def history(c: CallbackQuery):
    uid = c.from_user.id
    deps = db.execute("SELECT * FROM deposits WHERE user_id=? ORDER BY id DESC LIMIT 7", (uid,)).fetchall()
    wds = db.execute("SELECT * FROM withdrawals WHERE user_id=? ORDER BY id DESC LIMIT 7", (uid,)).fetchall()
    ers = db.execute("SELECT * FROM earnings WHERE user_id=? ORDER BY id DESC LIMIT 7", (uid,)).fetchall()
    text = "🧾 <b>Transaction History</b>\n\n📥 <b>Deposit History</b>\n"
    text += "\n".join(f"#{d['id']} • {money(d['amount'])}৳ • {d['status']}" for d in deps) or "কোনো রেকর্ড নেই"
    text += "\n\n📤 <b>Withdraw History</b>\n"
    text += "\n".join(f"#{w['id']} • {money(w['amount'])}৳ • {w['status']}" for w in wds) or "কোনো রেকর্ড নেই"
    text += "\n\n📊 <b>Earnings History</b>\n"
    text += "\n".join(f"#{e['id']} • {money(e['amount'])}৳ • {e['claim_date']}" for e in ers) or "কোনো রেকর্ড নেই"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Next ▶️", callback_data="history_next")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu")]
    ])
    await c.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await c.answer()

@dp.callback_query(F.data == "history_next")
async def history_next(c: CallbackQuery):
    await c.answer("পরের History pagination পরে যুক্ত করা যাবে।", show_alert=True)

# ---------- Help ----------
async def show_help(target):
    text = (
        "🆘 <b>Help & Support</b>\n\n"
        "কোনো সমস্যা বা প্রশ্ন থাকলে আমাদের Support Team-এর সাথে যোগাযোগ করুন।\n"
        "📌 Account Problem\n💳 Deposit Problem\n💸 Withdraw Problem\n"
        "👥 Referral Problem\n❓ Other Issues\n🕐 Support Hours: Available as stated by the service."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Support Center", url="https://t.me/Nikan_Support01")],
        [InlineKeyboardButton(text="📢 Official Channel", url="https://t.me/NIKAN_EARN")],
        [InlineKeyboardButton(text="📋 Rules", callback_data="rules")]
    ])
    await target.answer(text, reply_markup=kb, parse_mode="HTML") if isinstance(target, Message) else await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "help")
async def help_cb(c: CallbackQuery):
    await show_help(c)
    await c.answer()

@dp.callback_query(F.data == "rules")
async def rules(c: CallbackQuery):
    await c.message.edit_text(
        "🌐 <b>About NIKAN</b>\n\n"
        "NIKAN একটি অনলাইন earning platform-এর DEMO interface, যেখানে earning features, "
        "referral program, transaction history এবং configurable plans-এর flow দেখানো হয়।\n\n"
        "💰 Earning Features\n📊 Track Your Earnings\n👥 Referral Program\n"
        "🧾 Transaction History\n🆘 User Support\n\n"
        "⚠️ কোনো earning/return নিশ্চিত বা গ্যারান্টিযুক্ত নয়।",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="help")]
        ]), parse_mode="HTML"
    )
    await c.answer()

# ---------- Admin actions ----------
@dp.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("da:"))
async def admin_dep_approve(c: CallbackQuery):
    dep_id = int(c.data.split(":")[1])
    d = db.execute("SELECT * FROM deposits WHERE id=?", (dep_id,)).fetchone()
    if not d:
        await c.answer("Deposit request পাওয়া যায়নি.", show_alert=True); return
    if d["status"] == "APPROVED":
        await c.answer("Already approved.", show_alert=True); return
    db.execute("UPDATE deposits SET status='APPROVED',updated_at=? WHERE id=?", (now().isoformat(), dep_id))
    db.execute("UPDATE users SET deposit_balance=deposit_balance+? WHERE id=?", (d["amount"], d["user_id"]))
    db.commit()
    await bot.send_message(
        d["user_id"],
        f"🎉 <b>Deposit Successful!</b>\nআপনার {money(d['amount'])}৳ Deposit সফলভাবে সম্পন্ন হয়েছে। ✅\n"
        f"📝 Transaction ID: {d['txid']}\n🆔 Order Number: {d['order_no']}\n\n"
        f"💳 আপনার Deposit Balance-এ {money(d['amount'])}৳ যোগ করা হয়েছে।",
        parse_mode="HTML"
    )
    await c.message.edit_reply_markup(reply_markup=None)
    await c.answer("Deposit approved.")

@dp.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("dr:"))
async def admin_dep_reject(c: CallbackQuery):
    dep_id = int(c.data.split(":")[1])
    d = db.execute("SELECT * FROM deposits WHERE id=?", (dep_id,)).fetchone()
    if not d:
        await c.answer("Request পাওয়া যায়নি.", show_alert=True); return
    db.execute("UPDATE deposits SET status='REJECTED',reason=?,updated_at=? WHERE id=?",
               ("Admin rejected / demo review", now().isoformat(), dep_id))
    db.commit()
    await bot.send_message(
        d["user_id"],
        f"❌ <b>Deposit Failed!</b>\n"
        "আপনার দেওয়া Transaction ID সঠিক নয় অথবা এই Transaction ID-এর মাধ্যমে কোনো পেমেন্ট শনাক্ত করা যায়নি।\n"
        f"📝 Transaction ID: {d['txid']}\n🆔 Order No: {d['order_no']}\n\n"
        "🔄 অনুগ্রহ করে সঠিক Transaction ID দিয়ে আবার চেষ্টা করুন।",
        parse_mode="HTML"
    )
    await c.message.edit_reply_markup(reply_markup=None)
    await c.answer("Deposit rejected.")

@dp.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("wa:"))
async def admin_wd_approve(c: CallbackQuery):
    wid = int(c.data.split(":")[1])
    w = db.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()
    if not w:
        await c.answer("Request পাওয়া যায়নি.", show_alert=True); return
    db.execute("UPDATE withdrawals SET status='APPROVED',updated_at=? WHERE id=?", (now().isoformat(), wid))
    db.commit()
    await bot.send_message(
        w["user_id"],
        f"🎊 <b>উইথড্র কনফার্মড!</b>\n💰 পরিমাণ: {money(w['amount'])}৳\n\n"
        "🟢 আপনার পেমেন্ট রিকোয়েস্ট অনুমোদিত হয়েছে।\n"
        "📲 নির্ধারিত নম্বর/ওয়ালেটে পেমেন্ট পাঠানোর বিষয়টি সার্ভিসের বাইরে আলাদাভাবে যাচাই করুন।",
        parse_mode="HTML"
    )
    await c.message.edit_reply_markup(reply_markup=None)
    await c.answer("Withdrawal approved.")

@dp.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("wr:"))
async def admin_wd_reject(c: CallbackQuery):
    wid = int(c.data.split(":")[1])
    w = db.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()
    if not w:
        await c.answer("Request পাওয়া যায়নি.", show_alert=True); return
    db.execute("UPDATE users SET main_balance=main_balance+? WHERE id=?", (w["amount"], w["user_id"]))
    db.execute("UPDATE withdrawals SET status='REJECTED',reason=?,updated_at=? WHERE id=?",
               ("Admin rejected / demo review", now().isoformat(), wid))
    db.commit()
    await bot.send_message(
        w["user_id"],
        f"🚫 <b>WITHDRAW CANCELLED</b>\n\n💰 Amount: {money(w['amount'])}৳\n"
        "আপনার উইথড্র রিকোয়েস্টটি বাতিল করা হয়েছে।\n\n"
        f"↩️ {money(w['amount'])}৳ আপনার অ্যাকাউন্ট ব্যালেন্সে পুনরায় যোগ হয়েছে।",
        parse_mode="HTML"
    )
    await c.message.edit_reply_markup(reply_markup=None)
    await c.answer("Withdrawal rejected and refunded.")

@dp.callback_query()
async def unknown_admin_action(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID and (c.data.startswith(("da:","dr:","wa:","wr:"))):
        await c.answer("⛔ অনুমতি নেই।", show_alert=True)
    else:
        await c.answer()

async def main():
    init_db()
    print("NIKAN DEMO bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
