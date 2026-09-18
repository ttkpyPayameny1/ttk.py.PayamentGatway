# NIKAN EARN - Reply Keyboard Demo Bot
# Python 3.10+ / aiogram 3.x
# DEMO/SIMULATION ONLY — no real payment gateway or payout is performed.

import asyncio
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# =========================
# CONFIG
# =========================
BOT_TOKEN = "8983512458:AAGUw0goCNIUSUeJxzYSX1qKnDjz9GdzmiA"
ADMIN_ID = 2037461288

# Replace with your real gateway URL when you have a compatible provider.
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
DEMO_DAILY_RATE = Decimal("0.34")  # Requested demo calculation; not a guaranteed return.

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# =========================
# DATABASE
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


def money(x):
    return f"{Decimal(str(x)):.2f}".rstrip("0").rstrip(".")


def order_no():
    return "RC" + datetime.now().strftime("%Y%m%d%H%M%S%f")[:21]


# =========================
# REPLY KEYBOARD
# =========================
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔐 ফান্ড ডিপোজিট"), KeyboardButton(text="👤 একাউন্ট")],
            [KeyboardButton(text="💸 Withdraw"), KeyboardButton(text="👥 Referral")],
            [KeyboardButton(text="📊 Daily Earnings"), KeyboardButton(text="🎁 Bonus Center")],
            [KeyboardButton(text="💎 Available Plans"), KeyboardButton(text="🧾 Transaction History")],
            [KeyboardButton(text="🆘 Help & Support")],
        ],
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


class AdminState(StatesGroup):
    action = State()
    request_id = State()
    reason = State()


# =========================
# START / MENU
# =========================
@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    get_user(message)
    await message.answer(
        "🚀 NIKAN EARN\n\nস্বাগতম! নিচের মেনু থেকে একটি অপশন নির্বাচন করুন।",
        reply_markup=main_keyboard()
    )


@dp.message(Command("menu"))
async def menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Main Menu\nনিচের মেনু থেকে একটি অপশন নির্বাচন করুন।", reply_markup=main_keyboard())


@dp.message(Command("help"))
async def help_command(message: Message):
    await show_help(message)


@dp.message(F.text == "❌ Cancel")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ বর্তমান প্রক্রিয়াটি বাতিল করা হয়েছে।", reply_markup=main_keyboard())


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
        "🔐 ফান্ড ডিপোজিট\n━━━━━━━━━━━━━━━━━━\n"
        "নিচের অপশন থেকে একটি মেথড নির্বাচন করুন।",
        reply_markup=kb
    )


@dp.callback_query(F.data.in_(["dep_bkash", "dep_nagad"]))
async def dep_local_method(call: CallbackQuery, state: FSMContext):
    method = "bKash" if call.data == "dep_bkash" else "Nagad"
    await state.update_data(method=method)
    await state.set_state(DepositState.amount)
    await call.message.answer(
        f"💳 {method} Deposit\n\n"
        "📊 ডিপোজিট লিমিট: 0/3\n"
        "💰 সর্বনিম্ন: 50৳\n"
        "💰 সর্বোচ্চ: 10,000৳\n\n"
        "👉 কত টাকা ডিপোজিট করতে চান? সংখ্যায় লিখুন।",
        reply_markup=cancel_keyboard()
    )
    await call.answer()


@dp.message(DepositState.amount)
async def dep_local_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ সঠিক সংখ্যায় ডিপোজিট এমাউন্ট লিখুন।")
        return

    if amount < 50 or amount > 10000:
        await message.answer("⚠️ ডিপোজিটের পরিমাণ 50৳ থেকে 10,000৳ এর মধ্যে হতে হবে।")
        return

    data = await state.get_data()
    method = data["method"]

    # Gateway URL is configurable in CONFIG.
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 পেমেন্ট গেটওয়েতে যান", url=PAYMENT_GATEWAY_URL)],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_inline")]
    ])
    await message.answer(
        f"💰 ডিপোজিট এমাউন্ট: {money(amount)}৳\n\n"
        "আপনার প্রদত্ত এমাউন্টটি ডিপোজিট করতে নিচের দেওয়া লিংকে প্রবেশ করুন।\n\n"
        f"💳 Method: {method}",
        reply_markup=kb
    )
    await state.clear()


@dp.callback_query(F.data == "dep_binance")
async def dep_binance(call: CallbackQuery, state: FSMContext):
    await state.update_data(method="Binance")
    await state.set_state(DepositState.amount)
    await call.message.answer(
        "🟡 Binance — USDT Deposit\n\n"
        "💵 সর্বনিম্ন: $1\n"
        "💵 সর্বোচ্চ: $50\n\n"
        "👉 কত USDT ডিপোজিট করবেন? লিখুন।",
        reply_markup=cancel_keyboard()
    )
    await call.answer()


@dp.message(DepositState.amount)
async def dep_binance_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("method") != "Binance":
        return

    try:
        amount = Decimal(message.text.strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ সঠিক USDT পরিমাণ লিখুন।")
        return

    if amount < 1 or amount > 50:
        await message.answer("⚠️ USDT পরিমাণ $1 থেকে $50 এর মধ্যে হতে হবে।")
        return

    await state.update_data(usdt=amount)
    await state.set_state(DepositState.txid)

    bdt = amount * USDT_RATE_BDT
    await message.answer(
        "🟡 USDT — BEP20 ডিপোজিট\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💱 ডিপোজিট রেট: 1 USDT = {money(USDT_RATE_BDT)}৳\n"
        f"💰 আপনার পরিমাণ: {money(amount)} USDT\n"
        f"💵 ব্যালেন্সে যোগ হবে: {money(bdt)}৳\n\n"
        "📌 BEP20 / BSC নেটওয়ার্ক ব্যবহার করে নিচের ঠিকানায় USDT পাঠান:\n\n"
        f"`{BINANCE_DEPOSIT_ADDRESS}`\n\n"
        "📝 পেমেন্ট করার পর TxID / Transaction Hash পাঠান।",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )


@dp.message(DepositState.txid)
async def dep_binance_txid(message: Message, state: FSMContext):
    txid = message.text.strip()
    if not re.fullmatch(r"0x[a-fA-F0-9]{64}", txid):
        await message.answer(
            "❌ TxID সঠিক নয়।\n"
            "0x দিয়ে শুরু হওয়া 64-hex-character Transaction Hash পাঠান।"
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
        "✅ আপনার ডিপোজিটের অনুরোধ জমা করা হয়েছে।\n"
        "⏳ অনুমোদনের জন্য অপেক্ষা করুন।",
        reply_markup=main_keyboard()
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
        "📥 NEW DEPOSIT REQUEST\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 নাম: {user.full_name}\n"
        f"🔗 Username: {username}\n"
        f"🆔 User ID: {user.id}\n"
        f"💳 Method: {method}\n"
        f"💰 Amount: {money(amount)}৳\n"
        f"📝 TxID: {txid}\n"
        f"🆔 Order No: {oid}\n"
        f"📌 Status: Pending",
        reply_markup=kb
    )


# =========================
# ACCOUNT
# =========================
@dp.message(F.text == "👤 একাউন্ট")
async def account(message: Message):
    row = get_user(message)
    uid, name, username, main, deposit, bonus, referral, total, created = row

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT plan, expires_at FROM plans
        WHERE user_id=? AND active=1 ORDER BY expires_at
    """, (uid,))
    active = cur.fetchall()
    con.close()

    vip1 = "সক্রিয় নয়"
    vip2 = "সক্রিয় নয়"
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
        "👤 আমার অ্যাকাউন্টের তথ্য\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 ব্যবহারকারীর নাম: {name}\n"
        f"🔗 ইউজারনেম: @{username if username else 'নেই'}\n"
        f"🆔 ইউজার আইডি: {uid}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💰 BALANCE DETAILS\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 মোট ব্যালেন্স: {money(main)}৳\n"
        f"📥 ডিপোজিট ব্যালেন্স: {money(deposit)}৳\n"
        f"🎁 ডিপোজিট বোনাস: {money(bonus)}৳\n"
        f"🫂 রেফার ব্যালেন্স: {money(referral)}৳\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 ACCOUNT STATUS\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏳ Plan এর মেয়াদ:\n"
        f"• VIP 1 — {vip1}\n"
        f"• VIP 2 — {vip2}\n"
        "🚫 নিষিদ্ধ: না\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ আপনার অ্যাকাউন্টের সকল তথ্য এখানে দেখানো হয়েছে।"
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
    await message.answer("💸 Withdraw\n\nএকটি পেমেন্ট মেথড নির্বাচন করুন।", reply_markup=kb)


@dp.callback_query(F.data.in_(["wd_bkash", "wd_nagad"]))
async def wd_method(call: CallbackQuery, state: FSMContext):
    method = "bKash" if call.data == "wd_bkash" else "Nagad"
    await state.update_data(method=method)
    await state.set_state(WithdrawState.account)
    await call.message.answer(
        f"📲 {method}\n\n"
        "আপনার সঠিক ১১ ডিজিটের নম্বরটি লিখুন।\n"
        "উদাহরণ: 017XXXXXXXX",
        reply_markup=cancel_keyboard()
    )
    await call.answer()


@dp.message(WithdrawState.account)
async def wd_account(message: Message, state: FSMContext):
    account_no = message.text.strip()
    if not re.fullmatch(r"01[3-9]\d{8}", account_no):
        await message.answer("❌ সঠিক ১১ ডিজিটের মোবাইল নম্বর দিন।")
        return

    await state.update_data(account=account_no)
    await state.set_state(WithdrawState.amount)

    row = get_user(message)
    balance = Decimal(str(row[3]))

    await message.answer(
        f"💰 আপনার বর্তমান ব্যালেন্স: {money(balance)}৳\n\n"
        "📌 উইথড্র সীমা:\n"
        "• সর্বনিম্ন: 100৳\n"
        "• সর্বোচ্চ: 25,000৳\n\n"
        f"📲 নম্বর: {account_no}\n\n"
        "👉 কত টাকা উইথড্র করতে চান? সংখ্যায় লিখুন।",
        reply_markup=cancel_keyboard()
    )


@dp.message(WithdrawState.amount)
async def wd_amount(message: Message, state: FSMContext):
    try:
        amount = Decimal(message.text.strip())
    except (InvalidOperation, AttributeError):
        await message.answer("❌ সঠিক পরিমাণ লিখুন।")
        return

    row = get_user(message)
    balance = Decimal(str(row[3]))

    if amount < 100 or amount > 25000 or amount > balance:
        await message.answer(
            "⚠️ উইথড্র পরিমাণ সঠিক নয়!\n"
            "💰 উইথড্র করার সীমা:\n"
            "• সর্বনিম্ন — 100৳\n"
            "• সর্বোচ্চ — 25,000৳\n"
            f"আপনার বর্তমান ব্যালেন্স {money(balance)}৳\n\n"
            "👉 অনুগ্রহ করে সঠিক পরিমাণ লিখে আবার চেষ্টা করুন।",
            reply_markup=cancel_keyboard()
        )
        return

    data = await state.get_data()
    method = data["method"]
    account_no = data["account"]

    # Reserve main balance while pending.
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE users SET main_balance=main_balance-? WHERE user_id=? AND main_balance>=?",
                (float(amount), message.from_user.id, float(amount)))
    if cur.rowcount != 1:
        con.rollback()
        con.close()
        await message.answer("❌ ব্যালেন্স পরিবর্তিত হয়েছে। আবার চেষ্টা করুন.")
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
        f"✅ আপনার 💸 {money(amount)}৳ উইথড্র রিকোয়েস্ট সফলভাবে জমা হয়েছে!\n\n"
        "⏳ প্রসেসিং সময়: Admin review\n"
        "অনুমোদন সম্পন্ন হওয়া পর্যন্ত অপেক্ষা করুন।",
        reply_markup=main_keyboard()
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
        "📤 NEW WITHDRAW REQUEST\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 নাম: {user.full_name}\n"
        f"🔗 Username: {username}\n"
        f"🆔 User ID: {user.id}\n"
        f"💳 Method: {method}\n"
        f"📲 Account: {account_no}\n"
        f"💰 Amount: {money(amount)}৳\n"
        f"🆔 Request ID: {wid}\n"
        "📌 Status: Pending",
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
    # Referral tracking can be connected to your preferred referral source later.
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
        "👥 Referral Center\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔗 আপনার Referral Link:\n{link}\n\n"
        "👥 মোট referrals: 0\n"
        f"💰 Referral earnings: {money(refbal)}৳\n\n"
        "📌 রেফার করা ব্যক্তি ডিপোজিট করলে, প্রযোজ্য শর্ত অনুযায়ী "
        "তার ডিপোজিট থেকে ৫% কমিশন গণনা করা যেতে পারে।",
        reply_markup=kb
    )


@dp.callback_query(F.data == "ref_rules")
async def ref_rules(call: CallbackQuery):
    await call.message.answer(
        "📋 Referral Rules\n\n"
        "রেফার করা ব্যক্তি ডিপোজিট করলে তার ডিপোজিটের ৫% কমিশন "
        "সিস্টেমের নির্ধারিত নিয়ম অনুযায়ী Referral Balance-এ যোগ হতে পারে।"
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
    lines = ["📊 Daily Earnings", "━━━━━━━━━━━━━━━━━━"]

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
            f"💎 {plan} — {money(amount)}৳\n"
            f"📅 মেয়াদ শেষ: {exp.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"📊 Demo daily amount: {money(daily)}৳\n"
        )

    if not valid:
        lines.append("❌ কোনো active plan নেই।")
        await message.answer("\n".join(lines))
        return

    lines.append("🕗 Claim window: 08:00–24:00")
    lines.append("⚠️ Claim না করলে ওই দিনের amount পরের দিনে carry হবে না।")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧮 Today Earnings Claim", callback_data="claim_today")]
    ])
    await message.answer("\n".join(lines), reply_markup=kb)


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
        # Demo earnings are credited to main balance.
        cur.execute("""
            UPDATE users
            SET main_balance=main_balance+?, total_earnings=total_earnings+?
            WHERE user_id=?
        """, (float(total), float(total), uid))

    con.commit()
    con.close()

    if total == 0:
        await call.answer("⚠️ আজকের earnings ইতিমধ্যে claim করা হয়েছে বা available নেই।", show_alert=True)
        return

    await call.message.answer(
        "🎉 Today Earnings Claim Successful\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 মোট যোগ হয়েছে: {money(total)}৳\n"
        f"📦 Active plans claimed: {len(claimed)}\n\n"
        "ℹ️ এটি DEMO/SIMULATION calculation; কোনো নির্দিষ্ট লাভ নিশ্চিত নয়।"
    )
    await call.answer("✅ Claim সম্পন্ন হয়েছে।")


# =========================
# BONUS
# =========================
@dp.message(F.text == "🎁 Bonus Center")
async def bonus_center(message: Message):
    uid = message.from_user.id
    con = db()
    cur = con.cursor()
    cur.execute("SELECT bonus_balance FROM users WHERE user_id=?", (uid,))
    bal = cur.fetchone()[0]
    con.close()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Daily Free 5৳ Claim", callback_data="bonus_claim")],
        [InlineKeyboardButton(text="📜 Bonus History", callback_data="bonus_history")]
    ])
    await message.answer(
        "🎁 Bonus Center\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 Available Bonus: {money(bal)}৳\n"
        "🎁 Active Rewards: Daily Free 5৳\n\n"
        "📌 Bonus Balance সরাসরি withdraw বা plan purchase-এর জন্য ব্যবহার করা যাবে না।\n"
        "Admin নির্ধারিত শর্তে Bonus Balance Main Balance-এ convert করতে পারে।",
        reply_markup=kb
    )


@dp.callback_query(F.data == "bonus_claim")
async def bonus_claim(call: CallbackQuery):
    uid = call.from_user.id
    today = datetime.now(timezone.utc).date().isoformat()

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT 1 FROM bonuses WHERE user_id=? AND type='daily' AND date(created_at)=date('now')
    """, (uid,))
    if cur.fetchone():
        con.close()
        await call.answer("আজকের 5৳ Bonus ইতিমধ্যে নেওয়া হয়েছে।", show_alert=True)
        return

    cur.execute("UPDATE users SET bonus_balance=bonus_balance+5 WHERE user_id=?", (uid,))
    cur.execute("""
        INSERT INTO bonuses(user_id,amount,type,created_at)
        VALUES(?,?,?,?)
    """, (uid, 5, "daily", now_iso()))
    con.commit()
    con.close()

    await call.message.answer("🎁 আজকের 5৳ Bonus আপনার Bonus Balance-এ যোগ হয়েছে।")
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
        text = "📜 Bonus History\n\nকোনো bonus history পাওয়া যায়নি।"
    else:
        text = "📜 Bonus History\n━━━━━━━━━━━━━━━━━━\n"
        for amount, typ, created in rows:
            text += f"🎁 +{money(amount)}৳ — {typ}\n📅 {created[:10]}\n\n"

    await call.message.answer(text)
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
        "💎 Available Plans\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "নিচে একটি Plan নির্বাচন করুন।\n\n"
        "📅 মেয়াদ: 4 দিন\n"
        "📊 Daily calculation: 34% (DEMO/SIMULATION)\n"
        "⚠️ কোনো নির্দিষ্ট লাভ নিশ্চিত নয়।",
        reply_markup=plan_keyboard()
    )


@dp.callback_query(F.data.startswith("plan:"))
async def plan_details(call: CallbackQuery):
    plan = call.data.split(":", 1)[1]
    amount = PLANS.get(plan)
    if amount is None:
        await call.answer("Plan পাওয়া যায়নি।", show_alert=True)
        return

    daily = Decimal(str(amount)) * DEMO_DAILY_RATE
    total_demo = daily * PLAN_DAYS

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Plan Buy", callback_data=f"buy:{plan}")],
        [InlineKeyboardButton(text="⬅️ Plans", callback_data="plans_back")]
    ])

    await call.message.answer(
        f"💼 {plan} Plan Details\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 Amount: {amount}৳\n"
        f"📅 Duration: {PLAN_DAYS} days\n"
        f"📊 Demo daily amount: {money(daily)}৳\n"
        f"📈 Demo total: {money(total_demo)}৳\n\n"
        "⚠️ এটি শুধুমাত্র DEMO/SIMULATION calculation; কোনো নির্দিষ্ট লাভ নিশ্চিত নয়।",
        reply_markup=kb
    )
    await call.answer()


@dp.callback_query(F.data == "plans_back")
async def plans_back(call: CallbackQuery):
    await call.message.answer(
        "💎 Available Plans\nএকটি Plan নির্বাচন করুন।",
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
            "⚠️ Plan Limit Reached\n"
            f"দুঃখিত! আপনার {plan} Plan বর্তমানে সর্বোচ্চ ২টি সক্রিয় রয়েছে। ❌\n\n"
            "📅 এই Plan-এর যেকোনো ১টির মেয়াদ শেষ না হওয়া পর্যন্ত "
            "একই Plan আর নতুন করে সক্রিয় করতে পারবেন না।\n\n"
            "💎 তবে অন্যান্য Available Plans থেকে Plan নির্বাচন করতে পারবেন।"
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
            "❌ আপনার ডিপোজিট ও মেইন balance এ পর্যাপ্ত টাকা নেই।\n"
            "দয়া করে আগে যোগ করুন, পরে আবার চেষ্টা করুন। ধন্যবাদ। ❤️"
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
        f"🎊 অভিনন্দন! আপনার {plan} Plan সফলভাবে সক্রিয় হয়েছে। ✅\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💎 Plan: {plan}\n"
        f"💰 বিনিয়োগ: ৳{amount}\n"
        f"📅 মেয়াদ: {PLAN_DAYS} দিন\n"
        f"📊 Demo দৈনিক আয়: ৳{money(daily)}\n\n"
        "💵 Daily Earnings থেকে claim করতে পারবেন।\n"
        "⏳ Plan-এর মেয়াদ সক্রিয় হওয়ার সময় থেকে গণনা হবে।\n\n"
        "⚠️ Daily amount একটি DEMO/SIMULATION calculation; "
        "কোনো নির্দিষ্ট লাভ নিশ্চিত নয়।"
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

    text = "🧾 Transaction History\n━━━━━━━━━━━━━━━━━━\n\n"
    text += "📥 Deposit History\n"
    if deps:
        for method, amount, status, oid, created in deps:
            text += f"• {method} — {money(amount)}৳ — {status}\n  🆔 {oid}\n"
    else:
        text += "• কোনো রেকর্ড নেই\n"

    text += "\n📤 Withdraw History\n"
    if wds:
        for method, amount, status, created in wds:
            text += f"• {method} — {money(amount)}৳ — {status}\n"
    else:
        text += "• কোনো রেকর্ড নেই\n"

    text += "\n📊 Earnings History\n"
    if earns:
        for amount, claim_date, created in earns:
            text += f"• +{money(amount)}৳ — {claim_date}\n"
    else:
        text += "• কোনো রেকর্ড নেই\n"

    await message.answer(text)


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
        "🆘 Help & Support\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Account Problem\n"
        "Deposit Problem\n"
        "Withdraw Problem\n"
        "Referral Problem\n"
        "Other Issues\n\n"
        "🕐 Support Hours: Available as stated by the service.",
        reply_markup=kb
    )


@dp.message(F.text == "🆘 Help & Support")
async def help_menu(message: Message):
    await show_help(message)


@dp.callback_query(F.data == "help_rules")
async def help_rules(call: CallbackQuery):
    await call.message.answer(
        "🌐 About NIKAN\n\n"
        "NIKAN একটি online earning service demo interface, "
        "যেখানে earning features, referral program এবং available plans "
        "দেখানো হয়।\n\n"
        "📊 Track Your Earnings\n"
        "👥 Referral Program\n"
        "🧾 Transaction History\n"
        "🆘 User Support\n\n"
        "⚠️ কোনো নির্দিষ্ট লাভ নিশ্চিত নয়।"
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
        await call.answer("Request পাওয়া যায়নি।", show_alert=True)
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
        "🎉 Deposit Successful!\n\n"
        f"আপনার {money(amount)} Deposit সফলভাবে সম্পন্ন হয়েছে। ✅\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 Deposit Amount: {money(amount)} BDT\n"
        f"📝 Transaction ID: {txid}\n"
        f"🆔 Order Number: {oid}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💳 আপনার মূল ডিপোজিট ব্যালেন্সে {money(amount)} BDT যোগ করা হয়েছে।\n"
        "ধন্যবাদ। ❤️"
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
        await call.answer("Request পাওয়া যায়নি।", show_alert=True)
        return

    did, uid, amount, txid, status = row
    cur.execute("""
        UPDATE deposits SET status='Rejected',reason=?,updated_at=? WHERE id=?
    """, ("Transaction/payment could not be verified.", now_iso(), did))
    con.commit()
    con.close()

    await bot.send_message(
        uid,
        "❌ Deposit Failed!\n\n"
        "আপনার দেওয়া Transaction ID সঠিক নয় অথবা এই Transaction ID-এর মাধ্যমে কোনো পেমেন্ট শনাক্ত করা যায়নি।\n\n"
        f"📝 Transaction ID: {txid}\n"
        f"🆔 Order No: {oid}\n\n"
        "🔄 অনুগ্রহ করে সঠিক Transaction ID দিয়ে আবার চেষ্টা করুন। "
        "পেমেন্ট সম্পন্ন না করে থাকলে আগে পেমেন্ট সম্পন্ন করুন।"
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
        await call.answer("Request পাওয়া যায়নি।", show_alert=True)
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
        "🎊 উইথড্র কনফার্মড!\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 পরিমাণ: {money(amount)}৳\n"
        "🟢 আপনার পেমেন্ট রিকোয়েস্ট সফলভাবে অনুমোদিত হয়েছে।\n"
        f"📲 নির্ধারিত {method} নম্বর: {account_no}\n\n"
        "ℹ️ DEMO mode-এ কোনো বাস্তব পেমেন্ট পাঠানো হয় না।"
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
        await call.answer("Request পাওয়া যায়নি।", show_alert=True)
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
        "🚫 WITHDRAW CANCELLED\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 Amount: {money(amount)}৳\n"
        "আপনার উইথড্র রিকোয়েস্টটি বাতিল করা হয়েছে।\n"
        f"↩️ {money(amount)}৳ আপনার অ্যাকাউন্ট ব্যালেন্সে পুনরায় যোগ হয়েছে।\n\n"
        "ℹ️ কারণ: Withdrawal request rejected by admin."
    )
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("Withdraw rejected.")


# =========================
# INLINE CANCEL
# =========================
@dp.callback_query(F.data == "cancel_inline")
async def inline_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("❌ বাতিল করা হয়েছে।", reply_markup=main_keyboard())
    await call.answer()


# =========================
# UNKNOWN TEXT
# =========================
@dp.message()
async def fallback(message: Message):
    await message.answer(
        "🏠 অনুগ্রহ করে নিচের Reply Keyboard থেকে একটি অপশন নির্বাচন করুন।",
        reply_markup=main_keyboard()
    )


# =========================
# RUN
# =========================
async def main():
    init_db()
    print("NIKAN EARN bot started...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
