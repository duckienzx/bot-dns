import os
import io
import uuid
import threading
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes

# Múi giờ Việt Nam (UTC+7)
VN_TZ = timezone(timedelta(hours=7))

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8766885663:AAHbYNiInm0R7b3LIMhxoTUwK2NlSjDuDwE").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "7126654319").strip()

NEXTDNS_ID = "ed4988"
AUTHOR_NAME = "DNS Huy Hiệu"

app = Flask(__name__)
CORS(app)

orders = {}

# 1. API NHẬN YÊU CẦU TẠO ĐƠN TỪ WEB
@app.route('/create-order', methods=['POST'])
def create_order():
    try:
        data = request.json
        name = data.get('name')
        if not name:
            return jsonify({"success": False, "message": "Thiếu tên khách hàng!"}), 400

        order_id = str(uuid.uuid4())[:8].upper()
        created_at = datetime.now(VN_TZ).strftime("%H:%M:%S - %d/%m/%Y")

        orders[order_id] = {
            'name': name,
            'status': 'PENDING',
            'created_at': created_at,
            'message_id': None
        }

        msg = (
            f"🔔 **ĐƠN HÀNG MỚI NÈ!**\n\n"
            f"👤 **Khách hàng:** `{name}`\n"
            f"🆔 **Mã đơn:** `{order_id}`\n"
            f"💵 **Nội dung CK:** `LOCKET {order_id}`\n"
            f"⏰ **Thời gian tạo:** `{created_at}`\n\n"
            f"👉 *Hãy kiểm tra App Ngân hàng xem đã nhận tiền chưa:*"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ XÁC NHẬN ĐÃ NHẬN TIỀN", callback_data=f"approve_{order_id}")]
        ])

        # Gửi tin nhắn đến Telegram và lưu ID tin nhắn
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

# 2. API HỦY ĐƠN HÀNG KHI KHÁCH BẤM HỦY TRÊN WEB
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
                # Chỉnh sửa tin nhắn cũ: Xóa nút bấm và đổi trạng thái thành ĐÃ HỦY
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

# 3. API KIỂM TRA TRẠNG THÁI TỪ WEB (POLLING)
@app.route('/check-status/<order_id>', methods=['GET'])
def check_status(order_id):
    order = orders.get(order_id)
    if not order:
        return jsonify({"status": "NOT_FOUND"})
    return jsonify({"status": order['status'], "name": order['name']})

@app.route('/', methods=['GET'])
def health_check():
    return "Bot & Server DNS Locket đang hoạt động bình thường 24/7!", 200

# 4. XỬ LÝ NÚT "XÁC NHẬN" TRÊN TELEGRAM
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
            
            # Cập nhật nội dung tin nhắn và MẤT NÚT BẤM (không truyền reply_markup)
            await query.edit_message_text(
                text=(
                    f"✅ **ĐÃ XÁC NHẬN THÀNH CÔNG!**\n\n"
                    f"👤 **Khách hàng:** `{customer_name}`\n"
                    f"🆔 **Mã đơn:** `{order_id}`\n"
                    f"⏰ **Thời gian tạo:** `{created_at}`\n"
                    f"🎯 **Thời gian hoàn thành:** `{completed_at}`\n\n"
                    f"🚀 *Hệ thống đã tự động mở khóa nút Tải File (.mobileconfig) cho khách trên Web!*"
                ),
                parse_mode="Markdown"
            )

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    threading.Thread(target=run_flask).start()
    tg_app = ApplicationBuilder().token(BOT_TOKEN).build()
    tg_app.add_handler(CallbackQueryHandler(button_callback))
    tg_app.run_polling()
