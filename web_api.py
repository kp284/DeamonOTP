import asyncio, time, secrets, hashlib, json, logging
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Depends, Cookie, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from database import *
import aiohttp

# ============= CONFIG (same as bot) =============
API_ID = 32208414
API_HASH = "628f11c05a44c8dda4b006e66f4bf7df"
BOT_TOKEN = "8671527017:AAGnEOcXU4vXKNSywCXM_A1MjpbJEVpQFd4"
ADMIN_ID = 8640418772
LOG_CHANNEL_ID = -1003970256704
TERMS_URL = "https://golden-sms-ro-bot.vercel.app/"
UPI_ID = "krishpatel284@fam"
UPI_MID = "vbaveF22128686328253"

# ============= FASTAPI APP =============
def create_app(bot_system=None):   # bot_system is optional for message sending
    app = FastAPI(title="Fresh Tg API", version="1.0")
    app.mount("/static", StaticFiles(directory="static"), name="static")
    templates = Jinja2Templates(directory="templates")
    
    # Session middleware (cookie-based)
    app.add_middleware(SessionMiddleware, secret_key="super-secret-key-change-me")

    # ------------------- Helper to get current user from session -----------------
    async def get_current_user(request: Request):
        uid = request.session.get("user_id")
        if not uid:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return uid

    # ------------------- Telegram Login Verification --------------------------
    def verify_telegram_auth(data: dict):
        """Verify Telegram login widget hash using BOT_TOKEN."""
        check_hash = data.get("hash")
        if not check_hash:
            return False
        items = sorted([(k, v) for k, v in data.items() if k != "hash"])
        data_check_string = "\n".join(f"{k}={v}" for k, v in items)
        secret = hashlib.sha256(BOT_TOKEN.encode()).digest()
        hmac_hash = hashlib.sha256(secret + data_check_string.encode()).hexdigest()
        return hmac_hash == check_hash

    # ------------------- Web Routes -------------------
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse("all_pages.html", {"request": request})

    @app.get("/auth/telegram")
    async def telegram_auth(request: Request):
        data = dict(request.query_params)
        if not verify_telegram_auth(data):
            return HTMLResponse("<h1>Invalid Telegram Auth</h1>", status_code=403)
        uid = int(data["id"])
        ensure_user(uid)
        request.session["user_id"] = uid
        return RedirectResponse(url="/#dashboard")

    @app.get("/logout")
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse(url="/")

    # ------------------- Dashboard API (requires login) ------------------------
    @app.get("/api/dashboard")
    async def dashboard_data(request: Request, user_id: int = Depends(get_current_user)):
        profile = get_user_profile(user_id)
        if not profile:
            raise HTTPException(404, "User not found")
        # Fetch API key
        api_key_row = cur.execute("SELECT api_key, secret_key, enabled FROM api_keys WHERE user_id=?", (user_id,)).fetchone()
        # Count orders
        total_orders = cur.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (user_id,)).fetchone()[0]
        total_spent = cur.execute("SELECT SUM(price) FROM orders WHERE user_id=?", (user_id,)).fetchone()[0] or 0
        referral_count = cur.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (user_id,)).fetchone()[0]

        return {
            "user_id": user_id,
            "balance": profile[1],
            "total_deposited": profile[2],
            "joined_date": profile[3],
            "discount": profile[4],
            "banned": profile[5],
            "total_orders": total_orders,
            "total_spent": total_spent,
            "referral_count": referral_count,
            "api_key": api_key_row[0] if api_key_row else None,
            "secret_key": api_key_row[1] if api_key_row else None,
            "api_enabled": api_key_row[2] if api_key_row else False,
            "usdt_rate": get_usdt_rate(),
        }

    @app.post("/api/create-key")
    async def create_api_key(request: Request, user_id: int = Depends(get_current_user)):
        # Check if already exists
        exist = cur.execute("SELECT api_key FROM api_keys WHERE user_id=?", (user_id,)).fetchone()
        if exist:
            raise HTTPException(400, "API key already exists. Reset it if needed.")
        api_key = "ftgu_" + secrets.token_hex(16)
        secret_key = secrets.token_hex(32)
        cur.execute("INSERT OR REPLACE INTO api_keys (user_id, api_key, secret_key) VALUES (?,?,?)", (user_id, api_key, secret_key))
        db.commit()
        return {"api_key": api_key, "secret_key": secret_key}

    @app.post("/api/reset-key")
    async def reset_api_key(request: Request, user_id: int = Depends(get_current_user)):
        api_key = "ftgu_" + secrets.token_hex(16)
        secret_key = secrets.token_hex(32)
        cur.execute("UPDATE api_keys SET api_key=?, secret_key=? WHERE user_id=?", (api_key, secret_key, user_id))
        db.commit()
        return {"api_key": api_key, "secret_key": secret_key}

    # ------------------- REST API (Bearer / ?api_key= ) -------------------------
    async def get_api_user(request: Request):
        # support query param or header
        api_key = request.query_params.get("api_key") or request.headers.get("Authorization", "").replace("Bearer ", "")
        if not api_key:
            raise HTTPException(401, "API key required")
        row = cur.execute("SELECT user_id, enabled FROM api_keys WHERE api_key=?", (api_key,)).fetchone()
        if not row or row[1] == 0:
            raise HTTPException(403, "Invalid or disabled API key")
        # Update last_used and count
        cur.execute("UPDATE api_keys SET last_used=CURRENT_TIMESTAMP, requests_count = requests_count + 1 WHERE api_key=?", (api_key,))
        db.commit()
        return row[0]  # user_id

    def log_api_request(user_id, api_key, endpoint, method, ip, data=""):
        cur.execute("INSERT INTO api_logs (user_id, api_key, endpoint, method, ip, request_data) VALUES (?,?,?,?,?,?)",
                    (user_id, api_key, endpoint, method, ip, data))
        db.commit()

    @app.get("/api/ping")
    async def ping():
        return {"status": "ok", "time": datetime.utcnow().isoformat()}

    @app.get("/api/balance")
    async def api_balance(request: Request, api_user: int = Depends(get_api_user)):
        profile = get_user_profile(api_user)
        return {"user_id": api_user, "balance": profile[1], "usdt_balance": to_usd(profile[1])}

    @app.get("/api/stock")
    async def api_stock(request: Request, country: str = None, year: int = None, api_user: int = Depends(get_api_user)):
        query = "SELECT country_icon, country_name, account_year, price, COUNT(*) FROM stock WHERE available=1"
        params = []
        if country:
            query += " AND country_name LIKE ?"
            params.append(f"%{country}%")
        if year:
            query += " AND account_year = ?"
            params.append(year)
        query += " GROUP BY country_name, account_year, price ORDER BY country_name, account_year DESC"
        rows = cur.execute(query, params).fetchall()
        stock = [{"icon": r[0], "country": r[1], "year": r[2], "price": r[3], "count": r[4]} for r in rows]
        return {"stock": stock}

    @app.get("/api/prices")
    async def api_prices(request: Request, country: str = None, api_user: int = Depends(get_api_user)):
        query = "SELECT DISTINCT country_name, account_year, price FROM stock WHERE available=1"
        params = []
        if country:
            query += " AND country_name LIKE ?"
            params.append(f"%{country}%")
        rows = cur.execute(query, params).fetchall()
        return {"prices": [{"country": r[0], "year": r[1], "price": r[2]} for r in rows]}

    @app.get("/api/countries")
    async def api_countries(api_user: int = Depends(get_api_user)):
        rows = cur.execute("SELECT DISTINCT country_name, country_icon FROM stock WHERE available=1").fetchall()
        return {"countries": [{"name": r[0], "flag": r[1]} for r in rows]}

    @app.get("/api/years")
    async def api_years(country: str, api_user: int = Depends(get_api_user)):
        rows = cur.execute("SELECT DISTINCT account_year FROM stock WHERE available=1 AND country_name LIKE ?", (f"%{country}%",)).fetchall()
        return {"country": country, "years": [r[0] for r in rows]}

    @app.post("/api/buy")
    async def api_buy(request: Request, api_user: int = Depends(get_api_user)):
        data = await request.json()
        country = data.get("country")
        year = int(data.get("year"))
        quantity = int(data.get("quantity", 1))
        # Simple single purchase with locking
        lock = asyncio.Lock()
        async with lock:
            row = cur.execute("SELECT phone, session_file, country_icon, account_year, price, twofa FROM stock WHERE country_name LIKE ? AND account_year=? AND available=1 LIMIT 1", (f"%{country}%", year)).fetchone()
            if not row:
                raise HTTPException(400, "Out of stock")
            phone, sess, c_icon, actual_year, price, twofa_pass = row
            # Check balance
            user_bal = cur.execute("SELECT balance FROM users WHERE user_id=?", (api_user,)).fetchone()[0]
            if user_bal < price:
                raise HTTPException(402, "Insufficient balance")
            # Deduct balance
            cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (price, api_user))
            cur.execute("UPDATE stock SET available=0 WHERE phone=?", (phone,))
            db.commit()
            # OTP fetching would require live client; here we just mark order and return phone
            order_id = f"API_{api_user}_{int(time.time())}"
            cur.execute("INSERT INTO api_orders (order_id, user_id, phone, country, year, price, status, api_key_used) VALUES (?,?,?,?,?,?,?,?)",
                        (order_id, api_user, phone, country, actual_year, price, "waiting", api_user))
            db.commit()
            # Log request
            log_api_request(api_user, "api", "/api/buy", "POST", request.client.host, json.dumps(data))
        return {"order_id": order_id, "phone": phone, "price": price, "country": country, "year": actual_year, "message": "OTP will be available via /api/check-otp"}

    @app.get("/api/check-otp")
    async def api_check_otp(order_id: str, api_user: int = Depends(get_api_user)):
        order = cur.execute("SELECT phone, status, otp FROM api_orders WHERE order_id=? AND user_id=?", (order_id, api_user)).fetchone()
        if not order:
            raise HTTPException(404, "Order not found")
        return {"order_id": order_id, "status": order[1], "otp": order[2] if order[1] == "done" else None}

    @app.post("/api/cancel")
    async def api_cancel(order_id: str, api_user: int = Depends(get_api_user)):
        order = cur.execute("SELECT phone, status, price FROM api_orders WHERE order_id=? AND user_id=?", (order_id, api_user)).fetchone()
        if not order or order[1] != "waiting":
            raise HTTPException(400, "Cannot cancel")
        # Refund
        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (order[2], api_user))
        cur.execute("UPDATE stock SET available=1 WHERE phone=?", (order[0],))
        cur.execute("DELETE FROM api_orders WHERE order_id=?", (order_id,))
        db.commit()
        return {"status": "cancelled", "refunded": order[2]}

    @app.get("/api/order-status")
    async def api_order_status(order_id: str, api_user: int = Depends(get_api_user)):
        order = cur.execute("SELECT status FROM api_orders WHERE order_id=? AND user_id=?", (order_id, api_user)).fetchone()
        if not order:
            raise HTTPException(404, "Order not found")
        return {"order_id": order_id, "status": order[0]}

    @app.get("/api/orders")
    async def api_orders(api_user: int = Depends(get_api_user)):
        orders = cur.execute("SELECT order_id, phone, country, price, status, request_time FROM api_orders WHERE user_id=? ORDER BY request_time DESC LIMIT 50", (api_user,)).fetchall()
        return {"orders": [{"id": r[0], "phone": r[1], "country": r[2], "price": r[3], "status": r[4], "time": r[5]} for r in orders]}

    @app.get("/api/stats")
    async def api_stats(api_user: int = Depends(get_api_user)):
        profile = get_user_profile(api_user)
        total_orders = cur.execute("SELECT COUNT(*) FROM api_orders WHERE user_id=?", (api_user,)).fetchone()[0]
        return {
            "balance": profile[1],
            "total_deposited": profile[2],
            "total_api_orders": total_orders,
        }

    @app.post("/api/deposit")
    async def api_deposit(request: Request, api_user: int = Depends(get_api_user)):
        data = await request.json()
        amount = int(data["amount"])
        method = data.get("method", "API")
        # In a real system, integrate payment gateway. For demo, just simulate.
        # We'll insert a deposit request for admin approval.
        cur.execute("INSERT INTO deposits (user_id, amount, method_name, status) VALUES (?,?,?,'pending')", (api_user, amount, method))
        db.commit()
        dep_id = cur.lastrowid
        # Notify bot admin via log channel? We'll skip here.
        return {"status": "pending", "deposit_id": dep_id, "message": "Deposit request submitted. Awaiting admin approval."}

    @app.post("/api/buy-session")
    async def api_buy_session(request: Request, api_user: int = Depends(get_api_user)):
        data = await request.json()
        country = data["country"]
        year = int(data["year"])
        quantity = int(data.get("quantity", 1))
        # Fetch available sessions
        rows = cur.execute("SELECT phone, session_file, price, twofa FROM stock WHERE country_name LIKE ? AND account_year=? AND available=1 LIMIT ?",
                           (f"%{country}%", year, quantity)).fetchall()
        if len(rows) < quantity:
            raise HTTPException(400, "Not enough stock")
        total_price = sum(r[2] for r in rows)
        user_bal = cur.execute("SELECT balance FROM users WHERE user_id=?", (api_user,)).fetchone()[0]
        if user_bal < total_price:
            raise HTTPException(402, "Insufficient balance")
        # Deduct
        cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (total_price, api_user))
        phones = [r[0] for r in rows]
        placeholders = ",".join("?" for _ in phones)
        cur.execute(f"UPDATE stock SET available=0 WHERE phone IN ({placeholders})", phones)
        for r in rows:
            cur.execute("INSERT INTO api_orders (order_id, user_id, phone, country, year, price, status, api_key_used) VALUES (?,?,?,?,?,?,?,?)",
                        (f"API_{api_user}_{int(time.time())}", api_user, r[0], country, year, r[2], "completed_no_otp", str(api_user)))
        db.commit()
        # Create zip
        zip_name = f"api_sessions_{api_user}_{int(time.time())}.zip"
        with zipfile.ZipFile(zip_name, 'w') as zf:
            for phone, sess, price, twofa in rows:
                base = sess if not sess.endswith('.session') else sess[:-8]
                for ext in ['.session', '.session-wal', '.session-shm', '.session-journal']:
                    src = base + ext
                    if os.path.exists(src):
                        zf.write(src, os.path.basename(src))
        with open(zip_name, 'rb') as f:
            content = f.read()
        os.remove(zip_name)
        return Response(content=content, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={zip_name}"})

    # ------------------- Admin API (session required) ------------------------
    @app.get("/admin/api-users")
    async def admin_api_users(request: Request):
        uid = request.session.get("user_id")
        if not uid or not is_admin(uid):
            raise HTTPException(403)
        users = cur.execute("SELECT user_id, api_key, enabled, requests_count, last_used FROM api_keys").fetchall()
        return {"api_users": [{"user_id": r[0], "api_key": r[1], "enabled": r[2], "requests": r[3], "last_used": r[4]} for r in users]}

    @app.get("/admin/api-logs")
    async def admin_api_logs(request: Request):
        uid = request.session.get("user_id")
        if not uid or not is_admin(uid):
            raise HTTPException(403)
        logs = cur.execute("SELECT user_id, endpoint, method, ip, timestamp, response_status FROM api_logs ORDER BY timestamp DESC LIMIT 100").fetchall()
        return {"logs": [{"user_id": r[0], "endpoint": r[1], "method": r[2], "ip": r[3], "time": r[4], "status": r[5]} for r in logs]}

    @app.post("/admin/disable-key")
    async def admin_disable_key(request: Request):
        uid = request.session.get("user_id")
        if not uid or not is_admin(uid):
            raise HTTPException(403)
        data = await request.json()
        target = data["user_id"]
        cur.execute("UPDATE api_keys SET enabled=0 WHERE user_id=?", (target,))
        db.commit()
        return {"status": "disabled"}

    @app.post("/admin/enable-key")
    async def admin_enable_key(request: Request):
        uid = request.session.get("user_id")
        if not uid or not is_admin(uid):
            raise HTTPException(403)
        data = await request.json()
        target = data["user_id"]
        cur.execute("UPDATE api_keys SET enabled=1 WHERE user_id=?", (target,))
        db.commit()
        return {"status": "enabled"}

    return app