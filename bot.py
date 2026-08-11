import os
import json
import uuid
import threading
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes
from upstash_redis import Redis

# Múi giờ Việt Nam (UTC+7)
VN_TZ = timezone(timedelta(hours=7))

# Cấu hình Token & ID Admin Telegram
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8766885663:AAHbYNiInm0R7b3LIMhxoTUwK2NlSjDuDwE").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "7126654319").strip()

# Thông tin Upstash Redis
UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "https://crucial-redfish-68584.upstash.io").strip()
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "gQAAAAAAAQvoAAIgcDE5MmE5MzU4ODUwZDY0MWM5OTMwNjQ1YzVlMTA1MGRiZg").strip()

# Khởi tạo kết nối Upstash Redis
redis = Redis(url=UPSTASH_URL, token=UPSTASH_TOKEN)

# Hàm đọc tất cả keys từ Đám Mây Redis (Đã xử lý parse JSON chuẩn)
def get_all_keys():
    try:
        keys_data = redis.get("dns_vip_keys")
        if not keys_data:
            return {}
        if isinstance(keys_data, str):
            return json.loads(keys_data)
        return keys_data
    except Exception as e:
        print(f"Lỗi đọc dữ liệu từ Redis: {e}")
        return {}

# Hàm lưu keys lên Đám Mây Redis (Đã ép kiểu json.dumps)
def save_all_keys(keys_dict):
    try:
        redis.set("dns_vip_keys", json.dumps(keys_dict, ensure_ascii=False))
    except Exception as e:
        print(f"Lỗi lưu dữ liệu lên Redis: {e}")

orders = {}
app = Flask(__name__)
CORS(app)

# ==================== CÁC LỆNH TELEGRAM ====================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Bạn không có quyền dùng Bot này!")
        return

    help_text = (
        "📖 **BẢNG HƯỚNG DẪN QUẢN LÝ BOT DUC KIEN DNS**\n\n"
        "🔑 **1. Tạo mã Key (Lưu đám mây 100% vĩnh viễn):**\n"
        "• `/genkey <tên_key> <số_ngày> <giá>`\n"
        "  *Ví dụ:* `/genkey VIP30 30 15000` (Key 30 ngày - Giá 15k)\n"
        "  *Ví dụ:* `/genkey FREE30 30 0` (Key Miễn phí 0đ)\n\n"
        "🗑️ **2. Xóa mã Key:**\n"
        "• `/delkey <tên_key>` (Ví dụ: `/delkey VIP30`)\n\n"
        "📋 **3. Xem danh sách mã đang có:**\n"
        "• `/listkeys`"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def genkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này!")
        return

    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "⚠️ **Cú pháp chưa đúng:** `/genkey <tên_key> <số_ngày> <giá_tiền>`\n"
            "Ví dụ: `/genkey VIP30 30 15000`",
            parse_mode="Markdown"
        )
        return

    custom_key = args[0].upper()
    try:
        days = int(args[1])
        price = int(args[2])
    except ValueError:
        await update.message.reply_text("⚠️ Số ngày và Giá tiền phải là chữ số hợp lệ!")
        return

    keys = get_all_keys()
    if custom_key in keys:
        await update.message.reply_text(f"❌ Mã `{custom_key}` đã tồn tại trước đó!", parse_mode="Markdown")
        return

    keys[custom_key] = {
        "days": days,
        "price": price,
        "created_at": datetime.now(VN_TZ).strftime("%H:%M:%S - %d/%m/%Y")
    }
    
    # Lưu vĩnh viễn lên Upstash Redis
    save_all_keys(keys)

    await update.message.reply_text(
        f"🎉 **ĐÃ TẠO MÃ KEY THÀNH CÔNG (ĐÃ LƯU ĐÁM MÂY)!**\n\n"
        f"🔑 **Mã Key:** `{custom_key}`\n"
        f"⏳ **Thời hạn:** `{days} ngày`\n"
        f"💵 **Giá thiết lập:** `{price:,} VNĐ`\n\n"
        f"👉 *Mã này đã được bảo vệ vĩnh viễn trên Upstash Cloud!*",
        parse_mode="Markdown"
    )

async def delkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Cú pháp: `/delkey <tên_key>`", parse_mode="Markdown")
        return

    target_key = context.args[0].upper()
    keys = get_all_keys()

    if target_key in keys:
        del keys[target_key]
        save_all_keys(keys)
        await update.message.reply_text(f"🗑️ Đã xóa thành công mã `{target_key}` khỏi đám mây!", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Không tìm thấy mã `{target_key}`!", parse_mode="Markdown")

async def listkeys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này!")
        return

    keys = get_all_keys()
    if not keys:
        await update.message.reply_text("📂 Hiện chưa có mã kích hoạt nào trên đám mây!")
        return

    msg = "📋 **DANH SÁCH MÃ KEY ĐANG LƯU VĨNH VIỄN:**\n\n"
    for k, v in keys.items():
        msg += f"• `{k}`: {v['days']} ngày | Giá: `{v.get('price', 15000):,} VNĐ`\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

# ==================== API XỬ LÝ WEB ====================

@app.route('/create-order', methods=['POST'])
def create_order():
    try:
        data = request.json
        name = data.get('name')
        amount = data.get('amount', 15000)
        
        if not name:
            return jsonify({"success": False, "message": "Thiếu thông tin!"}), 400

        order_id = str(uuid.uuid4())[:8].upper()
        created_at = datetime.now(VN_TZ).strftime("%H:%M:%S - %d/%m/%Y")

        orders[order_id] = {
            'name': name,
            'status': 'PENDING',
            'created_at': created_at,
            'amount': amount,
            'message_id': None
        }

        msg = (
            f"🔔 **ĐƠN HÀNG MỚI NÈ!**\n\n"
            f"👤 **Khách hàng:** `{name}`\n"
            f"🆔 **Mã đơn:** `{order_id}`\n"
            f"💵 **Số tiền:** `{amount:,} VNĐ`\n"
            f"📝 **Nội dung CK:** `LOCKET {order_id}`\n"
            f"⏰ **Thời gian:** `{created_at}`\n\n"
            f"👉 *Hãy kiểm tra App Ngân hàng xem đã nhận tiền chưa:*"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ XÁC NHẬN ĐÃ NHẬN TIỀN", callback_data=f"approve_{order_id}")]
        ])

        res = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": ADMIN_CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown",
                "reply_markup": keyboard.to_dict()
            }
        ).json()

        if res.get("ok"):
            orders[order_id]['message_id'] = res['result']['message_id']

        return jsonify({"success": True, "order_id": order_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/check-key', methods=['POST'])
def check_key():
    try:
        data = request.json
        raw_key = data.get('key', '').strip().upper()

        keys = get_all_keys()
        if not raw_key or raw_key not in keys:
            return jsonify({"success": False, "message": "Mã kích hoạt không tồn tại hoặc không hợp lệ!"}), 400

        key_info = keys[raw_key]
        return jsonify({
            "success": True,
            "key": raw_key,
            "days": key_info['days'],
            "price": key_info.get('price', 0)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/cancel-order', methods=['POST'])
def cancel_order():
    try:
        data = request.json
        order_id = data.get('order_id')
        if order_id in orders:
            orders[order_id]['status'] = 'CANCELLED'
            customer_name = orders[order_id]['name']
            created_at = orders[order_id]['created_at']
            message_id = orders[order_id].get('message_id')
            cancelled_at = datetime.now(VN_TZ).strftime("%H:%M:%S - %d/%m/%Y")

            if message_id:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
                    json={
                        "chat_id": ADMIN_CHAT_ID,
                        "message_id": message_id,
                        "text": (
                            f"❌ **ĐƠN HÀNG ĐÃ BỊ HỦY / TẠO LẠI!**\n\n"
                            f"👤 **Khách hàng:** `{customer_name}`\n"
                            f"🆔 **Mã đơn:** `{order_id}`\n"
                            f"⏰ **Thời gian tạo:** `{created_at}`\n"
                            f"🚫 **Thời gian hủy:** `{cancelled_at}`"
                        ),
                        "parse_mode": "Markdown"
                    }
                )

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/check-status/<order_id>', methods=['GET'])
def check_status(order_id):
    order = orders.get(order_id)
    if not order:
        return jsonify({"status": "NOT_FOUND"})
    return jsonify({"status": order['status'], "name": order['name']})

@app.route('/', methods=['GET'])
def health_check():
    return "Bot & Server DNS Locket đang hoạt động bình thường 24/7!", 200

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("approve_"):
        order_id = query.data.split("_")[1]
        if order_id in orders:
            orders[order_id]['status'] = 'APPROVED'
            customer_name = orders[order_id]['name']
            created_at = orders[order_id]['created_at']
            completed_at = datetime.now(VN_TZ).strftime("%H:%M:%S - %d/%m/%Y")
            
            await query.edit_message_text(
                text=(
                    f"✅ **ĐÃ XÁC NHẬN THÀNH CÔNG!**\n\n"
                    f"👤 **Khách hàng:** `{customer_name}`\n"
                    f"🆔 **Mã đơn:** `{order_id}`\n"
                    f"⏰ **Thời gian tạo:** `{created_at}`\n"
                    f"🎯 **Thời gian hoàn thành:** `{completed_at}`\n\n"
                    f"🚀 *Hệ thống đã mở khóa nút Tải Profile cho khách!*"
                ),
                parse_mode="Markdown"
            )

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    threading.Thread(target=run_flask).start()
    
    tg_app = ApplicationBuilder().token(BOT_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", help_command))
    tg_app.add_handler(CommandHandler("help", help_command))
    tg_app.add_handler(CommandHandler("genkey", genkey_command))
    tg_app.add_handler(CommandHandler("delkey", delkey_command))
    tg_app.add_handler(CommandHandler("listkeys", listkeys_command))
    tg_app.add_handler(CallbackQueryHandler(button_callback))
    
    tg_app.run_polling()
