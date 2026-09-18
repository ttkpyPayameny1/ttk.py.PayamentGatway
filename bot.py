import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Token & Super Admin ID
TOKEN = "8631873007:AAEVtP7swVa82bIl8Mr_seyzi1MdFwQzvM4"  # আপনার বটের টোকেন এখানে বসাবেন
SUPER_ADMIN_ID = 2037461288

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

logging.basicConfig(level=logging.INFO)

# Global Bot Settings & Toggles
bot_settings = {
    "is_bot_on": True,
    "fund_system": True,
    "withdraw_system": True,
    "gateways": {
        "bkash": True,
        "nagad": True,
        "rocket": False,  # Temporarily Closed
        "upay": False,   # Temporarily Closed
        "usdt": True
    }
}

# FSM States
class DepositStates(StatesGroup):
    waiting_for_amount = State()
    waiting_usdt_hash = State()

class WithdrawStates(StatesGroup):
    waiting_number = State()
    waiting_amount = State()

# --- HELPER: MAIN MENU BUILDER (Commands always above Back button) ---
def get_main_menu(is_admin: bool = False):
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📥 Deposit", callback_data="menu_deposit"),
        types.InlineKeyboardButton(text="💸 Withdraw", callback_data="menu_withdraw")
    )
    builder.row(
        types.InlineKeyboardButton(text="📊 MY ACCOUNT", callback_data="menu_account"),
        types.InlineKeyboardButton(text="💎 Available Plans", callback_data="menu_plans")
    )
    builder.row(
        types.InlineKeyboardButton(text="👥 Referral", callback_data="menu_referral"),
        types.InlineKeyboardButton(text="📊 Daily Earnings", callback_data="menu_earnings")
    )
    builder.row(
        types.InlineKeyboardButton(text="🎁 Bonus Center", callback_data="menu_bonus"),
        types.InlineKeyboardButton(text="🧾 Transaction History", callback_data="menu_history")
    )
    builder.row(
        types.InlineKeyboardButton(text="🆘 Help & Support", callback_data="menu_support"),
        types.InlineKeyboardButton(text="📋 Rules & FAQ", callback_data="menu_rules")
    )
    if is_admin:
        builder.row(types.InlineKeyboardButton(text="🛠️ Admin Panel", callback_data="admin_panel"))
    return builder.as_markup()

# --- START COMMAND ---
@dp.message(F.text == "/start")
async def cmd_start(message: types.Message):
    is_admin = (message.from_user.id == SUPER_ADMIN_ID)
    if not bot_settings["is_bot_on"] and not is_admin:
        await message.answer("⚠️ বট বর্তমানে মেইনটেনেন্স মোডে রয়েছে। অনুগ্রহ করে পরে চেষ্টা করুন।")
        return

    welcome_text = (
        "💎 **স্বাগতম NIKAN EARN প্ল্যাটফর্মে!**\n\n"
        "নিচের অপশনগুলো থেকে আপনার প্রয়োজনীয় সেবাটি নির্বাচন করুন। 👇"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu(is_admin))

# --- ADMIN PANEL & CONTROLS ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel_handler(callback: types.CallbackQuery):
    if callback.from_user.id != SUPER_ADMIN_ID:
        await callback.answer("❌ আপনার এই সেকশনে প্রবেশাধিকার নেই!", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    s_bot = "🟢 ON" if bot_settings["is_bot_on"] else "🔴 OFF"
    s_fund = "🟢 ON" if bot_settings["fund_system"] else "🔴 OFF"
    s_wd = "🟢 ON" if bot_settings["withdraw_system"] else "🔴 OFF"

    builder.row(types.InlineKeyboardButton(text=f"Bot Status: {s_bot}", callback_data="toggle_bot"))
    builder.row(types.InlineKeyboardButton(text=f"Fund System: {s_fund}", callback_data="toggle_fund"),
                types.InlineKeyboardButton(text=f"Withdraw System: {s_wd}", callback_data="toggle_wd"))
    builder.row(types.InlineKeyboardButton(text="« মূল মেনু (Back)", callback_data="back_home"))

    await callback.message.edit_text(
        "🛠️ **Admin Control Panel**\n\nবটের ডিপোজিট, উইথড্র এবং গ্লোবাল স্ট্যাটাস নিয়ন্ত্রণ করুন:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.in_({"toggle_bot", "toggle_fund", "toggle_wd"}))
async def handle_toggles(callback: types.CallbackQuery):
    if callback.from_user.id != SUPER_ADMIN_ID:
        return
    if callback.data == "toggle_bot":
        bot_settings["is_bot_on"] = not bot_settings["is_bot_on"]
    elif callback.data == "toggle_fund":
        bot_settings["fund_system"] = not bot_settings["fund_system"]
    elif callback.data == "toggle_wd":
        bot_settings["withdraw_system"] = not bot_settings["withdraw_system"]
    await admin_panel_handler(callback)

# --- DEPOSIT SYSTEM ---
@dp.callback_query(F.data == "menu_deposit")
async def deposit_menu(callback: types.CallbackQuery):
    if not bot_settings["fund_system"]:
        await callback.answer("⚠️ ডিপোজিট সিস্টেম বর্তমানে বন্ধ রয়েছে।", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    b_status = "🪙 চালু" if bot_settings["gateways"]["bkash"] else "⚡ বন্ধ"
    n_status = "💠 চালু" if bot_settings["gateways"]["nagad"] else "⚡ বন্ধ"
    u_status = "🔐 চালু" if bot_settings["gateways"]["usdt"] else "⚡ বন্ধ"

    builder.row(
        types.InlineKeyboardButton(text=f"💎 bKash — {b_status}", callback_data="dep_bkash"),
        types.InlineKeyboardButton(text=f"🌸 Nagad — {n_status}", callback_data="dep_nagad")
    )
    builder.row(
        types.InlineKeyboardButton(text="🚀 Rocket — ⚡ বন্ধ", callback_data="dep_rocket"),
        types.InlineKeyboardButton(text="🟣 Upay — 💫 বন্ধ", callback_data="dep_upay")
    )
    builder.row(types.InlineKeyboardButton(text=f"🟡 Binance (USDT) — {u_status}", callback_data="dep_usdt"))
    builder.row(types.InlineKeyboardButton(text="« মূল মেনু (Back)", callback_data="back_home"))

    text = (
        "📥 **Deposit**\n\n"
        "আপনার পছন্দের Payment Method নির্বাচন করে Deposit Process শুরু করুন।\n\n"
        "📰 পেমেন্ট মাধ্যম বেছে নিন:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.in_({"dep_rocket", "dep_upay"}))
async def closed_gateway_alert(callback: types.CallbackQuery):
    method_name = "রকেট" if "rocket" in callback.data else "উপায়"
    text = (
        f"⚠️ পেমেন্ট মেথড সাময়িকভাবে বন্ধ\n"
        f"দুঃখিত! {method_name} পেমেন্ট বর্তমানে সাময়িকভাবে বন্ধ রয়েছে。\n\n"
        f"এই মেথডের মাধ্যমে এই মুহূর্তে কোনো ডিপোজিট করা যাবে না。\n"
        f"🔄 অনুগ্রহ করে অন্য কোনো সক্রিয় পেমেন্ট মেথড নির্বাচন করুন।"
    )
    await callback.answer(text, show_alert=True)

@dp.callback_query(F.data.in_({"dep_bkash", "dep_nagad"}))
async def bkash_nagad_deposit(callback: types.CallbackQuery, state: FSMContext):
    method = "বিকাশ" if "bkash" in callback.data else "নগদ"
    await state.update_data(deposit_method=method)
    await state.set_state(DepositStates.waiting_for_amount)

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="❌ বাতিল", callback_data="menu_deposit"))

    text = (
        f"🔐 ফান্ড ডিপোজিট ({method})\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📲 নিচের অপশন থেকে একটি মেথড নির্বাচন করুন।👇\n\n"
        f"নগদ বিকাশ\n\n"
        "ডিপোজিট লিমিট রয়েছে: 0/3\n\n"
        "আপনি কত টাকা ডিপোজিট করতে চান? সর্বনিম্ন ৫০ সর্বোচ্চ ১০০০০\n"
        "অনুগ্রহ করে টাকার পরিমাণ লিখুন:"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.message(DepositStates.waiting_for_amount)
async def process_deposit_amount_input(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.reply("⚠️ অনুগ্রহ করে সঠিক সংখ্যায় টাকার পরিমাণ লিখুন।")
        return

    amount = int(message.text)
    if amount < 50 or amount > 10000:
        await message.reply("⚠️ ডিপোজিট সীমা: সর্বনিম্ন ৫০ এবং সর্বোচ্চ ১০,০০০ টাকা। সঠিক পরিমাণ দিন।")
        return

    data = await state.get_data()
    method = data.get("deposit_method", "বিকাশ")
    await state.clear()

    # Successful Simulation Message
    success_text = (
        f"🎉 Deposit Successful!\n"
        f"আপনার {method} Deposit সফলভাবে সম্পন্ন হয়েছে। ✅\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 Deposit Amount: {amount}.0 BDT\n"
        f"📝 Transaction ID: Atyuaanab8\n"
        f"🆔 Order Number: RC202609181420583097036909\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💳 আপনার মূল ডিপোজিট ব্যালেন্সে {amount}.0 BDT যোগ করা হয়েছে।\n"
        "ধন্যবাদ। ❤️"
    )
    await message.answer(success_text, parse_mode="Markdown")

@dp.callback_query(F.data == "dep_usdt")
async def usdt_deposit_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(DepositStates.waiting_usdt_hash)
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="❌ বাতিল", callback_data="menu_deposit"))

    text = (
        "🟡 USDT — BEP20 ডিপোজিট\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💱 ডিপোজিট রেট:\n\n"
        "1 USDT = ৳125\n"
        "💰 1 USDT ডিপোজিট করলে ব্যালেন্সে ৳125 যোগ হবে।\n"
        "📌 ডিপোজিটের ধাপ:\n"
        "① আপনার ওয়ালেট/এক্সচেঞ্জে গিয়ে USDT → Withdraw/Send নির্বাচন করুন।\n"
        "② নিচের BEP20 Address কপি করুন:\n"
        "`0xade76b7f023c3ded14850293ea26e477edbdd048`\n"
        "③ Network হিসেবে BEP20 (BSC) নির্বাচন করুন।\n"
        "④ আপনার কাঙ্ক্ষিত পরিমাণ USDT পাঠান।\n"
        "⑤ ট্রানজেকশন সম্পন্ন হলে TxnID / Transaction Hash কপি করুন।\n"
        "⑥ নিচে আপনার Transaction Hashটি দিয়ে সাবমিট করুন 👇\n"
        "⚠️ শুধুমাত্র BEP20 (BSC) নেটওয়ার্ক ব্যবহার করুন।\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.message(DepositStates.waiting_usdt_hash)
async def process_usdt_hash_input(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("আপনার ট্রানজেকশন আইডিটি সফলভাবে পাওয়া গেছে দুই মিনিটের ভেতর কনফার্মেশন পাবেন। ✅", parse_mode="Markdown")

# --- WITHDRAW SYSTEM ---
@dp.callback_query(F.data == "menu_withdraw")
async def withdraw_menu(callback: types.CallbackQuery):
    if not bot_settings["withdraw_system"]:
        await callback.answer("⚠️ উইথড্র সিস্টেম বর্তমানে বন্ধ রয়েছে।", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="📱 bKash", callback_data="wd_bkash"),
        types.InlineKeyboardButton(text="🪙 Nagad", callback_data="wd_nagad")
    )
    builder.row(
        types.InlineKeyboardButton(text="⚡ Rocket", callback_data="wd_rocket"),
        types.InlineKeyboardButton(text="🔰 Upay", callback_data="wd_upay")
    )
    builder.row(types.InlineKeyboardButton(text="« মূল মেনু (Back)", callback_data="back_home"))

    text = (
        "💸 Withdraw\n"
        "উইথড্র\n\n"
        "আপনার উপলব্ধ Balance থেকে Withdraw Request করতে নিচের অপশন নির্বাচন করুন। 👇\n\n"
        "💳 Payment Method"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.in_({"wd_bkash", "wd_nagad", "wd_rocket", "wd_upay"}))
async def withdraw_method_selected(callback: types.CallbackQuery, state: FSMContext):
    method = callback.data.split("_")[1].capitalize()
    await state.update_data(wd_method=method)
    await state.set_state(WithdrawStates.waiting_number)

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="❌ বাতিল", callback_data="menu_withdraw"))

    text = (
        f"💳 আপনি {method} সিলেক্ট করেছেন।\n"
        f"📱 অনুগ্রহ করে আপনার সঠিক ১১ সংখ্যার {method} নম্বরটি লিখে পাঠান।\n"
        "উদাহরণ:\n"
        "`017XXXXXXXX`\n"
        "⚠️ নম্বরটি দেওয়ার আগে ভালোভাবে যাচাই করে নিন।"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.message(WithdrawStates.waiting_number)
async def withdraw_number_verification(message: types.Message, state: FSMContext):
    num = message.text.strip()
    if not num.isdigit() or len(num) != 11:
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="❌ বাতিল", callback_data="menu_withdraw"))
        await message.reply(
            f"আপনি ভুল নাম্বার দিয়েছেন দয়া করে সঠিক ১১ ডিজিটের মোবাইল নাম্বারটি নিচে দিন।",
            reply_markup=builder.as_markup()
        )
        return

    await state.update_data(wd_number=num)
    await state.set_state(WithdrawStates.waiting_amount)

    text = (
        "💰 আপনার বর্তমান ব্যালেন্স: ৫,০০০৳\n"
        "💸 উইথড্র সীমা:\n\n"
        "▫️ সর্বনিম্ন: ১,০০০৳\n"
        "▫️ সর্বোচ্চ: ২৫,০০০৳\n\n"
        "🏦 নম্বর সফলভাবে গ্রহণ করা হয়েছে।\n"
        "✍️ এখন আপনি কত টাকা উইথড্র করতে চান, শুধু টাকার পরিমাণটি সংখ্যায় লিখে পাঠান।\n"
        "উদাহরণ: 100"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(WithdrawStates.waiting_amount)
async def withdraw_amount_verification(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.reply("⚠️ সঠিক অংকে টাকার পরিমাণ লিখুন।")
        return

    amount = int(message.text)
    if amount < 1000 or amount > 25000:
        error_text = (
            "⚠️ উইথড্র পরিমাণ সঠিক নয়!\n"
            "💰 উইথড্র করার সীমা:\n"
            "• সর্বনিম্ন — ১,০০০৳\n"
            "• সর্বোচ্চ — ২৫,০০০৳\n"
            "আপনার বর্তমান ব্যালেন্স ৫,০০০ ৳\n\n"
            "👉 অনুগ্রহ করে ১,০০০৳ থেকে ২৫,০০০৳ এর মধ্যে সঠিক পরিমাণ লিখে আবার চেষ্টা করুন।"
        )
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🔰 বাতিল", callback_data="menu_withdraw"))
        await message.reply(error_text, parse_mode="Markdown", reply_markup=builder.as_markup())
        return

    await state.clear()
    await message.answer(
        f"💸 {amount}৳ উইথড্র রিকোয়েস্ট সফলভাবে জমা হয়েছে!\n"
        "⏳ প্রসেসিং সময়: ২৪ ঘন্টা\n"
        "অনুমোদন সম্পন্ন হওয়া পর্যন্ত অপেক্ষা করুন।",
        parse_mode="Markdown"
    )

# --- ACCOUNT, REFERRAL & DAILY EARNINGS ---
@dp.callback_query(F.data == "menu_account")
async def account_info(callback: types.CallbackQuery):
    user = callback.from_user
    text = (
        "📊 MY ACCOUNT • আমার অ্যাকাউন্ট\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 ব্যবহারকারীর নাম: {user.first_name}\n"
        f"🔗 ইউজারনেম: @{user.username if user.username else 'N/A'}\n"
        f"🆔 ইউজার আইডি: `{user.id}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💰 BALANCE DETAILS\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💵 মোট ব্যালেন্স: ৫,০০০ টাকা\n"
        "📥 ডিপোজিট ব্যালেন্স: ১,০০০ টাকা\n"
        "🎁 ডিপোজিট বোনাস: ২০০ টাকা\n"
        "🫂 রেফার ব্যালেন্স: ৫০০ টাকা\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 ACCOUNT STATUS\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏳ Plan এর মেয়াদ:\n"
        "• VIP 1 — ৩ দিন\n"
        "• VIP 2 — ৪ দিন\n"
        "🚫 নিষিদ্ধ: না\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ আপনার অ্যাকাউন্টের সকল তথ্য এখানে দেখানো হয়েছে।"
    )
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="« মূল মেনু (Back)", callback_data="back_home"))
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "menu_referral")
async def referral_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Share করুন 🔗", url="https://t.me/share/url?url=https://t.me/NikanEarnBot"))
    builder.row(types.InlineKeyboardButton(text="« মূল মেনু (Back)", callback_data="back_home"))

    text = (
        "👥 Referral\n"
        "রেফারেল\n\n"
        "👥 Referral Program\n\n"
        "বন্ধুদের আপনার Referral Link দিয়ে Join করান এবং প্রযোজ্য Referral Reward সম্পর্কে এখানে দেখুন।\n"
        "আপনার রেফার করা ব্যক্তির কাছ যদি ডিপোজিট করে তাহলে ৫% কমিশন আপনি পাবেন!\n\n"
        "🔗 Your Referral Link: `https://t.me/NikanEarnBot?start=ref123`\n"
        "👤 Total Referrals: ০ জন।\n"
        "💰 Referral Earnings: ০ ৳।\n"
        "📢 আপনার Referral Link শেয়ার করতে নিচের অপশন ব্যবহার করুন।"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "menu_earnings")
async def daily_earnings_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🧮 Today Earnings Claim", callback_data="claim_earnings"))
    builder.row(types.InlineKeyboardButton(text="« মূল মেনু (Back)", callback_data="back_home"))

    text = (
        "📊 Daily Earnings\n"
        "দৈনিক আয়\n\n"
        "📊 Daily Earnings\n\n"
        "আপনার Earnings-এর বর্তমান তথ্য এখানে দেখতে পারবেন।\n"
        "💰 Today: ৳০\n"
        "📈 Total Earnings: ৳০\n"
        "📅 Earnings History: কোনো হিস্ট্রি নেই\n\n"
        "ℹ️ Earnings প্ল্যান ও শর্ত অনুযায়ী পরিবর্তিত হতে পারে।\n\n"
        "যা ক্রয় করেছেন 🔰\n"
        "• VIP 1 প্যাকেজ"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "claim_earnings")
async def claim_action(callback: types.CallbackQuery):
    await callback.answer("✅ আপনার আজকের ইনকাম সফলভাবে ক্লেইম করা হয়েছে!", show_alert=True)

# --- BONUS CENTER ---
@dp.callback_query(F.data == "menu_bonus")
async def bonus_center(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Next ▶️", callback_data="bonus_next"))
    builder.row(types.InlineKeyboardButton(text="« মূল মেনু (Back)", callback_data="back_home"))

    text = (
        "🎁 Bonus Center\n"
        "বোনাস সেন্টার\n\n"
        "আপনার জন্য উপলব্ধ Bonus ও Reward এখানে দেখতে পারবেন।\n"
        "🎁 Available Bonus: ৳৫\n"
        "🏆 Active Rewards: কোনো রিওয়ার্ড নেই\n"
        "📜 Bonus History (প্রতি ৫টি এরপর Next ▶️)\n\n"
        "✅ প্রতিদিন ৫ টাকা এখান থেকে ক্লেইম করা যাবে ফ্রিতে যা শুধু বোনাস ব্যালেন্সে অ্যাড হবে উইড্রো করা যাবে না এবং তা দিয়ে Plan কিনা যাবে না।"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

# --- AVAILABLE PLANS (VIP 1 - VIP 12) ---
@dp.callback_query(F.data == "menu_plans")
async def available_plans_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    # 3 or 4 items per row as requested
    builder.row(
        types.InlineKeyboardButton(text="VIP 1 (৳300)", callback_data="plan_1"),
        types.InlineKeyboardButton(text="VIP 2 (৳500)", callback_data="plan_2"),
        types.InlineKeyboardButton(text="VIP 3 (৳1,000)", callback_data="plan_3")
    )
    builder.row(
        types.InlineKeyboardButton(text="VIP 4 (৳2,000)", callback_data="plan_4"),
        types.InlineKeyboardButton(text="VIP 5 (৳3,000)", callback_data="plan_5"),
        types.InlineKeyboardButton(text="VIP 6 (৳5,000)", callback_data="plan_6")
    )
    builder.row(
        types.InlineKeyboardButton(text="VIP 7 (৳7,500)", callback_data="plan_7"),
        types.InlineKeyboardButton(text="VIP 8 (৳10,000)", callback_data="plan_8"),
        types.InlineKeyboardButton(text="VIP 9 (৳15,000)", callback_data="plan_9")
    )
    builder.row(
        types.InlineKeyboardButton(text="VIP 10 (৳20,000)", callback_data="plan_10"),
        types.InlineKeyboardButton(text="VIP 11 (৳30,000)", callback_data="plan_11"),
        types.InlineKeyboardButton(text="VIP 12 (৳50,000)", callback_data="plan_12")
    )
    builder.row(types.InlineKeyboardButton(text="« মূল মেনু (Back)", callback_data="back_home"))

    text = (
        "💎 Available Plans\n"
        "উপলব্ধ প্ল্যানসমূহ\n\n"
        "উপলব্ধ Investment Plans দেখতে নিচের অপশন থেকে আপনার পছন্দের প্ল্যানে চাপ দিন। 👇"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("plan_"))
async def single_plan_details(callback: types.CallbackQuery):
    plan_id = callback.data.split("_")[1]
    amounts = {
        "1": "300", "2": "500", "3": "1,000", "4": "2,000",
        "5": "3,000", "6": "5,000", "7": "7,500", "8": "10,000",
        "9": "15,000", "10": "20,000", "11": "30,000", "12": "50,000"
    }
    amt = amounts.get(plan_id, "300")

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Plan Buy 💸", callback_data=f"buy_plan_{plan_id}"))
    builder.row(types.InlineKeyboardButton(text="« প্ল্যান তালিকা (Back)", callback_data="menu_plans"))

    text = (
        "💼 Plan Details\n"
        "INGKA INVESTMENTS\n\n"
        f"💎 VIP {plan_id} — Ingka বিনিয়োগ\n"
        f"💰 Amount: ৳{amt}\n"
        "📅 Duration: 4 দিন\n"
        "📊 Return: 34% (প্রতিদিন)\n\n"
        "নিচে Plan Buy বাটনে ক্লিক করে প্যাকেজটি সক্রিয় করুন।"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("buy_plan_"))
async def buy_plan_action(callback: types.CallbackQuery):
    plan_id = callback.data.split("_")[2]
    text = (
        f"🎊 অভিনন্দন! আপনার VIP {plan_id} Plan সফলভাবে সক্রিয় হয়েছে। ✅\n\n"
        f"💎 Plan: VIP {plan_id}\n"
        "📅 মেয়াদ: 4 দিন\n"
        "💵 দৈনিক ইনকাম ক্লেইম করতে:\n"
        "👇 নিচের 📊 Daily Earnings বাটনে চাপ দিন।"
    )
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📊 Daily Earnings", callback_data="menu_earnings"))
    builder.row(types.InlineKeyboardButton(text="« মূল মেনু (Back)", callback_data="back_home"))
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

# --- TRANSACTION HISTORY ---
@dp.callback_query(F.data == "menu_history")
async def transaction_history_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📥 Deposit History (Next ▶️)", callback_data="hist_dep"))
    builder.row(types.InlineKeyboardButton(text="📤 Withdraw History (Next ▶️)", callback_data="hist_wd"))
    builder.row(types.InlineKeyboardButton(text="📊 Earnings History (Next ▶️)", callback_data="hist_earn"))
    builder.row(types.InlineKeyboardButton(text="« মূল মেনু (Back)", callback_data="back_home"))

    text = (
        "🧾 Transaction History\n"
        "লেনদেনের ইতিহাস\n\n"
        "আপনার Account-এর Deposit, Withdraw এবং অন্যান্য Transaction-এর তথ্য এখানে দেখতে পারবেন।👇"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

# --- HELP & SUPPORT / RULES ---
@dp.callback_query(F.data == "menu_support")
async def help_support_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📞 Support Center", url="https://t.me/Nikan_Support01"))
    builder.row(types.InlineKeyboardButton(text="📢 Official Channel", url="https://t.me/NIKAN_EARN"))
    builder.row(types.InlineKeyboardButton(text="« মূল মেনু (Back)", callback_data="back_home"))

    text = (
        "🆘 Help & Support\n"
        "সাহায্য ও সাপোর্ট\n\n"
        "কোনো সমস্যা বা প্রশ্ন থাকলে আমাদের Support Team-এর সাথে যোগাযোগ করুন।\n"
        "📌 Account Problem\n"
        "💳 Deposit Problem\n"
        "💸 Withdraw Problem\n"
        "👥 Referral Problem\n"
        "❓ Other Issues\n"
        "🕐 Support Hours: Available as stated by the service."
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "menu_rules")
async def rules_faq_menu(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="« মূল মেনু (Back)", callback_data="back_home"))

    text = (
        "📋 Rules & FAQ\n"
        "নিয়ম ও প্রশ্নোত্তর\n\n"
        "🌐 About NIKAN\n"
        "NIKAN একটি অনলাইন Earning Platform, যেখানে ব্যবহারকারীরা বিভিন্ন earning features, Referral Program এবং উপলব্ধ Plans-এর মাধ্যমে আয় করার সুযোগ পেতে পারেন।\n\n"
        "💎 Available Plans\n"
        "💰 Real Earning Opportunities\n"
        "📊 Track Your Earnings\n"
        "👥 Referral Program\n"
        "🧾 Transaction History\n"
        "🆘 User Support"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=builder.as_markup())

# --- BACK TO HOME HANDLER ---
@dp.callback_query(F.data == "back_home")
async def back_to_home(callback: types.CallbackQuery):
    is_admin = (callback.from_user.id == SUPER_ADMIN_ID)
    welcome_text = (
        "💎 **স্বাগতম NIKAN EARN প্ল্যাটফর্মে!**\n\n"
        "নিচের অপশনগুলো থেকে আপনার প্রয়োজনীয় সেবাটি নির্বাচন করুন। 👇"
    )
    await callback.message.edit_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu(is_admin))

# --- MAIN EXECUTION LOOP ---
async def main():
    print("Bot is running successfully with all requirements...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
