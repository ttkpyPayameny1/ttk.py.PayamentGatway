# NIKAN EARN - Reply Keyboard Demo Bot
# Python 3.10+ / aiogram 3.x
# DEMO/SIMULATION ONLY — no real payment gateway or payout is performed.

import asyncio
import errno
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, ErrorEvent
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# =========================
# CONFIG
# =========================
BOT_TOKEN = "8983512458:AAGUw0goCNIUSUeJxzYSX1qKnDjz9GdzmiA"
ADMIN_ID = 2037461288
OWNER_ID = ADMIN_ID

PAYMENT_GATEWAY_URL = "https://example.com/payment-gateway"

BINANCE_DEPOSIT_ADDRESS = "0xade76b7f023c3ded14850293ea26e477edbdd048"
USDT_RATE_BDT = Decimal("125")

DB_NAME = "nikan.db"

# =========================
# PLANS
# =========================
PLANS = {
    "VIP1": 300, "VIP2": 500, "VIP3": 1000, "VIP4": 2000,
    "VIP5": 3000, "VIP6": 5000, "VIP7": 7500, "VIP8": 10000,
    "VIP9": 15000, "VIP10": 20000, "VIP11": 30000, "VIP12": 50000,
}
PLAN_DAYS = 4
DEMO_DAILY_RATE = Decimal("0.34")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# =========================
# ✅ FIX: SINGLE-INSTANCE LOCK
# =========================
# একই মেশিনে bot একাধিকবার চালু থাকলে Telegram থেকে একই মেসেজ
# একাধিকবার প্রসেস হয়ে user ১-৩ বার রিপ্লাই পায়।
# এই lock দ্বিতীয় instance চালু হওয়ার সাথে সাথে সেটি বন্ধ করে দেয়।
LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nikan_bot.lock")
_lock_handle = None


def acquire_single_instance_lock():
    global _lock_handle
    try:
        import fcntl  # Linux / macOS
    except ImportError:
        return  # Windows: এই check skip হবে
    try:
        handle = open(LOCK_FILE, "a+")
    except OSError:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        handle.close()
        if getattr(e, "errno", None) in (errno.EAGAIN, errno.EACCES):
            print("=" * 62)
            print("❌ NIKAN EARN bot ইতিমধ্যেই অন্য একটি instance-এ চলছে!")
            print("👉 আগের bot / terminal / panel বন্ধ করে আবার চালান।")
            print("   (একসাথে ২+ instance চললে user ১-৩ বার রিপ্লাই পায়)")
            print("=" * 62)
            sys.exit(1)
        return
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    _lock_handle = handle


# =========================
# DATABASE (CORRECTED & UNIFIED)
# =========================
def db():
    return sqlite3.connect(DB_NAME)


def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        username TEXT,
        main_balance REAL DEFAULT 0,
        deposit_balance REAL DEFAULT 0,
        bonus_balance REAL DEFAULT 0,
        referral_balance REAL DEFAULT 0,
        total_earnings REAL DEFAULT 0,
        created_at TEXT
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        method TEXT,
        amount REAL,
        txid TEXT,
        order_no TEXT,
        status TEXT DEFAULT 'Pending',
        reason TEXT DEFAULT '',
        created_at TEXT,
        updated_at TEXT
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        method TEXT,
        account TEXT,
        amount REAL,
        status TEXT DEFAULT 'Pending',
        reason TEXT DEFAULT '',
        created_at TEXT,
        updated_at TEXT
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        plan TEXT,
        amount REAL,
        activated_at TEXT,
        expires_at TEXT,
        last_claim_date TEXT DEFAULT '',
        active INTEGER DEFAULT 1
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS earnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        plan_id INTEGER,
        amount REAL,
        claim_date TEXT,
        created_at TEXT
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS bonuses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        type TEXT,
        created_at TEXT
    )""")

    cur.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, role TEXT DEFAULT 'admin', added_at TEXT)")
    cur.execute("INSERT OR IGNORE INTO admins(user_id,role,added_at) VALUES(?,?,?)", (OWNER_ID, 'owner', datetime.now(timezone.utc).isoformat()))
    cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    
    defaults = {
        'bot_enabled': '1', 'fund_enabled': '1', 'withdraw_enabled': '1',
        'dep_bkash_enabled': '1', 'dep_nagad_enabled': '1',
        'wth_bkash_enabled': '1', 'wth_nagad_enabled': '1', 'wth_rocket_enabled': '1', 'wth_upay_enabled': '1',
        'bkash_number': '', 'nagad_number': '', 'dep_bkash_gateway': '', 'dep_nagad_gateway': '',
        'min_dep': '50', 'max_dep': '10000', 'min_wth': '100', 'max_wth': '25000', 'daily_dep_limit': '3',
        'force_join_enabled': '0', 'force_join_chat': '', 'force_join_link': ''
    }
    for k, v in defaults.items(): 
        cur.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', (k, v))

    cols = {r[1] for r in cur.execute('PRAGMA table_info(users)').fetchall()}
    for col, typ, default in [
        ('task_balance', 'REAL', '0'), ('referral_count', 'INTEGER', '0'), 
        ('completed_tasks', 'INTEGER', '0'), ('banned', 'INTEGER', '0'), ('suspended', 'INTEGER', '0')
    ]:
        if col not in cols: 
            cur.execute(f'ALTER TABLE users ADD COLUMN {col} {typ} DEFAULT {default}')

    con.commit()
    con.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_user(message: Message):
    u = message.from_user
    con = db()
    cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (u.id,))
    row = cur.fetchone()

    if not row:
        cur.execute("""
            INSERT INTO users(user_id,name,username,created_at)
            VALUES(?,?,?,?)
        """, (u.id, u.full_name, u.username or "", now_iso()))
        con.commit()
        cur.execute("SELECT * FROM users WHERE user_id=?", (u.id,))
        row = cur.fetchone()
    else:
        cur.execute("""
            UPDATE users SET name=?, username=? WHERE user_id=?
        """, (u.full_name, u.username or "", u.id))
        con.commit()

    con.close()
    return row


def user_row(uid):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone()
    con.close()
    return r


def money(x):
    return f"{Decimal(str(x)):.2f}".rstrip("0").rstrip(".")


def order_no():
    return "RC" + datetime.now().strftime("%Y%m%d%H%M%S%f")[:21]


# =========================
# REPLY KEYBOARD
# =========================
def main_keyboard(uid=None):
    kb = [
        [KeyboardButton(text="🔐 ফান্ড ডিপোজিট"), KeyboardButton(text="👤 একাউন্ট")],
        [KeyboardButton(text="💸 Withdraw"), KeyboardButton(text="👥 Referral")],
        [KeyboardButton(text="📊 Daily Earnings"), KeyboardButton(text="🎁 Bonus Center")],
        [KeyboardButton(text="💎 Available Plans"), KeyboardButton(text="🧾 Transaction History")],
        [KeyboardButton(text="🆘 Help & Support")],
    ]
    if uid and admin_ok(uid):
        kb.append([KeyboardButton(text="🔧 Admin Panel")])
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="একটি অপশন নির্বাচন করুন"
    )


def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Cancel")]],
        resize_keyboard=True
    )


# =========================
# STATES
# =========================
class DepositState(StatesGroup):
    method = State()
    amount = State()
    txid = State()


class WithdrawState(StatesGroup):
    method = State()
    account = State()
    amount = State()


# =========================
# START / MENU
# =========================
@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    get_user(message)
    await message.answer(
        "🚀 **NIKAN EARN**\n\nস্বাগতম! নিচের মেনু থেকে একটি অপশন নির্বাচন করুন।",
        parse_mode="Markdown",
        reply_markup=main_keyboard(message.from_user.id)
    )


@dp.message(Command("menu"))
async def menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 **Main Menu**\nনিচের মেনু থেকে একটি অপশন নির্বাচন করুন।", parse_mode="Markdown", reply_markup=main_keyboard(message.from_user.id))


@dp.message(Command("help"))
async def help_command(message: Message):
    await show_help(message)


@dp.message(F.text == "❌ Cancel")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ **বর্তমান প্রক্রিয়াটি বাতিল করা হয়েছে।**", parse_mode="Markdown", reply_markup=main_keyboard(message.from_user.id))


# =========================
# DEPOSIT
# =========================
@dp.message(F.text == "🔐 ফান্ড ডিপোজিট")
async def deposit_menu(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 বিকাশ", callback_data="dep_bkash"),
         InlineKeyboardButton(text="💠 নগদ", callback_data="dep_nagad")],
        [InlineKeyboardButton(text="🟡 Binance", callback_data="dep_binance")],
    ])
    await message.answer(
        "🔐 **ফান্ড ডিপোজিট**\n━━━━━━━━━━━━━━━━━━\n"
        "নিচের অপশন থেকে একটি মেথড নির্বাচন করুন।",
        parse_mode="Markdown",
        reply_markup=kb
    )


@dp.callback_query(F.data.in_(["dep_bkash", "dep_nagad"]))
async def dep_local_method(call: CallbackQuery, state: FSMContext):
    method = "bKash" if call.data == "dep_bkash" else "Nagad"
    await state.update_data(method=method)
    await state.set_state(DepositState.amount)
    await call.message.answer(
        f"💳 **{method} Deposit**\n\n"
        "📊 **ডিপোজিট লিমিট:** 0/3\n"
        "💰 **সর্বনিম্ন:** 50৳\n"
        "💰 **সর্বোচ্চ:** 10,000৳\n\n"
        "👉 **কত টাকা ডিপোজিট করতে চান? সংখ্যায় লিখুন।**",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    await call.answer()


@dp.message(DepositState.amount)
async def dep_local_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("method") == "Binance":
        return await dep_binance_amount(message, state)

    try:
        amount = Decimal(message.text.strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ **সঠিক সংখ্যায় ডিপোজিট এমাউন্ট লিখুন।**", parse_mode="Markdown")
        return

    if amount < 50 or amount > 10000:
        await message.answer("⚠️ **ডিপোজিটের পরিমাণ 50৳ থেকে 10,000৳ এর মধ্যে হতে হবে।**", parse_mode="Markdown")
        return

    method = data["method"]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 পেমেন্ট গেটওয়েতে যান", url=PAYMENT_GATEWAY_URL)],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_inline")]
    ])
    await message.answer(
        f"💰 **ডিপোজিট এমাউন্ট:** {money(amount)}৳\n\n"
        "আপনার প্রদত্ত এমাউন্টটি ডিপোজিট করতে নিচের দেওয়া লিংকে প্রবেশ করুন।\n\n"
        f"💳 **Method:** {method}",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await state.clear()


@dp.callback_query(F.data == "dep_binance")
async def dep_binance(call: CallbackQuery, state: FSMContext):
    await state.update_data(method="Binance")
    await state.set_state(DepositState.amount)
    await call.message.answer(
        "🟡 **Binance — USDT Deposit**\n\n"
        "💵 **সর্বনিম্ন:** $1\n"
        "💵 **সর্বোচ্চ:** $50\n\n"
        "👉 **কত USDT ডিপোজিট করবেন? লিখুন।**",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    await call.answer()


async def dep_binance_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ **সঠিক USDT পরিমাণ লিখুন।**", parse_mode="Markdown")
        return

    if amount < 1 or amount > 50:
        await message.answer("⚠️ **USDT পরিমাণ $1 থেকে $50 এর মধ্যে হতে হবে।**", parse_mode="Markdown")
        return

    await state.update_data(usdt=amount)
    await state.set_state(DepositState.txid)

    bdt = amount * USDT_RATE_BDT
    await message.answer(
        "🟡 **USDT — BEP20 ডিপোজিট**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💱 **ডিপোজিট রেট:** 1 USDT = {money(USDT_RATE_BDT)}৳\n"
        f"💰 **আপনার পরিমাণ:** {money(amount)} USDT\n"
        f"💵 **ব্যালেন্সে যোগ হবে:** {money(bdt)}৳\n\n"
        "📌 **BEP20 / BSC নেটওয়ার্ক ব্যবহার করে নিচের ঠিকানায় USDT পাঠান:**\n\n"
        f"`{BINANCE_DEPOSIT_ADDRESS}`\n\n"
        "📝 **পেমেন্ট করার পর TxID / Transaction Hash পাঠান।**",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )


@dp.message(DepositState.txid)
async def dep_binance_txid(message: Message, state: FSMContext):
    txid = message.text.strip()
    if not re.fullmatch(r"0x[a-fA-F0-9]{64}", txid):
        await message.answer(
            "❌ **TxID সঠিক নয়।**\n"
            "0x দিয়ে শুরু হওয়া 64-hex-character Transaction Hash পাঠান।",
            parse_mode="Markdown"
        )
        return

    data = await state.get_data()
    usdt = Decimal(str(data["usdt"]))
    bdt = usdt * USDT_RATE_BDT
    oid = order_no()

    con = db()
    con.execute("""
        INSERT INTO deposits(user_id,method,amount,txid,order_no,status,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?)
    """, (
        message.from_user.id, "Binance", float(bdt), txid, oid,
        "Pending", now_iso(), now_iso()
    ))
    con.commit()
    con.close()

    await state.clear()
    await message.answer(
        "✅ **আপনার ডিপোজিটের অনুরোধ জমা করা হয়েছে।**\n"
        "⏳ **অনুমোদনের জন্য অপেক্ষা করুন।**",
        parse_mode="Markdown",
        reply_markup=main_keyboard(message.from_user.id)
    )

    await send_admin_deposit(message.from_user, "Binance", bdt, txid, oid)


async def send_admin_deposit(user, method, amount, txid, oid):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Approve", callback_data=f"adm_dep_ok:{oid}"),
         InlineKeyboardButton(text="❌ Reject", callback_data=f"adm_dep_no:{oid}")],
    ])
    username = f"@{user.username}" if user.username else "—"
    await bot.send_message(
        ADMIN_ID,
        "📥 **NEW DEPOSIT REQUEST**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 **নাম:** {user.full_name}\n"
        f"🔗 **Username:** {username}\n"
        f"🆔 **User ID:** {user.id}\n"
        f"💳 **Method:** {method}\n"
        f"💰 **Amount:** {money(amount)}৳\n"
        f"📝 **TxID:** {txid}\n"
        f"🆔 **Order No:** {oid}\n"
        f"📌 **Status:** Pending",
        parse_mode="Markdown",
        reply_markup=kb
    )


# =========================
# ACCOUNT (BODAG/BOLD FORMAT)
# =========================
@dp.message(F.text == "👤 একাউন্ট")
async def account(message: Message):
    row = get_user(message)

    # ✅ FIX: আগে এখানে ৯টি variable-এ unpack করা হচ্ছিল, কিন্তু users টেবিলে
    # ১৪টি column থাকায় "too many values to unpack" error হয়ে
    # একাউন্ট বাটন একদমই কাজ করত না। এখন index দিয়ে নিরাপদে পড়া হচ্ছে।
    uid = row[0]
    name = row[1]
    username = row[2]
    main = row[3]
    deposit = row[4]
    bonus = row[5]
    referral = row[6]

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT plan, expires_at FROM plans
        WHERE user_id=? AND active=1 ORDER BY expires_at
    """, (uid,))
    active = cur.fetchall()
    con.close()

    vip1 = "সক্রিয় নয়"
    vip2 = "সক্রিয় নয়"
    now = datetime.now(timezone.utc)

    for plan, expires in active:
        try:
            days = max(0, (datetime.fromisoformat(expires) - now).days)
        except Exception:
            days = 0
        if plan == "VIP1":
            vip1 = f"{days} দিন"
        if plan == "VIP2":
            vip2 = f"{days} দিন"

    await message.answer(
        "👤 **আমার অ্যাকাউন্টের তথ্য**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **ব্যবহারকারীর নাম:** {name}\n"
        f"🔗 **ইউজারনেম:** @{username if username else 'নেই'}\n"
        f"🆔 **ইউজার আইডি:** {uid}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💰 **BALANCE DETAILS**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **মোট ব্যালেন্স:** {money(main)}৳\n"
        f"📥 **ডিপোজিট ব্যালেন্স:** {money(deposit)}৳\n"
        f"🎁 **ডিপোজিট বোনাস:** {money(bonus)}৳\n"
        f"🫂 **রেফার ব্যালেন্স:** {money(referral)}৳\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 **ACCOUNT STATUS**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏳ **Plan এর মেয়াদ:**\n"
        f"• **VIP 1** — {vip1}\n"
        f"• **VIP 2** — {vip2}\n"
        "🚫 **নিষিদ্ধ:** না\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ **আপনার অ্যাকাউন্টের সকল তথ্য এখানে দেখানো হয়েছে।**",
        parse_mode="Markdown"
    )


# =========================
# WITHDRAW
# =========================
@dp.message(F.text == "💸 Withdraw")
async def withdraw_menu(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 bKash", callback_data="wd_bkash"),
         InlineKeyboardButton(text="💠 Nagad", callback_data="wd_nagad")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_inline")]
    ])
    await message.answer("💸 **Withdraw**\n\nএকটি পেমেন্ট মেথড নির্বাচন করুন।", parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data.in_(["wd_bkash", "wd_nagad"]))
async def wd_method(call: CallbackQuery, state: FSMContext):
    method = "bKash" if call.data == "wd_bkash" else "Nagad"
    await state.update_data(method=method)
    await state.set_state(WithdrawState.account)
    await call.message.answer(
        f"📲 **{method}**\n\n"
        "আপনার সঠিক ১১ ডিজিটের নম্বরটি লিখুন。\n"
        "উদাহরণ: `017XXXXXXXX`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    await call.answer()


@dp.message(WithdrawState.account)
async def wd_account(message: Message, state: FSMContext):
    account_no = message.text.strip()
    if not re.fullmatch(r"01[3-9]\d{8}", account_no):
        await message.answer("❌ **সঠিক ১১ ডিজিটের মোবাইল নম্বর দিন।**", parse_mode="Markdown")
        return

    await state.update_data(account=account_no)
    await state.set_state(WithdrawState.amount)

    row = get_user(message)
    balance = Decimal(str(row[3]))

    await message.answer(
        f"💰 **আপনার বর্তমান ব্যালেন্স:** {money(balance)}৳\n\n"
        "📌 **উইথড্র সীমা:**\n"
        "• **সর্বনিম্ন:** 100৳\n"
        "• **সর্বোচ্চ:** 25,000৳\n\n"
        f"📲 **নম্বর:** {account_no}\n\n"
        "👉 **কত টাকা উইথড্র করতে চান? সংখ্যায় লিখুন।**",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )


@dp.message(WithdrawState.amount)
async def wd_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ **সঠিক পরিমাণ লিখুন।**", parse_mode="Markdown")
        return

    row = get_user(message)
    balance = Decimal(str(row[3]))

    if amount < 100 or amount > 25000 or amount > balance:
        await message.answer(
            "⚠️ **উইথড্র পরিমাণ সঠিক নয়!**\n"
            "💰 **উইথড্র করার সীমা:**\n"
            "• **সর্বনিম্ন** — 100৳\n"
            "• **সর্বোচ্চ** — 25,000৳\n"
            f"আপনার বর্তমান ব্যালেন্স **{money(balance)}৳**\n\n"
            "👉 **অনুগ্রহ করে সঠিক পরিমাণ লিখে আবার চেষ্টা করুন।**",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard()
        )
        return

    data = await state.get_data()
    method = data["method"]
    account_no = data["account"]

    con = db()
    cur = con.cursor()
    cur.execute("UPDATE users SET main_balance=main_balance-? WHERE user_id=? AND main_balance>=?",
                (float(amount), message.from_user.id, float(amount)))
    if cur.rowcount != 1:
        con.rollback()
        con.close()
        await message.answer("❌ **ব্যালেন্স পরিবর্তিত হয়েছে। আবার চেষ্টা করুন।**", parse_mode="Markdown")
        return

    cur.execute("""
        INSERT INTO withdrawals(user_id,method,account,amount,status,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?)
    """, (message.from_user.id, method, account_no, float(amount), "Pending", now_iso(), now_iso()))
    wid = cur.lastrowid
    con.commit()
    con.close()

    await state.clear()
    await message.answer(
        f"✅ **আপনার 💸 {money(amount)}৳ উইথড্র রিকোয়েস্ট সফলভাবে জমা হয়েছে!**\n\n"
        "⏳ **প্রসেসিং সময়:** Admin review\n"
        "অনুমোদন সম্পন্ন হওয়া পর্যন্ত অপেক্ষা করুন।",
        parse_mode="Markdown",
        reply_markup=main_keyboard(message.from_user.id)
    )

    await send_admin_withdraw(message.from_user, wid, method, account_no, amount)


async def send_admin_withdraw(user, wid, method, account_no, amount):
    username = f"@{user.username}" if user.username else "—"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Approve", callback_data=f"adm_wd_ok:{wid}"),
         InlineKeyboardButton(text="❌ Reject", callback_data=f"adm_wd_no:{wid}")]
    ])
    await bot.send_message(
        ADMIN_ID,
        "📤 **NEW WITHDRAW REQUEST**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 **নাম:** {user.full_name}\n"
        f"🔗 **Username:** {username}\n"
        f"🆔 **User ID:** {user.id}\n"
        f"💳 **Method:** {method}\n"
        f"📲 **Account:** {account_no}\n"
        f"💰 **Amount:** {money(amount)}৳\n"
        f"🆔 **Request ID:** {wid}\n"
        f"📌 **Status:** Pending",
        parse_mode="Markdown",
        reply_markup=kb
    )


# =========================
# REFERRAL
# =========================
@dp.message(F.text == "👥 Referral")
async def referral(message: Message):
    uid = message.from_user.id
    con = db()
    cur = con.cursor()
    cur.execute("SELECT referral_balance FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    con.close()
    refbal = row[0] if row else 0

    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{uid}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Share করুন", switch_inline_query=link)],
        [InlineKeyboardButton(text="📋 Rules", callback_data="ref_rules")]
    ])
    await message.answer(
        "👥 **Referral Center**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔗 **আপনার Referral Link:**\n`{link}`\n\n"
        "👥 **মোট referrals:** 0\n"
        f"💰 **Referral earnings:** {money(refbal)}৳\n\n"
        "📌 **রেফার করা ব্যক্তি ডিপোজিট করলে, প্রযোজ্য শর্ত অনুযায়ী "
        "তার ডিপোজিট থেকে ৫% কমিশন গণনা করা যেতে পারে।**",
        parse_mode="Markdown",
        reply_markup=kb
    )


@dp.callback_query(F.data == "ref_rules")
async def ref_rules(call: CallbackQuery):
    await call.message.answer(
        "📋 **Referral Rules**\n\n"
        "রেফার করা ব্যক্তি ডিপোজিট করলে তার ডিপোজিটের ৫% কমিশন "
        "সিস্টেমের নির্ধারিত নিয়ম অনুযায়ী Referral Balance-এ যোগ হতে পারে।",
        parse_mode="Markdown"
    )
    await call.answer()


# =========================
# DAILY EARNINGS
# =========================
@dp.message(F.text == "📊 Daily Earnings")
async def daily_earnings(message: Message):
    uid = message.from_user.id
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id,plan,amount,activated_at,expires_at,last_claim_date
        FROM plans WHERE user_id=? AND active=1 ORDER BY id DESC
    """, (uid,))
    plans = cur.fetchall()
    con.close()

    now = datetime.now(timezone.utc)
    lines = ["📊 **Daily Earnings**", "━━━━━━━━━━━━━━━━━━"]

    valid = []
    for pid, plan, amount, activated, expires, last_claim in plans:
        try:
            exp = datetime.fromisoformat(expires)
        except Exception:
            exp = now

        if now >= exp:
            con = db()
            con.execute("UPDATE plans SET active=0 WHERE id=?", (pid,))
            con.commit()
            con.close()
            continue

        daily = Decimal(str(amount)) * DEMO_DAILY_RATE
        valid.append((pid, plan, amount, daily, last_claim))
        lines.append(
            f"💎 **{plan}** — {money(amount)}৳\n"
            f"📅 **মেয়াদ শেষ:** {exp.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"📊 **Demo daily amount:** {money(daily)}৳\n"
        )

    if not valid:
        lines.append("❌ **কোনো active plan নেই।**")
        await message.answer("\n".join(lines), parse_mode="Markdown")
        return

    lines.append("🕗 **Claim window:** 08:00–24:00")
    lines.append("⚠️ **Claim না করলে ওই দিনের amount পরের দিনে carry হবে না।**")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧮 Today Earnings Claim", callback_data="claim_today")]
    ])
    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data == "claim_today")
async def claim_today(call: CallbackQuery):
    uid = call.from_user.id
    now = datetime.now(timezone.utc)

    if now.hour < 8:
        await call.answer("⏳ Claim window সকাল ৮টা থেকে শুরু হবে।", show_alert=True)
        return

    today = now.date().isoformat()
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id,plan,amount,last_claim_date FROM plans
        WHERE user_id=? AND active=1
    """, (uid,))
    rows = cur.fetchall()

    total = Decimal("0")
    claimed = []

    for pid, plan, amount, last_claim in rows:
        cur.execute("SELECT expires_at FROM plans WHERE id=?", (pid,))
        exp_row = cur.fetchone()
        if not exp_row:
            continue

        try:
            exp = datetime.fromisoformat(exp_row[0])
        except Exception:
            continue

        if now >= exp:
            cur.execute("UPDATE plans SET active=0 WHERE id=?", (pid,))
            continue

        if last_claim == today:
            continue

        earning = Decimal(str(amount)) * DEMO_DAILY_RATE
        total += earning
        claimed.append((pid, plan, earning))

        cur.execute("""
            UPDATE plans SET last_claim_date=? WHERE id=?
        """, (today, pid))
        cur.execute("""
            INSERT INTO earnings(user_id,plan_id,amount,claim_date,created_at)
            VALUES(?,?,?,?,?)
        """, (uid, pid, float(earning), today, now_iso()))

    if total > 0:
        cur.execute("""
            UPDATE users
            SET main_balance=main_balance+?, total_earnings=total_earnings+?
            WHERE user_id=?
        """, (float(total), float(total), uid))

    con.commit()
    con.close()

    if total == 0:
        await call.answer("⚠️ আজকের earnings ইতিমধ্যে করা হয়েছে বা available নেই।", show_alert=True)
        return

    await call.message.answer(
        "🎉 **Today Earnings Claim Successful**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 **মোট যোগ হয়েছে:** {money(total)}৳\n"
        f"📦 **Active plans claimed:** {len(claimed)}\n\n"
        "ℹ️ এটি DEMO/SIMULATION calculation; কোনো নির্দিষ্ট লাভ নিশ্চিত নয়।",
        parse_mode="Markdown"
    )
    await call.answer("✅ Claim সম্পন্ন হয়েছে।")


# =========================
# BONUS
# =========================
@dp.message(F.text == "🎁 Bonus Center")
async def bonus_center(message: Message):
    get_user(message)  # ✅ FIX: /start না দিলেও user row তৈরি হবে (আগে crash হতো)
    uid = message.from_user.id
    con = db()
    cur = con.cursor()
    cur.execute("SELECT bonus_balance FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    bal = row[0] if row else 0
    con.close()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Daily Free 5৳ Claim", callback_data="bonus_claim")],
        [InlineKeyboardButton(text="📜 Bonus History", callback_data="bonus_history")]
    ])
    await message.answer(
        "🎁 **Bonus Center**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Available Bonus:** {money(bal)}৳\n"
        "🎁 **Active Rewards:** Daily Free 5৳\n\n"
        "📌 **Bonus Balance সরাসরি withdraw বা plan purchase-এর জন্য ব্যবহার করা যাবে না।**\n"
        "Admin নির্ধারিত শর্তে Bonus Balance Main Balance-এ convert করতে পারে।",
        parse_mode="Markdown",
        reply_markup=kb
    )


@dp.callback_query(F.data == "bonus_claim")
async def bonus_claim(call: CallbackQuery):
    uid = call.from_user.id
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT 1 FROM bonuses WHERE user_id=? AND type='daily' AND date(created_at)=date('now')
    """, (uid,))
    if cur.fetchone():
        con.close()
        await call.answer("আজকের 5৳ Bonus ইতিমধ্যে নেওয়া হয়েছে।", show_alert=True)
        return

    cur.execute("UPDATE users SET bonus_balance=bonus_balance+5 WHERE user_id=?", (uid,))
    cur.execute("""
        INSERT INTO bonuses(user_id,amount,type,created_at)
        VALUES(?,?,?,?)
    """, (uid, 5, "daily", now_iso()))
    con.commit()
    con.close()

    await call.message.answer("🎁 **আজকের 5৳ Bonus আপনার Bonus Balance-এ যোগ হয়েছে।**", parse_mode="Markdown")
    await call.answer("✅ Bonus claimed!")


@dp.callback_query(F.data == "bonus_history")
async def bonus_history(call: CallbackQuery):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT amount,type,created_at FROM bonuses
        WHERE user_id=? ORDER BY id DESC LIMIT 5
    """, (call.from_user.id,))
    rows = cur.fetchall()
    con.close()

    if not rows:
        text = "📜 **Bonus History**\n\nকোনো bonus history পাওয়া যায়নি।"
    else:
        text = "📜 **Bonus History**\n━━━━━━━━━━━━━━━━━━\n"
        for amount, typ, created in rows:
            text += f"🎁 +{money(amount)}৳ — {typ}\n📅 {created[:10]}\n\n"

    await call.message.answer(text, parse_mode="Markdown")
    await call.answer()


# =========================
# PLANS
# =========================
def plan_keyboard():
    buttons = []
    names = list(PLANS.keys())
    for i in range(0, len(names), 3):
        row = [
            InlineKeyboardButton(text=f"💎 {p}", callback_data=f"plan:{p}")
            for p in names[i:i+3]
        ]
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(F.text == "💎 Available Plans")
async def available_plans(message: Message):
    await message.answer(
        "💎 **Available Plans**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "নিচে একটি Plan নির্বাচন করুন।\n\n"
        "📅 **মেয়াদ:** 4 দিন\n"
        "📊 **Daily calculation:** 34% (DEMO/SIMULATION)\n"
        "⚠️ **কোনো নির্দিষ্ট লাভ নিশ্চিত নয়।**",
        parse_mode="Markdown",
        reply_markup=plan_keyboard()
    )


@dp.callback_query(F.data.startswith("plan:"))
async def plan_details(call: CallbackQuery):
    plan = call.data.split(":", 1)[1]
    amount = PLANS.get(plan)
    if amount is None:
        await call.answer("Plan পাওয়া যায়নি।", show_alert=True)
        return

    daily = Decimal(str(amount)) * DEMO_DAILY_RATE
    total_demo = daily * PLAN_DAYS

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Plan Buy", callback_data=f"buy:{plan}")],
        [InlineKeyboardButton(text="⬅️ Plans", callback_data="plans_back")]
    ])

    await call.message.answer(
        f"💼 **{plan} Plan Details**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Amount:** {amount}৳\n"
        f"📅 **Duration:** {PLAN_DAYS} days\n"
        f"📊 **Demo daily amount:** {money(daily)}৳\n"
        f"📈 **Demo total:** {money(total_demo)}৳\n\n"
        "⚠️ **এটি শুধুমাত্র DEMO/SIMULATION calculation; কোনো নির্দিষ্ট লাভ নিশ্চিত নয়।**",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await call.answer()


@dp.callback_query(F.data == "plans_back")
async def plans_back(call: CallbackQuery):
    await call.message.answer(
        "💎 **Available Plans**\nএকটি Plan নির্বাচন করুন।",
        parse_mode="Markdown",
        reply_markup=plan_keyboard()
    )
    await call.answer()


@dp.callback_query(F.data.startswith("buy:"))
async def buy_plan(call: CallbackQuery):
    plan = call.data.split(":", 1)[1]
    amount = PLANS.get(plan)
    uid = call.from_user.id

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM plans
        WHERE user_id=? AND plan=? AND active=1
    """, (uid, plan))
    active_count = cur.fetchone()[0]

    if active_count >= 2:
        con.close()
        await call.message.answer(
            "⚠️ **Plan Limit Reached**\n"
            f"দুঃখিত! আপনার {plan} Plan বর্তমানে সর্বোচ্চ ২টি সক্রিয় রয়েছে। ❌\n\n"
            "📅 **এই Plan-এর যেকোনো ১টির মেয়াদ শেষ না হওয়া পর্যন্ত "
            "একই Plan আর নতুন করে সক্রিয় করতে পারবেন না।**\n\n"
            "💎 তবে অন্যান্য Available Plans থেকে Plan নির্বাচন করতে পারবেন।",
            parse_mode="Markdown"
        )
        await call.answer()
        return

    cur.execute("""
        SELECT main_balance,deposit_balance FROM users WHERE user_id=?
    """, (uid,))
    row = cur.fetchone()
    main = Decimal(str(row[0]))
    deposit = Decimal(str(row[1]))
    available = main + deposit

    if available < amount:
        con.close()
        await call.message.answer(
            "❌ **আপনার ডিপোজিট ও মেইন balance এ পর্যাপ্ত টাকা নেই।**\n"
            "দয়া করে আগে যোগ করুন, পরে আবার চেষ্টা করুন। ধন্যবাদ। ❤️",
            parse_mode="Markdown"
        )
        await call.answer()
        return

    remaining = Decimal(str(amount))
    from_main = min(main, remaining)
    remaining -= from_main
    from_deposit = remaining

    cur.execute("""
        UPDATE users
        SET main_balance=main_balance-?, deposit_balance=deposit_balance-?
        WHERE user_id=?
    """, (float(from_main), float(from_deposit), uid))

    activated = datetime.now(timezone.utc)
    expires = activated + timedelta(days=PLAN_DAYS)

    cur.execute("""
        INSERT INTO plans(user_id,plan,amount,activated_at,expires_at,active)
        VALUES(?,?,?,?,?,1)
    """, (uid, plan, amount, activated.isoformat(), expires.isoformat()))

    con.commit()
    con.close()

    daily = Decimal(str(amount)) * DEMO_DAILY_RATE

    await call.message.answer(
        f"🎊 **অভিনন্দন! আপনার {plan} Plan সফলভাবে সক্রিয় হয়েছে।** ✅\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💎 **Plan:** {plan}\n"
        f"💰 **বিনিয়োগ:** ৳{amount}\n"
        f"📅 **মেয়াদ:** {PLAN_DAYS} দিন\n"
        f"📊 **Demo দৈনিক আয়:** ৳{money(daily)}\n\n"
        "💵 Daily Earnings থেকে claim করতে পারবেন।\n"
        "⏳ Plan-এর মেয়াদ সক্রিয় হওয়ার সময় থেকে গণনা হবে।\n\n"
        "⚠️ **Daily amount একটি DEMO/SIMULATION calculation; "
        "কোনো নির্দিষ্ট লাভ নিশ্চিত নয়।**",
        parse_mode="Markdown"
    )
    await call.answer("✅ Plan activated!")


# =========================
# TRANSACTION HISTORY
# =========================
@dp.message(F.text == "🧾 Transaction History")
async def transaction_history(message: Message):
    uid = message.from_user.id
    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT method,amount,status,order_no,created_at FROM deposits
        WHERE user_id=? ORDER BY id DESC LIMIT 7
    """, (uid,))
    deps = cur.fetchall()

    cur.execute("""
        SELECT method,amount,status,created_at FROM withdrawals
        WHERE user_id=? ORDER BY id DESC LIMIT 7
    """, (uid,))
    wds = cur.fetchall()

    cur.execute("""
        SELECT amount,claim_date,created_at FROM earnings
        WHERE user_id=? ORDER BY id DESC LIMIT 7
    """, (uid,))
    earns = cur.fetchall()
    con.close()

    text = "🧾 **Transaction History**\n━━━━━━━━━━━━━━━━━━\n\n"
    text += "📥 **Deposit History**\n"
    if deps:
        for method, amount, status, oid, created in deps:
            text += f"• {method} — {money(amount)}৳ — {status}\n  🆔 `{oid}`\n"
    else:
        text += "• কোনো রেকর্ড নেই\n"

    text += "\n📤 **Withdraw History**\n"
    if wds:
        for method, amount, status, created in wds:
            text += f"• {method} — {money(amount)}৳ — {status}\n"
    else:
        text += "• কোনো রেকর্ড নেই\n"

    text += "\n📊 **Earnings History**\n"
    if earns:
        for amount, claim_date, created in earns:
            text += f"• +{money(amount)}৳ — {claim_date}\n"
    else:
        text += "• কোনো রেকর্ড নেই\n"

    await message.answer(text, parse_mode="Markdown")


# =========================
# HELP
# =========================
async def show_help(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Support Center", url="https://t.me/Nikan_Support01")],
        [InlineKeyboardButton(text="📢 Official Channel", url="https://t.me/NIKAN_EARN")],
        [InlineKeyboardButton(text="📋 Rules", callback_data="help_rules")]
    ])
    await message.answer(
        "🆘 **Help & Support**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "• Account Problem\n"
        "• Deposit Problem\n"
        "• Withdraw Problem\n"
        "• Referral Problem\n"
        "• Other Issues\n\n"
        "🕐 **Support Hours:** Available as stated by the service.",
        parse_mode="Markdown",
        reply_markup=kb
    )


@dp.message(F.text == "🆘 Help & Support")
async def help_menu(message: Message):
    await show_help(message)


@dp.callback_query(F.data == "help_rules")
async def help_rules(call: CallbackQuery):
    await call.message.answer(
        "🌐 **About NIKAN**\n\n"
        "NIKAN একটি online earning service demo interface, "
        "যেখানে earning features, referral program এবং available plans "
        "দেখানো হয়।\n\n"
        "📊 Track Your Earnings\n"
        "👥 Referral Program\n"
        "🧾 Transaction History\n"
        "🆘 User Support\n\n"
        "⚠️ **কোনো নির্দিষ্ট লাভ নিশ্চিত নয়।**",
        parse_mode="Markdown"
    )
    await call.answer()


# =========================
# ADMIN: DEPOSIT APPROVE/REJECT
# =========================
@dp.callback_query(F.data.startswith("adm_dep_ok:"))
async def admin_dep_approve(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Unauthorized", show_alert=True)
        return

    oid = call.data.split(":", 1)[1]
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id,user_id,amount,txid,status FROM deposits WHERE order_no=?
    """, (oid,))
    row = cur.fetchone()

    if not row:
        con.close()
        await call.answer("Request পাওয়া যায়নি।", show_alert=True)
        return

    did, uid, amount, txid, status = row
    if status == "Approved":
        con.close()
        await call.answer("Already approved.", show_alert=True)
        return

    cur.execute("""
        UPDATE deposits SET status='Approved',updated_at=? WHERE id=?
    """, (now_iso(), did))
    cur.execute("""
        UPDATE users SET main_balance=main_balance+?, deposit_balance=deposit_balance+?
        WHERE user_id=?
    """, (amount, amount, uid))
    con.commit()
    con.close()

    await bot.send_message(
        uid,
        "🎉 **Deposit Successful!**\n\n"
        f"আপনার {money(amount)} Deposit সফলভাবে সম্পন্ন হয়েছে। ✅\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Deposit Amount:** {money(amount)} BDT\n"
        f"📝 **Transaction ID:** `{txid}`\n"
        f"🆔 **Order Number:** `{oid}`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💳 আপনার মূল ডিপোজিট ব্যালেন্সে **{money(amount)} BDT** যোগ করা হয়েছে।\n"
        "ধন্যবাদ। ❤️",
        parse_mode="Markdown"
    )
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("Deposit approved.")


@dp.callback_query(F.data.startswith("adm_dep_no:"))
async def admin_dep_reject(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Unauthorized", show_alert=True)
        return

    oid = call.data.split(":", 1)[1]
    con = db()
    cur = con.cursor()
    cur.execute("SELECT id,user_id,amount,txid,status FROM deposits WHERE order_no=?", (oid,))
    row = cur.fetchone()

    if not row:
        con.close()
        await call.answer("Request পাওয়া যায়নি।", show_alert=True)
        return

    did, uid, amount, txid, status = row
    cur.execute("""
        UPDATE deposits SET status='Rejected',reason=?,updated_at=? WHERE id=?
    """, ("Transaction/payment could not be verified.", now_iso(), did))
    con.commit()
    con.close()

    await bot.send_message(
        uid,
        "❌ **Deposit Failed!**\n\n"
        "আপনার দেওয়া Transaction ID সঠিক নয় অথবা এই Transaction ID-এর মাধ্যমে কোনো পেমেন্ট শনাক্ত করা যায়নি।\n\n"
        f"📝 **Transaction ID:** `{txid}`\n"
        f"🆔 **Order No:** `{oid}`\n\n"
        "🔄 **অনুগ্রহ করে সঠিক Transaction ID দিয়ে আবার চেষ্টা করুন।** "
        "পেমেন্ট সম্পন্ন না করে থাকলে আগে পেমেন্ট সম্পন্ন করুন।",
        parse_mode="Markdown"
    )
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("Deposit rejected.")


# =========================
# ADMIN: WITHDRAW APPROVE/REJECT
# =========================
@dp.callback_query(F.data.startswith("adm_wd_ok:"))
async def admin_wd_approve(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Unauthorized", show_alert=True)
        return

    try:
        wid = int(call.data.split(":", 1)[1])
    except ValueError:
        await call.answer("Invalid request.", show_alert=True)
        return

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT user_id,method,account,amount,status FROM withdrawals WHERE id=?
    """, (wid,))
    row = cur.fetchone()

    if not row:
        con.close()
        await call.answer("Request পাওয়া যায়নি।", show_alert=True)
        return

    uid, method, account_no, amount, status = row
    if status == "Approved":
        con.close()
        await call.answer("Already approved.", show_alert=True)
        return

    cur.execute("""
        UPDATE withdrawals SET status='Approved',updated_at=? WHERE id=?
    """, (now_iso(), wid))
    con.commit()
    con.close()

    await bot.send_message(
        uid,
        "🎊 **উইথড্র কনফার্মড!**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 **পরিমাণ:** {money(amount)}৳\n"
        "🟢 আপনার পেমেন্ট রিকোয়েস্ট সফলভাবে অনুমোদিত হয়েছে।\n"
        f"📲 নির্ধারিত **{method}** নম্বর: `{account_no}`\n\n"
        "ℹ️ DEMO mode-এ কোনো বাস্তব পেমেন্ট পাঠানো হয় না।",
        parse_mode="Markdown"
    )
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("Withdraw approved.")


@dp.callback_query(F.data.startswith("adm_wd_no:"))
async def admin_wd_reject(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Unauthorized", show_alert=True)
        return

    try:
        wid = int(call.data.split(":", 1)[1])
    except ValueError:
        await call.answer("Invalid request.", show_alert=True)
        return

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT user_id,amount,status FROM withdrawals WHERE id=?
    """, (wid,))
    row = cur.fetchone()

    if not row:
        con.close()
        await call.answer("Request পাওয়া যায়নি।", show_alert=True)
        return

    uid, amount, status = row
    if status == "Rejected":
        con.close()
        await call.answer("Already rejected.", show_alert=True)
        return

    cur.execute("""
        UPDATE withdrawals SET status='Rejected',reason=?,updated_at=? WHERE id=?
    """, ("Withdrawal request rejected by admin.", now_iso(), wid))
    cur.execute("""
        UPDATE users SET main_balance=main_balance+? WHERE user_id=?
    """, (amount, uid))
    con.commit()
    con.close()

    await bot.send_message(
        uid,
        "🚫 **WITHDRAW CANCELLED**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Amount:** {money(amount)}৳\n"
        "আপনার উইথড্র রিকোয়েস্টটি বাতিল করা হয়েছে。\n"
        f"↩️ **{money(amount)}৳** আপনার অ্যাকাউন্ট ব্যালেন্সে পুনরায় যোগ হয়েছে。\n\n"
        "ℹ️ কারণ: Withdrawal request rejected by admin.",
        parse_mode="Markdown"
    )
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("Withdraw rejected.")


# =========================
# INLINE CANCEL
# =========================
@dp.callback_query(F.data == "cancel_inline")
async def inline_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("❌ **বাতিল করা হয়েছে।**", parse_mode="Markdown", reply_markup=main_keyboard(call.from_user.id))
    await call.answer()


# =========================
# ADVANCED ADMIN PANEL FUNCTIONS
# =========================
def getset(k, default=''):
    con = db()
    r = con.execute('SELECT value FROM settings WHERE key=?', (k,)).fetchone()
    con.close()
    return r[0] if r else default


def setset(k, v):
    con = db()
    con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
    con.commit()
    con.close()


def role(uid):
    con = db()
    r = con.execute('SELECT role FROM admins WHERE user_id=?', (uid,)).fetchone()
    con.close()
    return r[0] if r else None


def admin_ok(uid): 
    return role(uid) is not None


def super_ok(uid): 
    return uid == OWNER_ID


def a_toggle(label, key): 
    return f'{label}: ' + ('🟢 ON' if getset(key) == '1' else '🔴 OFF')


def admin_kb(uid):
    rows = [
      [InlineKeyboardButton(text='📊 Dashboard', callback_data='x:dash')],
      [InlineKeyboardButton(text='⚙️ Bot Controls', callback_data='x:controls'), InlineKeyboardButton(text='💳 Payment Controls', callback_data='x:pay')],
      [InlineKeyboardButton(text='📈 Limits', callback_data='x:limits'), InlineKeyboardButton(text='📣 Force Join', callback_data='x:force')],
      [InlineKeyboardButton(text='👤 User Control', callback_data='x:user'), InlineKeyboardButton(text='📥 Deposits', callback_data='x:deps')],
      [InlineKeyboardButton(text='💸 Withdraws', callback_data='x:wds'), InlineKeyboardButton(text='📢 Broadcast', callback_data='x:broadcast')],
      [InlineKeyboardButton(text='✉️ User Broadcast', callback_data='x:ubroadcast')],
    ]
    if super_ok(uid): 
        rows.append([InlineKeyboardButton(text='👑 Admin Management', callback_data='x:admins')])
    rows.append([InlineKeyboardButton(text='⬅️ Main Menu', callback_data='x:close')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


class AdvancedAdminState(StatesGroup):
    generic_value = State(); user_id = State(); user_action = State(); user_value = State()
    broadcast = State(); user_broadcast_id = State(); user_broadcast_text = State()
    gateway_url = State(); number = State(); force_chat = State(); force_link = State()
    add_admin = State(); remove_admin = State(); reject_reason = State(); plan_uid = State(); plan_name = State()


@dp.message(F.text == '🔧 Admin Panel')
async def advanced_admin_button(message: Message):
    if not admin_ok(message.from_user.id):
        await message.answer('❌ আপনার Admin access নেই।')
        return
    await message.answer('🔐 **ADMIN CONTROL PANEL**\n━━━━━━━━━━━━━━━━━━\nসম্পূর্ণ dynamic control interface', parse_mode="Markdown", reply_markup=admin_kb(message.from_user.id))


@dp.callback_query(F.data == 'x:dash')
async def x_dash(call: CallbackQuery):
    if not admin_ok(call.from_user.id): 
        return await call.answer('Admin only', show_alert=True)
    con = db()
    cur = con.cursor()
    users = cur.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    vip = cur.execute('SELECT COUNT(DISTINCT user_id) FROM plans').fetchone()[0] if cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='plans'").fetchone() else 0
    fund = cur.execute("SELECT COALESCE(SUM(amount),0) FROM deposits WHERE status IN ('Approved','Success')").fetchone()[0]
    wth = cur.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status IN ('Approved','Success')").fetchone()[0]
    con.close()
    await call.message.edit_text(f'📊 **LIVE ADMIN DASHBOARD**\n━━━━━━━━━━━━━━━━━━\n👥 **Total Users:** {users}\n💎 **VIP Buyers:** {vip}\n💰 **Total Fund:** {money(fund)}৳\n💸 **Total Withdraw:** {money(wth)}৳\n\n🤖 **Bot:** {"🟢 ON" if getset("bot_enabled")=="1" else "🔴 OFF"}', parse_mode="Markdown", reply_markup=admin_kb(call.from_user.id))
    await call.answer()


@dp.callback_query(F.data == 'x:controls')
async def x_controls(call: CallbackQuery):
    if not admin_ok(call.from_user.id): 
        return await call.answer('Admin only', show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text=a_toggle('🤖 Bot', 'bot_enabled'), callback_data='x:t:bot_enabled')],
      [InlineKeyboardButton(text=a_toggle('💰 Fund', 'fund_enabled'), callback_data='x:t:fund_enabled')],
      [InlineKeyboardButton(text=a_toggle('💸 Withdraw', 'withdraw_enabled'), callback_data='x:t:withdraw_enabled')],
      [InlineKeyboardButton(text='⬅️ Back', callback_data='x:open')]])
    await call.message.edit_text('⚙️ **BOT / MASTER CONTROLS**', parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith('x:t:'))
async def x_toggle(call: CallbackQuery):
    if not admin_ok(call.from_user.id): 
        return await call.answer('Admin only', show_alert=True)
    key = call.data.split(':')[-1]
    setset(key, '0' if getset(key) == '1' else '1')
    await call.answer('Updated')
    await x_controls(call)


@dp.callback_query(F.data == 'x:pay')
async def x_pay(call: CallbackQuery):
    if not admin_ok(call.from_user.id): 
        return await call.answer('Admin only', show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text=a_toggle('Dep bKash', 'dep_bkash_enabled'), callback_data='x:t:dep_bkash_enabled'), InlineKeyboardButton(text=a_toggle('Dep Nagad', 'dep_nagad_enabled'), callback_data='x:t:dep_nagad_enabled')],
      [InlineKeyboardButton(text=a_toggle('Wth bKash', 'wth_bkash_enabled'), callback_data='x:t:wth_bkash_enabled'), InlineKeyboardButton(text=a_toggle('Wth Nagad', 'wth_nagad_enabled'), callback_data='x:t:wth_nagad_enabled')],
      [InlineKeyboardButton(text=a_toggle('Wth Rocket', 'wth_rocket_enabled'), callback_data='x:t:wth_rocket_enabled'), InlineKeyboardButton(text=a_toggle('Wth Upay', 'wth_upay_enabled'), callback_data='x:t:wth_upay_enabled')],
      [InlineKeyboardButton(text='🔄 All Withdraw ON/OFF', callback_data='x:allw')],
      [InlineKeyboardButton(text='📲 Set bKash Number', callback_data='x:num:bKash'), InlineKeyboardButton(text='📲 Set Nagad Number', callback_data='x:num:Nagad')],
      [InlineKeyboardButton(text='🔗 Add/Edit bKash Gateway', callback_data='x:gw:bKash'), InlineKeyboardButton(text='🔗 Add/Edit Nagad Gateway', callback_data='x:gw:Nagad')],
      [InlineKeyboardButton(text='🗑 Remove bKash Gateway', callback_data='x:rm:bKash'), InlineKeyboardButton(text='🗑 Remove Nagad Gateway', callback_data='x:rm:Nagad')],
      [InlineKeyboardButton(text='⬅️ Back', callback_data='x:open')]])
    await call.message.edit_text('💳 **PAYMENT CONTROLS**\n━━━━━━━━━━━━━━━━━━\nবিকাশ/নগদের Payment Gateway link এখান থেকেই Add/Edit/Remove করা যাবে।', parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == 'x:allw')
async def x_allw(call: CallbackQuery):
    if not admin_ok(call.from_user.id): 
        return await call.answer('Admin only', show_alert=True)
    keys = ['wth_bkash_enabled', 'wth_nagad_enabled', 'wth_rocket_enabled', 'wth_upay_enabled']
    new = '0' if all(getset(k) == '1' for k in keys) else '1'
    for k in keys:
        setset(k, new)
    await x_pay(call)


@dp.callback_query(F.data.startswith('x:num:'))
async def x_num_prompt(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id): 
        return await call.answer('Admin only', show_alert=True)
    await state.update_data(method=call.data.split(':')[-1])
    await state.set_state(AdvancedAdminState.number)
    await call.message.answer('📲 **নতুন ১১ ডিজিটের নম্বর পাঠান।**', parse_mode="Markdown")
    await call.answer()


@dp.message(AdvancedAdminState.number)
async def x_num(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id): 
        return
    n = message.text.strip()
    if not re.fullmatch(r'01[3-9]\d{8}', n): 
        return await message.answer('❌ **সঠিক ১১ ডিজিটের নম্বর দিন।**', parse_mode="Markdown")
    m = (await state.get_data())['method']
    setset('bkash_number' if m == 'bKash' else 'nagad_number', n)
    await state.clear()
    await message.answer(f'✅ **{m} number updated:** `{n}`', parse_mode="Markdown", reply_markup=main_keyboard(message.from_user.id))


@dp.callback_query(F.data.startswith('x:gw:'))
async def x_gw_prompt(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id): 
        return await call.answer('Admin only', show_alert=True)
    await state.update_data(method=call.data.split(':')[-1])
    await state.set_state(AdvancedAdminState.gateway_url)
    await call.message.answer('🔗 **Payment Gateway URL পাঠান (https://...)।**', parse_mode="Markdown")
    await call.answer()


@dp.message(AdvancedAdminState.gateway_url)
async def x_gw(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id): 
        return
    url = message.text.strip()
    if not re.match(r'^https?://', url): 
        return await message.answer('❌ **Valid http/https URL দিন।**', parse_mode="Markdown")
    m = (await state.get_data())['method']
    setset('dep_bkash_gateway' if m == 'bKash' else 'dep_nagad_gateway', url)
    await state.clear()
    await message.answer(f'✅ **{m} gateway saved.**', parse_mode="Markdown", reply_markup=main_keyboard(message.from_user.id))


@dp.callback_query(F.data.startswith('x:rm:'))
async def x_rm_gw(call: CallbackQuery):
    if not admin_ok(call.from_user.id): 
        return await call.answer('Admin only', show_alert=True)
    m = call.data.split(':')[-1]
    setset('dep_bkash_gateway' if m == 'bKash' else 'dep_nagad_gateway', '')
    await call.answer('Gateway removed', show_alert=True)
    await x_pay(call)


@dp.callback_query(F.data == 'x:limits')
async def x_limits(call: CallbackQuery):
    if not admin_ok(call.from_user.id): 
        return await call.answer('Admin only', show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text=f'Min Dep {getset("min_dep")}৳', callback_data='x:v:min_dep'), InlineKeyboardButton(text=f'Max Dep {getset("max_dep")}৳', callback_data='x:v:max_dep')],
      [InlineKeyboardButton(text=f'Min Wth {getset("min_wth")}৳', callback_data='x:v:min_wth'), InlineKeyboardButton(text=f'Max Wth {getset("max_wth")}৳', callback_data='x:v:max_wth')],
      [InlineKeyboardButton(text=f'Daily Dep Limit {getset("daily_dep_limit")}', callback_data='x:v:daily_dep_limit')],
      [InlineKeyboardButton(text='⬅️ Back', callback_data='x:open')]])
    await call.message.edit_text('📈 **LIMIT & AMOUNT CONFIGURATION**', parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith('x:v:'))
async def x_value_prompt(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id): 
        return await call.answer('Admin only', show_alert=True)
    await state.update_data(key=call.data.split(':')[-1])
    await state.set_state(AdvancedAdminState.generic_value)
    await call.message.answer('✏️ **নতুন সংখ্যাটি পাঠান।**', parse_mode="Markdown")
    await call.answer()


@dp.message(AdvancedAdminState.generic_value)
async def x_value(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id): 
        return
    try:
        v = Decimal(message.text.strip())
        assert v >= 0
    except Exception:
        return await message.answer('❌ **Valid positive number দিন।**', parse_mode="Markdown")
    k = (await state.get_data())['key']
    setset(k, money(v))
    await state.clear()
    await message.answer(f'✅ **{k} = {money(v)} সেট হয়েছে।**', parse_mode="Markdown", reply_markup=main_keyboard(message.from_user.id))


@dp.callback_query(F.data == 'x:force')
async def x_force(call: CallbackQuery):
    if not admin_ok(call.from_user.id): 
        return await call.answer('Admin only', show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text=a_toggle('📣 Force Join', 'force_join_enabled'), callback_data='x:tforce')],
      [InlineKeyboardButton(text='➕ Set Channel/Group', callback_data='x:fjset'), InlineKeyboardButton(text='🗑 Remove', callback_data='x:fjrm')],
      [InlineKeyboardButton(text='⬅️ Back', callback_data='x:open')]])
    await call.message.edit_text(f'📣 **FORCE JOIN**\n**Chat:** {getset("force_join_chat") or "Not set"}\n**Link:** {getset("force_join_link") or "Not set"}', parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == 'x:tforce')
async def x_tforce(call: CallbackQuery):
    if not admin_ok(call.from_user.id): 
        return await call.answer('Admin only', show_alert=True)
    setset('force_join_enabled', '0' if getset('force_join_enabled') == '1' else '1')
    await x_force(call)


@dp.callback_query(F.data == 'x:fjset')
async def x_fjset(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdvancedAdminState.force_chat)
    await call.message.answer('📣 **Channel username বা chat ID পাঠান। যেমন @NIKAN_EARN**', parse_mode="Markdown")
    await call.answer()


@dp.message(AdvancedAdminState.force_chat)
async def x_fjchat(message: Message, state: FSMContext):
    await state.update_data(chat=message.text.strip())
    await state.set_state(AdvancedAdminState.force_link)
    await message.answer('🔗 **Join link পাঠান।**', parse_mode="Markdown")


@dp.message(AdvancedAdminState.force_link)
async def x_fjlink(message: Message, state: FSMContext):
    link = message.text.strip()
    if not re.match(r'^https?://', link): 
        return await message.answer('❌ **Valid URL দিন।**', parse_mode="Markdown")
    d = await state.get_data()
    setset('force_join_chat', d['chat'])
    setset('force_join_link', link)
    setset('force_join_enabled', '1')
    await state.clear()
    await message.answer('✅ **Force Join set ও ON হয়েছে।**', parse_mode="Markdown", reply_markup=main_keyboard(message.from_user.id))


@dp.callback_query(F.data == 'x:fjrm')
async def x_fjrm(call: CallbackQuery):
    setset('force_join_enabled', '0')
    setset('force_join_chat', '')
    setset('force_join_link', '')
    await x_force(call)


@dp.callback_query(F.data == 'x:user')
async def x_user(call: CallbackQuery):
    if not admin_ok(call.from_user.id): 
        return await call.answer('Admin only', show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text='🔎 Search User by ID', callback_data='x:usearch')],
      [InlineKeyboardButton(text='💰 Edit Balances / Referral Count', callback_data='x:usearch')],
      [InlineKeyboardButton(text='💎 Plan Add', callback_data='x:plan')],
      [InlineKeyboardButton(text='⬅️ Back', callback_data='x:open')]])
    await call.message.edit_text('👤 **USER CONTROL PANEL**\n\nUser ID দিয়ে search করে balance, referral, ban/suspend ও plan control করুন।', parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == 'x:usearch')
async def x_usearch(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdvancedAdminState.user_id)
    await call.message.answer('🆔 **User Telegram ID পাঠান।**', parse_mode="Markdown")
    await call.answer()


@dp.message(AdvancedAdminState.user_id)
async def x_userid(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id): 
        return
    try:
        uid = int(message.text.strip())
    except Exception: 
        return await message.answer('❌ **Numeric User ID দিন।**', parse_mode="Markdown")

    # ✅ FIX: আগে ভুল column index থেকে Task/Referrals/Ban/Suspend দেখানো হচ্ছিল।
    # এখন নাম ধরে নির্দিষ্ট column select করা হয়েছে, তাই সব তথ্য সঠিক দেখাবে।
    con = db()
    r = con.execute("""
        SELECT user_id, name, username, main_balance, deposit_balance,
               bonus_balance, referral_balance, task_balance,
               referral_count, banned, suspended
        FROM users WHERE user_id=?
    """, (uid,)).fetchone()
    con.close()

    if not r: 
        await state.clear()
        return await message.answer('❌ **User পাওয়া যায়নি।**', parse_mode="Markdown", reply_markup=main_keyboard(message.from_user.id))
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text='🚫 Ban', callback_data=f'x:ban:{uid}:1'), InlineKeyboardButton(text='✅ Unban', callback_data=f'x:ban:{uid}:0')],
      [InlineKeyboardButton(text='⛔ Suspend', callback_data=f'x:sus:{uid}:1'), InlineKeyboardButton(text='🟢 Unsuspend', callback_data=f'x:sus:{uid}:0')],
      [InlineKeyboardButton(text='💰 Deposit Balance', callback_data=f'x:edit:{uid}:deposit_balance'), InlineKeyboardButton(text='🫂 Referral Balance', callback_data=f'x:edit:{uid}:referral_balance')],
      [InlineKeyboardButton(text='🎁 Bonus Balance', callback_data=f'x:edit:{uid}:bonus_balance'), InlineKeyboardButton(text='📝 Task Balance', callback_data=f'x:edit:{uid}:task_balance')],
      [InlineKeyboardButton(text='💵 Main Balance', callback_data=f'x:edit:{uid}:main_balance'), InlineKeyboardButton(text='👥 Referral Count', callback_data=f'x:edit:{uid}:referral_count')],
      [InlineKeyboardButton(text='🎁 Bonus → Main', callback_data=f'x:bmain:{uid}')],
    ])
    await message.answer(f'👤 **USER**\n━━━━━━━━━━━━━━━━━━\n👤 **{r[1]}**\n🔗 **@{r[2] or "None"}**\n🆔 **{r[0]}**\n💵 **Main:** {money(r[3])}৳\n📥 **Deposit:** {money(r[4])}৳\n🫂 **Referral:** {money(r[6])}৳\n🎁 **Bonus:** {money(r[5])}৳\n📝 **Task:** {money(r[7])}৳\n👥 **Referrals:** {r[8]}\n🚫 **Ban:** {"YES" if r[9] else "NO"}\n⛔ **Suspend:** {"YES" if r[10] else "NO"}', parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data.startswith('x:ban:'))
async def x_ban(call: CallbackQuery):
    _, _, uid, val = call.data.split(':')
    uid = int(uid)
    val = int(val)
    if uid == OWNER_ID:
        return await call.answer('Owner cannot be banned.', show_alert=True)
    con = db()
    con.execute('UPDATE users SET banned=? WHERE user_id=?', (val, uid))
    con.commit()
    con.close()
    await call.answer('Updated')
    await call.message.answer(f'✅ **Ban status:** {"ON" if val else "OFF"}', parse_mode="Markdown")


@dp.callback_query(F.data.startswith('x:sus:'))
async def x_sus(call: CallbackQuery):
    _, _, uid, val = call.data.split(':')
    uid = int(uid)
    val = int(val)
    if uid == OWNER_ID:
        return await call.answer('Owner cannot be suspended.', show_alert=True)
    con = db()
    con.execute('UPDATE users SET suspended=? WHERE user_id=?', (val, uid))
    con.commit()
    con.close()
    await call.answer('Updated')
    await call.message.answer(f'✅ **Suspend status:** {"ON" if val else "OFF"}', parse_mode="Markdown")


@dp.callback_query(F.data.startswith('x:edit:'))
async def x_edit_prompt(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id):
        return await call.answer('Admin only', show_alert=True)
    _, _, uid, field = call.data.split(':')
    await state.update_data(uid=int(uid), field=field)
    await state.set_state(AdvancedAdminState.user_value)
    await call.message.answer(f'✏️ **{field}**\nনতুন absolute value পাঠান।', parse_mode="Markdown")
    await call.answer()


@dp.message(AdvancedAdminState.user_value)
async def x_edit_value(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id):
        return
    d = await state.get_data()
    field = d['field']
    uid = d['uid']
    try:
        v = Decimal(message.text.strip())
        assert v >= 0
    except Exception:
        return await message.answer('❌ **Valid positive number দিন।**', parse_mode="Markdown")
    allowed = {'main_balance', 'deposit_balance', 'referral_balance', 'bonus_balance', 'task_balance', 'referral_count'}
    if field not in allowed:
        return
    con = db()
    con.execute(f'UPDATE users SET {field}=? WHERE user_id=?', (float(v), uid))
    con.commit()
    con.close()
    await state.clear()
    await message.answer(f'✅ **User {uid}: {field} = {money(v)}**', parse_mode="Markdown", reply_markup=main_keyboard(message.from_user.id))


@dp.callback_query(F.data.startswith('x:bmain:'))
async def x_bmain_prompt(call: CallbackQuery, state: FSMContext):
    uid = int(call.data.split(':')[-1])
    await state.update_data(uid=uid)
    await state.set_state(AdvancedAdminState.user_value)
    await call.message.answer('🎁 **Bonus Balance থেকে কত টাকা Main Balance-এ transfer করবেন?**', parse_mode="Markdown")
    await call.answer()


@dp.callback_query(F.data == 'x:plan')
async def x_plan(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdvancedAdminState.plan_uid)
    await call.message.answer('🆔 **User ID পাঠান।**', parse_mode="Markdown")
    await call.answer()


@dp.message(AdvancedAdminState.plan_uid)
async def x_plan_uid(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
    except Exception:
        return await message.answer('❌ **Numeric ID দিন।**', parse_mode="Markdown")
    if not user_row(uid):
        return await message.answer('❌ **User not found.**', parse_mode="Markdown")
    await state.update_data(uid=uid)
    await state.set_state(AdvancedAdminState.plan_name)
    names = list(PLANS)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=p, callback_data=f'x:padd:{uid}:{p}') for p in names[i:i+3]] for i in range(0, len(names), 3)])
    await message.answer('💎 **Plan নির্বাচন করুন।**', parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data.startswith('x:padd:'))
async def x_plan_add(call: CallbackQuery, state: FSMContext):
    _, _, uid, p = call.data.split(':')
    uid = int(uid)
    con = db()
    cur = con.cursor()
    cur.execute('INSERT INTO plans(user_id,plan,amount,activated_at,expires_at,active) VALUES(?,?,?,?,?,1)', (uid, p, PLANS[p], now_iso(), (datetime.now(timezone.utc) + timedelta(days=4)).isoformat()))
    con.commit()
    con.close()
    await state.clear()
    await call.message.answer(f'✅ **{p} added to {uid}.**', parse_mode="Markdown")
    await call.answer('Added')


@dp.callback_query(F.data == 'x:ubroadcast')
async def x_ubroadcast(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdvancedAdminState.user_broadcast_id)
    await call.message.answer('🆔 **User ID পাঠান।**', parse_mode="Markdown")
    await call.answer()


@dp.message(AdvancedAdminState.user_broadcast_id)
async def x_ubid(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
    except Exception:
        return await message.answer('❌ **Numeric ID দিন।**', parse_mode="Markdown")
    if not user_row(uid):
        return await message.answer('❌ **User not found.**', parse_mode="Markdown")
    await state.update_data(uid=uid)
    await state.set_state(AdvancedAdminState.user_broadcast_text)
    await message.answer('✉️ **Message লিখুন।**', parse_mode="Markdown")


@dp.message(AdvancedAdminState.user_broadcast_text)
async def x_ubtext(message: Message, state: FSMContext):
    d = await state.get_data()
    uid = d['uid']
    try:
        await bot.send_message(uid, message.text or '')
        out = '✅ **Message পাঠানো হয়েছে।**'
    except Exception as e:
        out = f'❌ **পাঠানো যায়নি:** {type(e).__name__}'
    await state.clear()
    await message.answer(out, parse_mode="Markdown", reply_markup=main_keyboard(message.from_user.id))


@dp.callback_query(F.data == 'x:broadcast')
async def x_broadcast(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdvancedAdminState.broadcast)
    await call.message.answer('📢 **Broadcast message লিখুন। তারপর Confirm/Cancel দেখানো হবে।**', parse_mode="Markdown")
    await call.answer()


@dp.message(AdvancedAdminState.broadcast)
async def x_bc_preview(message: Message, state: FSMContext):
    await state.update_data(text=message.text or '')
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='✅ Confirm', callback_data='x:bcok'), InlineKeyboardButton(text='❌ Cancel', callback_data='x:bccancel')]])
    await message.answer('📢 **BROADCAST PREVIEW**\n━━━━━━━━━━━━━━━━━━\n' + (message.text or '') + '\n━━━━━━━━━━━━━━━━━━\nসকল user-কে পাঠাবেন?', parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data == 'x:bccancel')
async def x_bccancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text('❌ **Broadcast cancelled.**', parse_mode="Markdown")
    await call.answer()


@dp.callback_query(F.data == 'x:bcok')
async def x_bcok(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id):
        return await call.answer('Admin only', show_alert=True)
    textmsg = (await state.get_data()).get('text', '')
    await state.clear()
    con = db()
    ids = [r[0] for r in con.execute('SELECT user_id FROM users WHERE banned=0 AND suspended=0')]
    con.close()
    sent = fail = 0
    for uid in ids:
        try:
            await bot.send_message(uid, textmsg)
            sent += 1
        except:
            fail += 1
        await asyncio.sleep(.04)
    await call.message.edit_text(f'📢 **Broadcast finished.**\n✅ **Sent:** {sent}\n❌ **Failed:** {fail}', parse_mode="Markdown")
    await call.answer()


@dp.callback_query(F.data == 'x:deps')
async def x_deps(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer('Admin only', show_alert=True)
    con = db()
    rows = con.execute("SELECT id,user_id,method,amount,txid,order_no,status FROM deposits WHERE status IN ('Pending','Processing') ORDER BY id DESC LIMIT 10").fetchall()
    con.close()
    if not rows:
        return await call.message.answer('📥 **No pending deposits.**', parse_mode="Markdown")
    for did, uid, m, a, t, o, s in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⚙️ Processing', callback_data=f'x:dproc:{did}')], [InlineKeyboardButton(text='✅ Approve', callback_data=f'x:dok:{o}'), InlineKeyboardButton(text='❌ Reject', callback_data=f'x:dno:{o}')]])
        await call.message.answer(f'📥 **#{did}**\n👤 **{uid}**\n💳 **{m}**\n💰 **{money(a)}৳**\n📝 `{t}`\n🆔 `{o}`\n📌 **{s}**', parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith('x:dproc:'))
async def x_dproc(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return
    did = int(call.data.split(':')[-1])
    con = db()
    con.execute("UPDATE deposits SET status='Processing',updated_at=? WHERE id=?", (now_iso(), did))
    con.commit()
    con.close()
    await call.answer('Processing')


@dp.callback_query(F.data.startswith('x:dok:'))
async def x_dok(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer('Admin only', show_alert=True)
    oid = call.data.split(':')[-1]
    con = db()
    cur = con.cursor()
    r = cur.execute('SELECT id,user_id,method,amount,txid,status FROM deposits WHERE order_no=?', (oid,)).fetchone()
    if not r:
        con.close()
        return await call.answer('Not found', show_alert=True)
    did, uid, m, a, t, s = r
    if s == 'Approved':
        con.close()
        return await call.answer('Already approved', show_alert=True)
    cur.execute("UPDATE deposits SET status='Approved',reason='Approved by admin',updated_at=? WHERE id=?", (now_iso(), did))
    cur.execute('UPDATE users SET main_balance=main_balance+?,deposit_balance=deposit_balance+? WHERE user_id=?', (a, a, uid))
    con.commit()
    con.close()
    await bot.send_message(uid, f'🎉 **Deposit Successful!**\nআপনার {m} Deposit সফলভাবে সম্পন্ন হয়েছে। ✅\n━━━━━━━━━━━━━━━━━━\n💰 **Deposit Amount:** {money(a)} BDT\n📝 **Transaction ID:** `{t}`\n🆔 **Order Number:** `{oid}`\n━━━━━━━━━━━━━━━━━━\n💳 আপনার মূল ডিপোজিট ব্যালেন্সে **{money(a)} BDT** যোগ করা হয়েছে।\nধন্যবাদ। ❤️\n\nℹ️ Admin reason: Approved by admin', parse_mode="Markdown")
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer('Approved')


@dp.callback_query(F.data.startswith('x:dno:'))
async def x_dno(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id):
        return await call.answer('Admin only', show_alert=True)
    oid = call.data.split(':')[-1]
    await state.update_data(kind='deposit', rid=oid)
    await state.set_state(AdvancedAdminState.reject_reason)
    await call.message.answer('❌ **Reject Reason লিখুন।**', parse_mode="Markdown")
    await call.answer()


@dp.callback_query(F.data == 'x:wds')
async def x_wds(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer('Admin only', show_alert=True)
    con = db()
    rows = con.execute("SELECT id,user_id,method,account,amount,status FROM withdrawals WHERE status IN ('Pending','Processing') ORDER BY id DESC LIMIT 10").fetchall()
    con.close()
    if not rows:
        return await call.message.answer('📤 **No pending withdrawals.**', parse_mode="Markdown")
    for wid, uid, m, acc, a, s in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='⚙️ Processing', callback_data=f'x:wproc:{wid}')], [InlineKeyboardButton(text='✅ Approve', callback_data=f'x:wok:{wid}'), InlineKeyboardButton(text='❌ Reject', callback_data=f'x:wno:{wid}')]])
        await call.message.answer(f'📤 **#{wid}**\n👤 **{uid}**\n💳 **{m}**\n📲 `{acc}`\n💰 **{money(a)}৳**\n📌 **{s}**', parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data.startswith('x:wproc:'))
async def x_wproc(call: CallbackQuery):
    wid = int(call.data.split(':')[-1])
    con = db()
    con.execute("UPDATE withdrawals SET status='Processing',updated_at=? WHERE id=?", (now_iso(), wid))
    con.commit()
    con.close()
    await call.answer('Processing')


@dp.callback_query(F.data.startswith('x:wok:'))
async def x_wok(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer('Admin only', show_alert=True)
    wid = int(call.data.split(':')[-1])
    con = db()
    r = con.execute('SELECT user_id,method,account,amount,status FROM withdrawals WHERE id=?', (wid,)).fetchone()
    if not r:
        con.close()
        return await call.answer('Not found', show_alert=True)
    uid, m, acc, a, s = r
    if s == 'Approved':
        con.close()
        return await call.answer('Already approved', show_alert=True)
    con.execute("UPDATE withdrawals SET status='Approved',reason='Approved by admin',updated_at=? WHERE id=?", (now_iso(), wid))
    con.commit()
    con.close()
    await bot.send_message(uid, f'🎊 **উইথড্র কনফার্মড!**\n💰 **পরিমাণ:** {money(a)}৳\n🟢 আপনার পেমেন্ট রিকোয়েস্ট অনুমোদিত হয়েছে。\n📲 **{m}:** `{acc}`\n\nℹ️ Admin reason: Approved by admin\nℹ️ DEMO mode-এ কোনো বাস্তব পেমেন্ট পাঠানো হয় না。', parse_mode="Markdown")
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer('Approved')


@dp.callback_query(F.data.startswith('x:wno:'))
async def x_wno(call: CallbackQuery, state: FSMContext):
    if not admin_ok(call.from_user.id):
        return await call.answer('Admin only', show_alert=True)
    wid = int(call.data.split(':')[-1])
    await state.update_data(kind='withdraw', rid=wid)
    await state.set_state(AdvancedAdminState.reject_reason)
    await call.message.answer('❌ **Withdraw Reject Reason লিখুন।**', parse_mode="Markdown")
    await call.answer()


@dp.message(AdvancedAdminState.reject_reason)
async def x_reject_reason(message: Message, state: FSMContext):
    if not admin_ok(message.from_user.id):
        return
    d = await state.get_data()
    kind, rid = d['kind'], d['rid']
    reason = message.text.strip()
    con = db()
    cur = con.cursor()
    if kind == 'deposit':
        r = cur.execute('SELECT user_id,amount,txid,method,status FROM deposits WHERE order_no=?', (rid,)).fetchone()
        if not r:
            con.close()
            await state.clear()
            return await message.answer('❌ **Request not found.**', parse_mode="Markdown")
        uid, a, t, m, s = r
        cur.execute("UPDATE deposits SET status='Rejected',reason=?,updated_at=? WHERE order_no=?", (reason, now_iso(), rid))
        await bot.send_message(uid, f'❌ **Deposit Failed!**\nআপনার দেওয়া Transaction ID সঠিক নয় অথবা এই Transaction ID-এর মাধ্যমে কোনো পেমেন্ট শনাক্ত করা যায়নি。\n📝 **Transaction ID:** `{t}`\n🆔 **Order No:** `{rid}`\n\n❗ **Reject Reason:** {reason}\n\n🔄 **অনুগ্রহ করে সঠিক Transaction ID দিয়ে আবার চেষ্টা করুন।**', parse_mode="Markdown")
    else:
        r = cur.execute('SELECT user_id,amount,method,account,status FROM withdrawals WHERE id=?', (int(rid),)).fetchone()
        if not r:
            con.close()
            await state.clear()
            return await message.answer('❌ **Request not found.**', parse_mode="Markdown")
        uid, a, m, acc, s = r
        if s != 'Rejected':
            cur.execute("UPDATE withdrawals SET status='Rejected',reason=?,updated_at=? WHERE id=?", (reason, now_iso(), int(rid)))
            cur.execute('UPDATE users SET main_balance=main_balance+? WHERE user_id=?', (a, uid))
        await bot.send_message(uid, f'🚫 **WITHDRAW CANCELLED**\n💰 **Amount:** {money(a)}৳\nআপনার উইথড্র রিকোয়েস্টটি বাতিল করা হয়েছে。\n↩️ **{money(a)}৳** আপনার অ্যাকাউন্ট ব্যালেন্সে পুনরায় যোগ হয়েছে。\n\n❗ **Reject Reason:** {reason}', parse_mode="Markdown")
    con.commit()
    con.close()
    await state.clear()
    await message.answer('✅ **Status updated এবং user notification পাঠানো হয়েছে।**', parse_mode="Markdown", reply_markup=main_keyboard(message.from_user.id))


@dp.callback_query(F.data == 'x:admins')
async def x_admins(call: CallbackQuery):
    if not super_ok(call.from_user.id):
        await call.message.answer('শুধুমাত্র সুপার এডমিন এটি দেখতে পারবে!')
        return await call.answer()
    con = db()
    rows = con.execute('SELECT user_id,role FROM admins ORDER BY user_id').fetchall()
    con.close()
    text = '👑 **ADMIN MANAGEMENT**\n━━━━━━━━━━━━━━━━━━\n' + ('\n'.join(f'🆔 `{u}` — {r}' for u, r in rows) or 'None')
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='➕ Add Admin', callback_data='x:addadmin'), InlineKeyboardButton(text='➖ Remove Admin', callback_data='x:rmadmin')], [InlineKeyboardButton(text='⬅️ Back', callback_data='x:open')]])
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await call.answer()


@dp.callback_query(F.data == 'x:addadmin')
async def x_addadmin(call: CallbackQuery, state: FSMContext):
    if not super_ok(call.from_user.id):
        return await call.message.answer('শুধুমাত্র সুপার এডমিন এটি দেখতে পারবে!')
    await state.set_state(AdvancedAdminState.add_admin)
    await call.message.answer('🆔 **নতুন Admin Telegram ID পাঠান।**', parse_mode="Markdown")
    await call.answer()


@dp.message(AdvancedAdminState.add_admin)
async def x_addadmin_msg(message: Message, state: FSMContext):
    if not super_ok(message.from_user.id):
        return
    try:
        uid = int(message.text.strip())
    except Exception:
        return await message.answer('❌ **Numeric ID দিন।**', parse_mode="Markdown")
    if uid == OWNER_ID:
        return await message.answer('ℹ️ 2037461288 Main Owner।')
    con = db()
    con.execute('INSERT OR REPLACE INTO admins(user_id,role,added_at) VALUES(?,?,?)', (uid, 'admin', now_iso()))
    con.commit()
    con.close()
    await state.clear()
    await message.answer(f'✅ **Admin {uid} added.**', parse_mode="Markdown", reply_markup=main_keyboard(message.from_user.id))


@dp.callback_query(F.data == 'x:rmadmin')
async def x_rmadmin(call: CallbackQuery, state: FSMContext):
    if not super_ok(call.from_user.id):
        return await call.message.answer('শুধুমাত্র সুপার এডমিন এটি দেখতে পারবে!')
    await state.set_state(AdvancedAdminState.remove_admin)
    await call.message.answer('🆔 **যে Admin remove করবেন তার ID পাঠান।**', parse_mode="Markdown")
    await call.answer()


@dp.message(AdvancedAdminState.remove_admin)
async def x_rmadmin_msg(message: Message, state: FSMContext):
    if not super_ok(message.from_user.id):
        return
    try:
        uid = int(message.text.strip())
    except Exception:
        return await message.answer('❌ **Numeric ID দিন।**', parse_mode="Markdown")
    if uid == OWNER_ID:
        return await message.answer('❌ Main Owner 2037461288 remove করা যাবে না।')
    con = db()
    con.execute('DELETE FROM admins WHERE user_id=?', (uid,))
    con.commit()
    con.close()
    await state.clear()
    await message.answer(f'✅ **Admin {uid} removed.**', parse_mode="Markdown", reply_markup=main_keyboard(message.from_user.id))


@dp.callback_query(F.data == 'x:open')
async def x_open(call: CallbackQuery):
    if not admin_ok(call.from_user.id):
        return await call.answer('Admin only', show_alert=True)
    await call.message.edit_text('🔐 **ADMIN CONTROL PANEL**\n━━━━━━━━━━━━━━━━━━\nসম্পূর্ণ dynamic control interface', parse_mode="Markdown", reply_markup=admin_kb(call.from_user.id))
    await call.answer()


@dp.callback_query(F.data == 'x:close')
async def x_close(call: CallbackQuery):
    await call.message.answer('🏠 **Main Menu**', parse_mode="Markdown", reply_markup=main_keyboard(call.from_user.id))
    await call.answer()


# =========================
# ✅ FIX: GLOBAL ERROR HANDLER
# =========================
# কোনো handler-এ unexpected error হলে আগে চুপচাপ fail করত।
# এখন error console-এ log হয় + Admin (আপনি) নোটিফিকেশন পান।
_last_error_sent = 0.0


@dp.errors()
async def on_error(event: ErrorEvent):
    global _last_error_sent
    logging.error("Unhandled exception: %s", event.exception, exc_info=event.exception)
    now_ts = time.time()
    if now_ts - _last_error_sent >= 15:  # spam ঠেকাতে ১৫ সেকেন্ড throttle
        _last_error_sent = now_ts
        try:
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ Bot Error!\n{type(event.exception).__name__}: {event.exception}"
            )
        except Exception:
            pass


# =========================
# UNKNOWN TEXT
# =========================
@dp.message()
async def fallback(message: Message):
    await message.answer(
        "🏠 **অনুগ্রহ করে নিচের Reply Keyboard থেকে একটি অপশন নির্বাচন করুন।**",
        parse_mode="Markdown",
        reply_markup=main_keyboard(message.from_user.id)
    )


# =========================
# RUN
# =========================
async def main():
    # ✅ FIX: একই মেশিনে দ্বিতীয় instance চালু হলে সেটি সাথে সাথে বন্ধ হয়ে যাবে
    acquire_single_instance_lock()

    logging.basicConfig(level=logging.INFO)
    init_db()

    # ✅ FIX: পুরোনো webhook / জমে থাকা pending update পরিষ্কার করা হয়,
    # যাতে restart-এর পর পুরোনো মেসেজে বারবার (ডুপ্লিকেট) রিপ্লাই না যায়।
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"delete_webhook warning: {e}")

    print("NIKAN EARN bot started...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
