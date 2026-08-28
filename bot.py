import os
import sqlite3
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask, request, jsonify
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ---------------------------------------------------------
# 1. SOZLAMALAR
# ---------------------------------------------------------
BOT_TOKEN = "8363949191:AAHMbK-Ep5XMJtQw2nTKdwfHftkAlKHyFnU" 
WEB_URL = "http://localhost:5000" 

DB_NAME = "xarajatlar.db"
PORT = int(os.environ.get('PORT', 5000))

app = Flask(__name__, static_folder='.', static_url_path='')

# ---------------------------------------------------------
# 2. MA'LUMOTLAR BAZASI
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Har safar toza jadval yaratamiz (test uchun)
    cursor.execute("DROP TABLE IF EXISTS xarajatlar")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS xarajatlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            summa REAL,
            kategoriya TEXT,
            sana TEXT,
            vaqt TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_expense_to_db(user_id, summa, kategoriya):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        now = datetime.now()
        cursor.execute(
            "INSERT INTO xarajatlar (user_id, summa, kategoriya, sana, vaqt) VALUES (?, ?, ?, ?, ?)",
            (user_id, summa, kategoriya, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"))
        )
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        return last_id
    except Exception as e:
        print(f"DB Save Error: {e}")
        return None

def update_expense_in_db(exp_id, user_id, summa, kategoriya):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE xarajatlar SET summa=?, kategoriya=? WHERE id=? AND user_id=?",
            (summa, kategoriya, exp_id, user_id)
        )
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    except Exception as e:
        print(f"DB Update Error: {e}")
        return False

def delete_expense_from_db(exp_id, user_id):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM xarajatlar WHERE id=? AND user_id=?", (exp_id, user_id))
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    except Exception as e:
        print(f"DB Delete Error: {e}")
        return False

def get_statistics_from_db(user_id, period="oy"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    now = datetime.now()
    start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d") if period == "hafta" else now.replace(day=1).strftime("%Y-%m-%d")
    
    # MUHIM: MIN(id) orqali har bir kategoriya uchun bitta ID olamiz
    cursor.execute(
        "SELECT MIN(id), kategoriya, SUM(summa), COUNT(*) FROM xarajatlar WHERE user_id=? AND sana>=? GROUP BY kategoriya ORDER BY SUM(summa) DESC",
        (user_id, start_date)
    )
    results = cursor.fetchall()
    
    cursor.execute("SELECT SUM(summa) FROM xarajatlar WHERE user_id=? AND sana>=?", (user_id, start_date))
    total = cursor.fetchone()[0] or 0
    
    conn.close()
    return results, total

def get_recent_expenses(user_id, limit=20):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, summa, kategoriya, sana, vaqt FROM xarajatlar WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows

# ---------------------------------------------------------
# 3. FUTURISTIK DIZAYN
# ---------------------------------------------------------
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cyber Xarajat</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --bg-color: #050510; --card-bg: rgba(20, 20, 40, 0.7);
            --primary: #00f3ff; --secondary: #bc13fe; --text: #ffffff;
            --glass: rgba(255, 255, 255, 0.05); --danger: #ff2a6d;
        }
        
        body { background-color: var(--bg-color); color: var(--text); font-family: 'Segoe UI', sans-serif; margin: 0; padding: 20px; min-height: 100vh; background-image: radial-gradient(circle at 50% 0%, #1a1a40 0%, #050510 70%); }
        .container { max-width: 450px; margin: 0 auto; }
        h1 { text-align: center; font-size: 28px; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 30px; text-shadow: 0 0 10px var(--primary); }
        
        .card { background: var(--card-bg); backdrop-filter: blur(10px); border: 1px solid rgba(0, 243, 255, 0.2); border-radius: 16px; padding: 20px; margin-bottom: 25px; box-shadow: 0 0 20px rgba(0, 243, 255, 0.05); }
        h3 { margin-top: 0; color: var(--primary); font-size: 18px; border-bottom: 1px solid var(--glass); padding-bottom: 10px; }
        
        input { width: 100%; background: rgba(0,0,0,0.3); border: 1px solid var(--primary); color: white; padding: 12px; border-radius: 8px; font-size: 16px; margin-bottom: 15px; outline: none; box-sizing: border-box; transition: 0.3s; }
        input:focus { box-shadow: 0 0 15px rgba(0, 243, 255, 0.3); }
        
        .cats { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 15px; }
        .cat-btn { background: var(--glass); border: 1px solid rgba(255,255,255,0.1); color: #aaa; padding: 8px 12px; border-radius: 20px; font-size: 13px; cursor: pointer; transition: 0.3s; }
        .cat-btn:hover { border-color: var(--primary); color: white; }
        .cat-btn.active { background: var(--primary); color: black; font-weight: bold; box-shadow: 0 0 10px var(--primary); border-color: var(--primary); }
        
        .btn-main { width: 100%; background: linear-gradient(90deg, var(--secondary), var(--primary)); border: none; padding: 14px; border-radius: 8px; color: white; font-weight: bold; font-size: 16px; cursor: pointer; text-transform: uppercase; letter-spacing: 1px; transition: transform 0.2s; }
        .btn-main:active { transform: scale(0.98); }
        .btn-cancel { background: transparent; border: 1px solid var(--glass); color: #aaa; margin-top: 10px; }
        
        .stats-row { display: flex; gap: 10px; margin-bottom: 15px; }
        .s-btn { flex: 1; background: transparent; border: 1px solid var(--glass); color: white; padding: 8px; border-radius: 6px; cursor: pointer; }
        .s-btn.active { background: var(--primary); color: black; border-color: var(--primary); }
        
        .list-item { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--glass); }
        .item-info { flex: 1; }
        .item-cat { font-size: 12px; opacity: 0.7; }
        .item-sum { font-weight: bold; color: var(--primary); }
        .item-actions { display: flex; gap: 8px; margin-left: 10px; }
        .act-btn { background: var(--glass); border: none; color: white; width: 32px; height: 32px; border-radius: 8px; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 14px; transition: 0.2s; }
        .act-btn.edit:hover { background: var(--primary); color: black; }
        .act-btn.del:hover { background: var(--danger); }
        
        .total-line { font-size: 18px; color: white; font-weight: bold; margin-bottom: 10px; display: block;}
        .toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: var(--primary); color: black; padding: 12px 24px; border-radius: 30px; font-weight: bold; opacity: 0; transition: 0.3s; pointer-events: none; z-index: 1000; }
        .toast.show { opacity: 1; bottom: 40px; }
    </style>
</head>
<body>
    <div class="container">
        <h1> Cyber Xarajat</h1>
        
        <div class="card">
            <h3 id="form-title">Yangi xarajat</h3>
            <input type="hidden" id="edit-id">
            <input type="number" id="amount" placeholder="Summa (so'm)">
            
            <div style="font-size:12px; margin-bottom:5px; opacity:0.7;">Kategoriyani tanlang yoki yozing:</div>
            <div class="cats" id="cat-box">
                <div class="cat-btn" onclick="sel(this,'Ovqat')">️ Ovqat</div>
                <div class="cat-btn" onclick="sel(this,'Transport')">🚗 Transport</div>
                <div class="cat-btn" onclick="sel(this,'Uy')">🏠 Uy</div>
                <div class="cat-btn" onclick="sel(this,'Ko\'ngilochar')"> Ko\'ngilochar</div>
                <div class="cat-btn" onclick="sel(this,'Xarid')">🛒 Xarid</div>
                <div class="cat-btn" onclick="sel(this,'Boshqa')"> Boshqa</div>
            </div>
            <input type="text" id="custom-cat" placeholder="Yoki o'zingiz yozing..." oninput="clearSel()">
            
            <button class="btn-main" id="save-btn" onclick="save()">SAQLASH</button>
            <button class="btn-main btn-cancel" id="cancel-btn" onclick="cancelEdit()" style="display:none;">BEKOR QILISH</button>
        </div>

        <div class="card">
            <h3>Statistika & Ro'yxat</h3>
            <div class="stats-row">
                <button class="s-btn active" id="btn-oy" onclick="loadView('oy')">Oylik</button>
                <button class="s-btn" id="btn-hafta" onclick="loadView('hafta')">Haftalik</button>
            </div>
            <div id="res"><span class="total-line">Jami: 0 so'm</span></div>
        </div>
    </div>
    
    <div id="toast" class="toast">✅ Saqlandi!</div>

    <script>
        const tg = window.Telegram.WebApp; tg.expand();
        let cat = null;
        let currentView = 'oy';
        const uid = tg.initDataUnsafe?.user?.id || 123;

        function sel(el, c) {
            document.querySelectorAll('.cat-btn').forEach(b=>b.classList.remove('active'));
            el.classList.add('active'); cat = c;
            document.getElementById('custom-cat').value = '';
        }
        function clearSel() {
            document.querySelectorAll('.cat-btn').forEach(b=>b.classList.remove('active'));
            cat = document.getElementById('custom-cat').value;
        }
        function showToast(msg) {
            const t = document.getElementById('toast'); t.innerText = msg; t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 2000);
        }

        async function save() {
            const s = document.getElementById('amount').value;
            const eid = document.getElementById('edit-id').value;
            if(!cat) cat = document.getElementById('custom-cat').value;
            if(!s || !cat) return showToast("️ Summa va kategoriyani kiriting!");
            
            const url = eid ? '/api/update' : '/api/save';
            const body = eid 
                ? {id: eid, user_id:uid, summa:s, kategoriya:cat}
                : {user_id:uid, summa:s, kategoriya:cat};

            try {
                await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
                showToast(eid ? "✏️ Yangilandi!" : "✅ Saqlandi!");
                resetForm();
                loadView(currentView);
            } catch(e) { showToast("❌ Xatolik!"); }
        }

        function resetForm() {
            document.getElementById('amount').value = '';
            document.getElementById('custom-cat').value = '';
            document.getElementById('edit-id').value = '';
            document.querySelectorAll('.cat-btn').forEach(b=>b.classList.remove('active'));
            document.getElementById('form-title').innerText = "Yangi xarajat";
            document.getElementById('save-btn').innerText = "SAQLASH";
            document.getElementById('cancel-btn').style.display = "none";
            cat = null;
        }

        function editItem(id, summa, kategoriya) {
            document.getElementById('edit-id').value = id;
            document.getElementById('amount').value = summa;
            
            const customInput = document.getElementById('custom-cat');
            const btns = document.querySelectorAll('.cat-btn');
            let found = false;
            btns.forEach(b => {
                if(b.innerText.includes(kategoriya)) {
                    sel(b, kategoriya); found = true;
                } else { b.classList.remove('active'); }
            });
            
            if(!found) {
                customInput.value = kategoriya;
                cat = kategoriya;
            } else { customInput.value = ''; }

            document.getElementById('form-title').innerText = "Tahrirlash";
            document.getElementById('save-btn').innerText = "YANGILASH";
            document.getElementById('cancel-btn').style.display = "block";
            window.scrollTo({top: 0, behavior: 'smooth'});
        }

        function cancelEdit() { resetForm(); }

        async function deleteItem(id) {
            if(!confirm("Rostdan ham o'chirmoqchimisiz?")) return;
            try {
                await fetch(`/api/delete?id=${id}&user_id=${uid}`, {method:'POST'});
                showToast("🗑️ O'chirildi!");
                loadView(currentView);
            } catch(e) { showToast("❌ Xatolik!"); }
        }

        async function loadView(view) {
            currentView = view;
            document.getElementById('btn-oy').classList.toggle('active', view==='oy');
            document.getElementById('btn-hafta').classList.toggle('active', view==='hafta');
            
            const resDiv = document.getElementById('res');
            resDiv.innerHTML = "<div style='opacity:0.5'>Yuklanmoqda...</div>";

            try {
                const r = await fetch(`/api/stats?user_id=${uid}&period=${view}`);
                const d = await r.json();
                
                let html = `<span class="total-line">Jami: ${d.total.toLocaleString()} so'm</span>`;
                
                // XATOLIK OLDINI OLISH: Massiv mavjudligini tekshirish
                if(d.categories && d.categories.length > 0) {
                    d.categories.forEach(c => {
                        const sum = c[2] || 0;
                        const name = c[1] || "Noma'lum";
                        const cnt = c[3] || 0;
                        const id = c[0] || 0;

                        html += `<div class="list-item">
                            <div class="item-info">
                                <div class="item-sum">${sum.toLocaleString()} so'm</div>
                                <div class="item-cat">${name} (${cnt} ta)</div>
                            </div>
                            <div class="item-actions">
                                <button class="act-btn edit" onclick="editItem(${id}, ${sum}, '${name}')">️</button>
                                <button class="act-btn del" onclick="deleteItem(${id})">️</button>
                            </div>
                        </div>`;
                    });
                } else {
                    html += "<div style='opacity:0.7; text-align:center; padding:10px;'>Bu davrda xarajatlar yo'q.</div>";
                }
                resDiv.innerHTML = html;
            } catch(e) {
                console.error(e);
                resDiv.innerHTML = "<div style='color:var(--danger)'>Ma'lumot yuklashda xatolik!</div>";
            }
        }
        
        loadView('oy');
    </script>
</body>
</html>
"""

# ---------------------------------------------------------
# 4. FLASK ROUTES
# ---------------------------------------------------------
@app.route('/')
def home():
    return HTML_CONTENT

@app.route('/api/save', methods=['POST'])
def api_save():
    data = request.json
    if data.get('user_id') and data.get('summa'):
        save_expense_to_db(data['user_id'], float(data['summa']), data.get('kategoriya','Boshqa'))
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@app.route('/api/update', methods=['POST'])
def api_update():
    data = request.json
    if data.get('id') and data.get('user_id'):
        success = update_expense_in_db(data['id'], data['user_id'], float(data['summa']), data.get('kategoriya'))
        return jsonify({"success": success})
    return jsonify({"success": False}), 400

@app.route('/api/delete', methods=['POST'])
def api_delete():
    eid = request.args.get('id')
    uid = request.args.get('user_id')
    if eid and uid:
        success = delete_expense_from_db(int(eid), int(uid))
        return jsonify({"success": success})
    return jsonify({"success": False}), 400

@app.route('/api/stats', methods=['GET'])
def api_stats():
    uid = request.args.get('user_id')
    p = request.args.get('period', 'oy')
    res, total = get_statistics_from_db(int(uid), p)
    # To'g'ri formatda yuborish: [[id, kat, sum, count], ...]
    cats = [[r[0], r[1], r[2], r[3]] for r in res]
    return jsonify({"total": total, "categories": cats})

# ---------------------------------------------------------
# 5. TELEGRAM BOT LOGIKASI
# ---------------------------------------------------------
# Web App tugmasisiz, faqat matnli klaviatura
keyboard = ReplyKeyboardMarkup([
    [" Statistika", "📜 Ro'yxat"],
    ["💡 Yordam"]
], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *Assalomu alaykum!*\\n\\n"
        "Futuristik Xarajat Bot ishga tushdi.\\n\\n"
        "📱 *Ilovani ochish:*\\n"
        f"`{WEB_URL}`\\n\\n"
        "📝 *Yoki shu yerda yozing:*\\n"
        "`50000 ovqat`"
    )
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=keyboard)

async def handle_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in [" Statistika", "📜 Ro'yxat", " Yordam"]: return

    try:
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Format: `50000 Ovqat`", parse_mode='Markdown', reply_markup=keyboard)
            return
        
        summa = float(parts[0])
        kat = ' '.join(parts[1:]) 
        
        save_expense_to_db(update.message.from_user.id, summa, kat)
        await update.message.reply_text(f"✅ {summa:,.0f} so'm ({kat}) saqlandi!", reply_markup=keyboard)
        
    except ValueError:
        await update.message.reply_text(" Raqam yozing.", reply_markup=keyboard)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    res, total = get_statistics_from_db(uid, "oy")
    
    if not res: txt = "Bu oyda xarajat yo'q."
    else:
        txt = f" *Oylik statistika:*\\n\\n"
        for r in res: txt += f"• {r[1]}: {r[2]:,.0f}\\n"
        txt += f"\\n💰 *Jami:* {total:,.0f} so'm"
        
    await update.message.reply_text(txt, parse_mode='Markdown', reply_markup=keyboard)

async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    rows = get_recent_expenses(uid, 10)
    
    if not rows: txt = " Hali xarajatlar yo'q."
    else:
        txt = " *So'nggi xarajatlar:*\\n\\n"
        for i, r in enumerate(rows, 1):
            txt += f"{i}. {r[2]}: {r[1]:,.0f} so'm ({r[3]} {r[4]})\\n"
            
    await update.message.reply_text(txt, parse_mode='Markdown', reply_markup=keyboard)

# ---------------------------------------------------------
# 6. ASOSIY QISM
# ---------------------------------------------------------
def main():
    init_db()
    
    def run_flask():
        app.run(host='0.0.0.0', port=PORT, use_reloader=False)
    
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print(f" Web server: http://localhost:{PORT}")

    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CommandHandler("royxat", show_list))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expense))
    
    print("🤖 Bot ishga tushdi...")
    application.run_polling()

if __name__ == "__main__":
    main()