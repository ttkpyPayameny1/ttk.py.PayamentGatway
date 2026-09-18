import sqlite3
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

# আপনার বটের টেলিগ্রাম টোকেন এখানে বসান
TOKEN = '8631873007:AAEVtP7swVa82bIl8Mr_seyzi1MdFwQzvM4'
bot = telebot.TeleBot(TOKEN)

# ডাটাবেস ইনিশিয়ালাইজেশন
def init_db():
    conn = sqlite3.connect('nikan_earn.db')
    cursor = conn.cursor()
    # ইউজার টেবিল
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            main_balance REAL DEFAULT 0.0,
            deposit_balance REAL DEFAULT 0.0,
            deposit_bonus REAL DEFAULT 0.0,
            refer_balance REAL DEFAULT 0.0,
            bonus_balance REAL DEFAULT 0.0,
            plan_claim_balance REAL DEFAULT 0.0,
            total_referrals INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
    ''')
    # ট্রানজেকশন টেবিল
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            method TEXT,
            amount REAL,
            order_no TEXT,
            status TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # অ্যাক্টিভ প্ল্যান টেবিল
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            plan_name TEXT,
            amount REAL,
            daily_income REAL,
            days_left INTEGER,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# প্রধান মেইন মেনু কিবোর্ড (বটের কমান্ড বা ব্যাক বাটনের উপরে থাকবে)
def main_menu_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton('🔐 ফান্ড ডিপোজিট'), KeyboardButton('💸 উইথড্র'))
    markup.add(KeyboardButton('👥 রেফারেল'), KeyboardButton('📊 ডেইলি আয়'))
    markup.add(KeyboardButton('🎁 বোনাস সেন্টার'), KeyboardButton('💎 উপলব্ধ প্ল্যান'))
    markup.add(KeyboardButton('📊 আমার অ্যাকাউন্ট'), KeyboardButton('🧾 ট্রানজেকশন ইতিহাস'))
    markup.add(KeyboardButton('🆘 সাহায্য ও সাপোর্ট'))
    return markup

# /start কমান্ড
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or "None"
    full_name = message.from_user.full_name

    conn = sqlite3.connect('nikan_earn.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            'INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)',
            (user_id, username, full_name)
        )
        conn.commit()
    conn.close()

    welcome_text = (
        f"স্বাগতম, {full_name}!\n"
        "NIKAN একটি অনলাইন Earning Platform। নিচের মেনু থেকে আপনার পছন্দের অপশন বেছে নিন। 👇"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu_keyboard())

# মেনু অপشن হ্যান্ডলার
@bot.message_handler(func=lambda message: True)
def handle_menu_options(message):
    text = message.text
    user_id = message.from_user.id

    if text == '🔐 ফান্ড ডিপোজিট':
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton('💳 বিকাশ', callback_data='dep_bkash'),
            InlineKeyboardButton('💠 নগদ', callback_data='dep_nagad')
        )
        markup.add(
            InlineKeyboardButton('🚀 রকেট', callback_data='dep_rocket'),
            InlineKeyboardButton('🟣 উপায়', callback_data='dep_upay')
        )
        markup.add(InlineKeyboardButton('🟡 Binance (USDT)', callback_data='dep_usdt'))
        markup.add(InlineKeyboardButton('❌ বাতিল', callback_data='cancel'))
        
        bot.send_message(
            message.chat.id,
            "🔐 ফান্ড ডিপোজিট\n━━━━━━━━━━━━━━━━━━\n📲 নিচের অপশন থেকে একটি মেথড নির্বাচন করুন।👇",
            reply_markup=markup
        )

    elif text == '📊 আমার অ্যাকাউন্ট':
        conn = sqlite3.connect('nikan_earn.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        u = cursor.fetchone()
        conn.close()

        if u:
            acc_text = (
                f"📊 MY ACCOUNT • আমার অ্যাকাউন্ট\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 ব্যবহারকারীর নাম: {u[2]}\n"
                f"🔗 ইউজারনেম: @{u[1]}\n"
                f"🆔 ইউজার আইডি: {u[0]}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 BALANCE DETAILS\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 মোট ব্যালেন্স: {u[3]} টাকা\n"
                f"📥 ডিপোজিট ব্যালেন্স: {u[4]} টাকা\n"
                f"🎁 ডিপোজিট বোনাস: {u[5]} টাকা\n"
                f"🫂 রেফার ব্যালেন্স: {u[6]} টাকা\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👑 ACCOUNT STATUS\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🚫 নিষিদ্ধ: {'হ্যাঁ' if u[10] == 1 else 'না'}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✨ আপনার অ্যাকাউন্টের সকল তথ্য এখানে দেখানো হয়েছে।"
            )
            bot.send_message(message.chat.id, acc_text, reply_markup=main_menu_keyboard())

    elif text == '💸 উইথড্র':
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton('💳 বিকাশ', callback_data='wd_bkash'),
            InlineKeyboardButton('🪙 নগদ', callback_data='wd_nagad'),
            InlineKeyboardButton('💲 USD', callback_data='wd_usd'),
            InlineKeyboardButton('⚡ রকেট', callback_data='wd_rocket'),
            InlineKeyboardButton('🔰 উপায়', callback_data='wd_upay')
        )
        bot.send_message(
            message.chat.id,
            "💸 উইথড্র\n\nআপনার উপলব্ধ Balance থেকে Withdraw Request করতে নিচের অপশন নির্বাচন করুন।👇",
            reply_markup=markup
        )

    elif text == '👥 রেফারেল':
        refer_text = (
            f"👥 Referral Program\n\n"
            f"বন্ধুদের আপনার Referral Link দিয়ে Join করান এবং প্রযোজ্য Referral Reward সম্পর্কে এখানে দেখুন।\n"
            f"আপনার রেফার করা ব্যক্তির কাছ যদি ডিপোজিট করে তাহলে ৫% কমিশন আপনি পাবেন!\n\n"
            f"🔗 Your Referral Link: `https://t.me/YourBotName?start=ref_{user_id}`\n"
            f"👤 Total Referrals: 0 জন।\n"
            f"💰 Referral Earnings: 0 ৳।"
        )
        bot.send_message(message.chat.id, refer_text, parse_mode="Markdown", reply_markup=main_menu_keyboard())

    elif text == '🎁 বোনাস সেন্টার':
        bonus_text = (
            "🎁 Bonus Center\n\n"
            "আপনার জন্য উপলব্ধ Bonus ও Reward এখানে দেখতে পারবেন।\n"
            "🎁 Available Bonus: 0 ৳\n\n"
            "প্রতিদিন ৫ টাকা এখান থেকে ক্লেইম করা যাবে ফ্রিতে (যা শুধু বোনাস ব্যালেন্সে অ্যাড হবে, উইথড্র করা যাবে না)।"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton('🎁 Daily Bonus Claim (5 ৳)', callback_data='claim_daily_bonus'))
        bot.send_message(message.chat.id, bonus_text, reply_markup=markup)

    elif text == '💎 উপলব্ধ প্ল্যান':
        plans_text = (
            "💎 Available Plans • উপলব্ধ প্ল্যানসমূহ\n\n"
            "INGKA INVESTMENTS - ৩% দৈনিক রিটার্ন (৪ দিনের মেয়াদ)। সর্বোচ্চ ২টি প্যাকেজ একইসাথে সক্রিয় রাখা যাবে।"
        )
        markup = InlineKeyboardMarkup(row_width=3)
        markup.add(
            InlineKeyboardButton('VIP 1 (300৳)', callback_data='buy_vip_1'),
            InlineKeyboardButton('VIP 2 (500৳)', callback_data='buy_vip_2'),
            InlineKeyboardButton('VIP 3 (1000৳)', callback_data='buy_vip_3'),
            InlineKeyboardButton('VIP 4 (2000৳)', callback_data='buy_vip_4'),
            InlineKeyboardButton('VIP 5 (3000৳)', callback_data='buy_vip_5'),
            InlineKeyboardButton('VIP 6 (5000৳)', callback_data='buy_vip_6')
        )
        bot.send_message(message.chat.id, plans_text, reply_markup=markup)

    elif text == '🆘 সাহায্য ও সাপোর্ট':
        support_text = (
            "🆘 Help & Support\n\n"
            "কোনো সমস্যা বা প্রশ্ন থাকলে আমাদের Support Team-এর সাথে যোগাযোগ করুন।"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton('📞 Support Center', url='https://t.me/Nikan_Support01'))
        markup.add(InlineKeyboardButton('📢 Official Channel', url='https://t.me/NIKAN_EARN'))
        bot.send_message(message.chat.id, support_text, reply_markup=markup)

    else:
        bot.send_message(message.chat.id, "দয়া করে নিচের মেনু থেকে সঠিক অপশনটি বেছে নিন।", reply_markup=main_menu_keyboard())

# ইনলাইন কলব্যাক কুয়েরি হ্যান্ডলার (ডিপোজিট, উইথড্র ও প্ল্যান কেনার জন্য)
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    data = call.data
    user_id = call.from_user.id

    if data == 'dep_bkash' or data == 'dep_nagad':
        method_name = "BKash" if 'bkash' in data else "Nagad"
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            f"💳 {method_name} ডিপোজিট গেটওয়ে\n\nডিপোজিট লিমিট: সর্বনিম্ন ৫০ সর্বোচ্চ ১০০০০ টাকা।\nঅনুগ্রহ করে টাকার পরিমাণ লিখে পাঠান:"
        )

    elif data == 'dep_rocket' or data == 'dep_upay':
        method_name = "রকেট" if 'rocket' in data else "উপায়"
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            f"⚠️ পেমেন্ট মেথড সাময়িকভাবে বন্ধ\nদুঃখিত! {method_name} পেমেন্ট বর্তমানে সাময়িকভাবে বন্ধ রয়েছে।"
        )

    elif data == 'dep_usdt':
        usdt_text = (
            "🟡 USDT — BEP20 ডিপোজিট\n━━━━━━━━━━━━━━━━━━\n"
            "💱 ডিপোজিট রেট: 1 USDT = ৳125\n\n"
            "নিচের BEP20 Address কপি করে ডিপোজিট করুন এবং Transaction Hash সাবমিট করুন:\n"
            "`0xade76b7f023c3ded14850293ea26e477edbdd048`"
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, usdt_text, parse_mode="Markdown")

    elif data.startswith('buy_vip_'):
        vip_num = data.split('_')[-1]
        amounts = {'1': 300, '2': 500, '3': 1000, '4': 2000, '5': 3000, '6': 5000}
        amt = amounts.get(vip_num, 300)
        
        bot.answer_callback_query(call.id)
        success_text = (
            f"🎊 অভিনন্দন! আপনার VIP {vip_num} Plan সফলভাবে সক্রিয় হয়েছে। ✅\n\n"
            f"💎 Plan: VIP {vip_num}\n"
            f"💰 বিনিয়োগ: ৳{amt}\n"
            f"📅 মেয়াদ: 4 দিন\n"
            f"📊 দৈনিক আয়: ৳{amt * 0.34:.1f}\n\n"
            f"দৈনিক ইনকাম ক্লেইম করতে নিচে 📊 ডেইলি আয় অপশনে চাপ দিন।"
        )
        bot.send_message(call.message.chat.id, success_text)

    elif data == 'cancel':
        bot.answer_callback_query(call.id, "অপারেশন বাতিল করা হয়েছে।")
        bot.send_message(call.message.chat.id, "মেইন মেনুতে ফিরে এসেছেন:", reply_markup=main_menu_keyboard())

# বট রান করা
if __name__ == '__main__':
    print("NIKAN Earn Bot is running successfully...")
    bot.infinity_polling()
