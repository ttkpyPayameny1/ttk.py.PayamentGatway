import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

# কনফিগারেশন
API_TOKEN = "8631873007:AAEVtP7swVa82bIl8Mr_seyzi1MdFwQzvM4"  # আপনার বটের টেলিগ্রাম টোকেন দিন
OWNER_ID = 2037461288  # সুপার এডমিন আইডি

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ----------------- Database Setup -----------------
conn = sqlite3.connect("nikan_earn.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute(
    """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    main_balance REAL DEFAULT 0.0,
    deposit_balance REAL DEFAULT 0.0,
    bonus_balance REAL DEFAULT 0.0,
    ref_balance REAL DEFAULT 0.0,
    is_banned INTEGER DEFAULT 0
)
"""
)

cursor.execute(
    """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
"""
)
conn.commit()


# ডিফল্ট সেটিংস সেট করা
def init_settings():
  defaults = {
      "bot_status": "ON",
      "fund_system": "ON",
      "withdraw_system": "ON",
      "bkash": "ON",
      "nagad": "ON",
      "rocket": "OFF",
      "upay": "OFF",
      "usdt": "ON",
  }
  for k, v in defaults.items():
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
    )
  conn.commit()


init_settings()


def get_setting(key):
  cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
  row = cursor.fetchone()
  return row[0] if row else "ON"


# ----------------- FSM States -----------------
class DepositState(StatesGroup):
  waiting_for_amount = State()
  waiting_for_trx_id = State()


class WithdrawState(StatesGroup):
  waiting_for_number = State()
  waiting_for_amount = State()


class BroadcastState(StatesGroup):
  waiting_for_message = State()


# ----------------- Keyboards -----------------
def main_menu_kb(is_admin=False):
  kb = [
      [
          InlineKeyboardButton(
              text="📥 Deposit (ডিপোজিট)", callback_data="menu_deposit"
          ),
          InlineKeyboardButton(
              text="💸 Withdraw (উইথড্র)", callback_data="menu_withdraw"
          ),
      ],
      [
          InlineKeyboardButton(
              text="📊 My Account (আমার অ্যাকাউন্ট)",
              callback_data="menu_account",
          ),
          InlineKeyboardButton(text="💎 VIP Plans", callback_data="menu_plans"),
      ],
      [
          InlineKeyboardButton(
              text="👥 Referral", callback_data="menu_referral"
          ),
          InlineKeyboardButton(
              text="📊 Daily Earnings", callback_data="menu_daily"
          ),
      ],
      [
          InlineKeyboardButton(
              text="🎁 Bonus Center", callback_data="menu_bonus"
          ),
          InlineKeyboardButton(
              text="🧾 Transactions", callback_data="menu_tx"
          ),
      ],
      [
          InlineKeyboardButton(
              text="🆘 Help & Support", callback_data="menu_support"
          ),
      ],
  ]
  if is_admin:
    kb.append(
        [
            InlineKeyboardButton(
                text="⚙️ Admin Control Panel", callback_data="admin_panel"
            )
        ]
    )
  return InlineKeyboardMarkup(inline_keyboard=kb)


# ----------------- Handlers: Start -----------------
@router.message(Command("start"))
async def cmd_start(message: Message):
  user_id = message.from_user.id
  username = message.from_user.username
  full_name = message.from_user.full_name

  # বটের স্ট্যাটাস চেক
  if (
      get_setting("bot_status") == "OFF"
      and user_id != OWNER_ID
  ):
    await message.answer(
        "⚠️ বট বর্তমানে রক্ষণাবেক্ষণ (Maintenance) মোডে রয়েছে। দয়া করে পরে চেষ্টা"
        " করুন।"
    )
    return

  # ইউজার ডাটাবেজে সংরক্ষণ
  cursor.execute(
      "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?,"
      " ?)",
      (user_id, username, full_name),
  )
  conn.commit()

  is_admin = user_id == OWNER_ID
  await message.answer(
      f"স্বাগতম, **{full_name}** Nikan Earn Bot-এ! 🎉\nদয়া করে নিচের মেনু"
      " থেকে আপনার অপশন বেছে নিন:",
      reply_markup=main_menu_kb(is_admin),
      parse_mode="Markdown",
  )


# ----------------- Admin Panel Logic -----------------
@router.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: CallbackQuery):
  if callback.from_user.id != OWNER_ID:
    await callback.answer(
        "⚠️ এই প্যানেলটি শুধুমাত্র এডমিনের জন্য!", show_alert=True
    )
    return

  b_status = get_setting("bot_status")
  f_status = get_setting("fund_system")
  w_status = get_setting("withdraw_system")

  kb = [
      [
          InlineKeyboardButton(
              text=f"Bot Status: {b_status}", callback_data="toggle_bot"
          )
      ],
      [
          InlineKeyboardButton(
              text=f"Deposit System: {f_status}", callback_data="toggle_fund"
          ),
          InlineKeyboardButton(
              text=f"Withdraw System: {w_status}", callback_data="toggle_withdraw"
          ),
      ],
      [
          InlineKeyboardButton(
              text="💳 Gateway Toggles", callback_data="admin_gateways"
          ),
          InlineKeyboardButton(
              text="📊 Statistics", callback_data="admin_stats"
          ),
      ],
      [
          InlineKeyboardButton(
              text="📢 Broadcast Message", callback_data="admin_broadcast"
          )
      ],
      [InlineKeyboardButton(text="🔙 Main Menu", callback_data="back_to_main")],
  ]
  await callback.message.edit_text(
      "⚙️ **Admin Control Panel**\nবটের সকল সিস্টেম এখান থেকে নিয়ন্ত্রণ করুন:",
      reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
      parse_mode="Markdown",
  )


@router.callback_query(F.data.startswith("toggle_"))
async def toggle_settings(callback: CallbackQuery):
  if callback.from_user.id != OWNER_ID:
    return

  key_map = {
      "toggle_bot": "bot_status",
      "toggle_fund": "fund_system",
      "toggle_withdraw": "withdraw_system",
  }
  action = callback.data
  if action in key_map:
    db_key = key_map[action]
    current = get_setting(db_key)
    new_val = "OFF" if current == "ON" else "ON"
    cursor.execute(
        "UPDATE settings SET value=? WHERE key=?", (new_val, db_key)
    )
    conn.commit()
    await admin_panel_handler(callback)


# ----------------- Deposit Flow -----------------
@router.callback_query(F.data == "menu_deposit")
async def deposit_menu(callback: CallbackQuery):
  if get_setting("fund_system") == "OFF":
    await callback.answer(
        "⚠️ ডিপোজিট সিস্টেম বর্তমানে বন্ধ রয়েছে।", show_alert=True
    )
    return

  kb = [
      [
          InlineKeyboardButton(
              text="💳 বিকাশ (bKash)", callback_data="dep_bkash"
          ),
          InlineKeyboardButton(text="💠 নগদ (Nagad)", callback_data="dep_nagad"),
      ],
      [
          InlineKeyboardButton(text="🚀 রকেট (Rocket)", callback_data="dep_rocket"),
          InlineKeyboardButton(text="🟣 উপায় (Upay)", callback_data="dep_upay"),
      ],
      [InlineKeyboardButton(text="🟡 Binance (USDT)", callback_data="dep_usdt")],
      [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main")],
  ]
  text = (
      "🔐 **ফান্ড ডিপোজিট**\n━━━━━━━━━━━━━━━━━━\n📲 নিচের অপশন থেকে একটি মেথড"
      " নির্বাচন করুন।👇"
  )
  await callback.message.edit_text(
      text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown"
  )


@router.callback_query(F.data.in_({"dep_rocket", "dep_upay"}))
async def temporary_closed_gateway(callback: CallbackQuery):
  method_name = "রকেট" if "rocket" in callback.data else "উপায়"
  text = (
      f"⚠️ **পেমেন্ট মেথড সাময়িকভাবে বন্ধ**\nদুঃখিত! {method_name} পেমেন্ট"
      " বর্তমানে সাময়িকভাবে বন্ধ রয়েছে。\n\nএই মেথডের মাধ্যমে এই মুহূর্তে কোনো"
      " ডিপোজিট করা যাবে না।\n🔄 অনুগ্রহ করে অন্য কোনো সক্রিয় পেমেন্ট মেথড"
      " নির্বাচন করুন।"
  )
  await callback.answer(text, show_alert=True)


@router.callback_query(F.data.in_({"dep_bkash", "dep_nagad"}))
async def bkash_nagad_deposit(callback: CallbackQuery, state: FSMContext):
  method = "বিকাশ" if "bkash" in callback.data else "নগদ"
  await state.update_data(method=method)
  await state.set_state(DepositState.waiting_for_amount)

  kb = [[InlineKeyboardButton(text="বাতিল ❌", callback_data="back_to_main")]]
  text = (
      f"💳 আপনি **{method}** সিলেক্ট করেছেন।\nডিপোজিট লিমিট রয়েছে: 0/3\n\nআপনি কত"
      " টাকা ডিপোজিট করতে চান?\nনিম্নলিখিত সীমা: সর্বনিম্ন ৫০ সর্বোচ্চ"
      " ১০০০০\nঅনুগ্রহ করে টাকার পরিমাণ লিখুন:"
  )
  await callback.message.edit_text(
      text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown"
  )


@router.message(DepositState.waiting_for_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
  try:
    amount = float(message.text)
    if amount < 50 or amount > 10000:
      await message.answer(
          "⚠️ ডিপোজিট সীমা ৫০ থেকে ১০,০০০ টাকার মধ্যে হতে হবে। পুনরায় সঠিক"
          " পরিমাণ লিখুন:"
      )
      return

    await state.update_data(amount=amount)
    await state.set_state(DepositState.waiting_for_trx_id)

    kb = [[InlineKeyboardButton(text="বাতিল ❌", callback_data="back_to_main")]]
    await message.answer(
        f"আপনার অ্যামাউন্ট: ৳{amount}।\nদয়া করে আপনার পেমেন্ট সম্পন্ন করে ট্রানজেকশন"
        " আইডি (TrxID) দিন:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
    )
  except ValueError:
    await message.answer("⚠️ অনুগ্রহ করে সঠিক সংখ্যায় টাকার পরিমাণ লিখুন:")


# ----------------- General Back to Main -----------------
@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
  is_admin = callback.from_user.id == OWNER_ID
  await callback.message.edit_text(
      "স্বাগতম! প্রধান মেনু:",
      reply_markup=main_menu_kb(is_admin),
      parse_mode="Markdown",
  )


# ----------------- Main Execution -----------------
async def main():
  print("Bot is starting...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
