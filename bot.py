import os
import io
import uuid
import threading
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes

# ==================== THÔNG TIN CẤU HÌNH BẢO MẬT ====================
# Code tự động lấy biến từ Render, nếu không thấy sẽ dùng giá trị mặc định bên dưới
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8766885663:AAHbYNiInm0R7b3LIMhxoTUwK2NlSjDuDwE").strip()
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "7126654319").strip()

NEXTDNS_ID = "ed4988"
AUTHOR_NAME = "DNS Huy Hiệu"
# =======================================================================

app = Flask(__name__)
CORS(app)  # Cho phép Web HTML trên GitHub Pages gọi API

# Bộ nhớ tạm lưu trữ đơn hàng trong RAM
orders = {}

# 1. API NHẬN YÊU CẦU TẠO ĐƠN TỪ WEB HTML
@app.route('/create-order', methods=['POST'])
def create_order():
    try:
        data = request.json
        name = data.get('name')
        if not name:
            return jsonify({"success": False, "message": "Thiếu tên khách hàng!"}), 400

        # Tạo mã đơn hàng ngắn 8 ký tự
        order_id = str(uuid.uuid4())[:8].upper()

        orders[order_id] = {
            'name': name,
            'status': 'PENDING'
        }

        # Gửi thông báo chuyển khoản về Telegram cho Admin duyệt
        msg = (
            f"🔔 **ĐƠN HÀNG MỚI NÈ!**\n\n"
            f"👤 **Khách hàng:** `{name}`\n"
            f"🆔 **Mã đơn:** `{order_id}`\n"
            f"💵 **Nội dung CK:** `LOCKET {order_id}`\n\n"
            f"👉 *Hãy kiểm tra App Ngân hàng xem đã nhận tiền chưa:* "
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ XÁC NHẬN ĐÃ NHẬN TIỀN", callback_data=f"approve_{order_id}")]
        ])

        # Gọi API Telegram gửi tin nhắn
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": ADMIN_CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown",
                "reply_markup": keyboard.to_dict()
            }
        )

        return jsonify({"success": True, "order_id": order_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 2. API ĐỂ WEB HỎI TRẠNG THÁI (POLLING)
@app.route('/check-status/<order_id>', methods=['GET'])
def check_status(order_id):
    order = orders.get(order_id)
    if not order:
        return jsonify({"status": "NOT_FOUND"})
    return jsonify({"status": order['status'], "name": order['name']})

# API KIỂM TRA BOT CÒN SỐNG KHÔNG (HEALTH CHECK)
@app.route('/', methods=['GET'])
def health_check():
    return "Bot & Server DNS Locket đang hoạt động bình thường 24/7!", 200

# 3. XỬ LÝ NÚT BẤM "XÁC NHẬN" TRÊN TELEGRAM
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("approve_"):
        order_id = query.data.split("_")[1]
        if order_id in orders:
            orders[order_id]['status'] = 'APPROVED'
            customer_name = orders[order_id]['name']
            
            await query.edit_message_text(
                text=(
                    f"✅ **ĐÃ XÁC NHẬN THÀNH CÔNG!**\n\n"
                    f"👤 **Khách hàng:** `{customer_name}`\n"
                    f"🆔 **Mã đơn:** `{order_id}`\n\n"
                    f"🚀 *Hệ thống đã tự động mở khóa nút Tải File (.mobileconfig) cho khách trên Web!*"
                ),
                parse_mode="Markdown"
            )

# HÀM CHẠY FLASK SERVER TRÊN CỔNG CỦA RENDER
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    # Chạy Web Server Flask ở luồng riêng
    threading.Thread(target=run_flask).start()

    # Chạy Telegram Bot ở luồng chính
    tg_app = ApplicationBuilder().token(BOT_TOKEN).build()
    tg_app.add_handler(CallbackQueryHandler(button_callback))
    tg_app.run_polling()
