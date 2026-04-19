from flask import Flask, jsonify
import mysql.connector
from flask_cors import CORS
from flask import request
import random
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import json
import os


app = Flask(__name__)
CORS(app)



def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT"))
    )

@app.route('/')
def home():
    return "Server Working"

@app.route('/products')
def get_products():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products")
    data = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(data)


@app.route('/recommend', methods=['POST'])
def recommend():
    data = request.get_json()
    cart_items = data.get("items", [])

    if not cart_items:
        return jsonify([])

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    scored_recs = []

    # Step 1: Collect all consequents with confidence/lift
    for item in cart_items:
        query = """
        SELECT consequents, confidence, lift
        FROM association_rules
        WHERE FIND_IN_SET(%s, antecedents)
          AND confidence >= 0.7
          AND lift >= 2.0
        """
        cursor.execute(query, (item.capitalize(),))
        results = cursor.fetchall()

        for row in results:
            for consequent in row['consequents'].split(','):
                scored_recs.append({
                    "name": consequent.strip(),
                    "confidence": row['confidence'],
                    "lift": row['lift']
                })

    cursor.close()
    conn.close()

    # Step 2: Deduplicate by name, keep strongest score
    best_recs = {}
    for rec in scored_recs:
        name = rec['name']
        if name not in best_recs or (
            rec['confidence'] > best_recs[name]['confidence'] or
            rec['lift'] > best_recs[name]['lift']
        ):
            best_recs[name] = rec

    # Step 3: Sort globally by confidence/lift
    sorted_recs = sorted(
        best_recs.values(),
        key=lambda x: (x['confidence'], x['lift']),
        reverse=True
    )

    # Step 4: Limit globally (e.g., top 4 overall)
    top_recs = [rec['name'] for rec in sorted_recs[:4]]

    # Step 5: Fetch product details from DB
    if top_recs:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        placeholders = ','.join(['%s'] * len(top_recs))
        product_query = f"""
        SELECT id, name, description, price, image
        FROM products
        WHERE name IN ({placeholders})
        """
        cursor.execute(product_query, tuple(top_recs))
        recommended_products = cursor.fetchall()
        cursor.close()
        conn.close()
    else:
        recommended_products = []
        

    return jsonify(recommended_products)

import random
from datetime import datetime

@app.route('/send-otp', methods=['POST'])
def send_otp():
    data = request.get_json()
    email = data.get('email')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 🔥 CHECK IF EMAIL ALREADY EXISTS
    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    existing = cursor.fetchone()

    if existing:
        cursor.close()
        conn.close()
        return jsonify({"message": "Email already registered"}), 400

    # 🔥 GENERATE OTP
    otp = str(random.randint(1000, 9999))

    # 🔥 DELETE OLD OTP
    cursor.execute("DELETE FROM otp_verification WHERE email=%s", (email,))

    # 🔥 INSERT NEW OTP
    cursor.execute(
        "INSERT INTO otp_verification (email, otp, created_at) VALUES (%s, %s, %s)",
        (email, otp, datetime.now())
    )

    conn.commit()
    cursor.close()
    conn.close()

    # 🔥 SEND EMAIL
    send_email_otp(email, otp)

    return jsonify({"message": "OTP sent successfully"})

@app.route('/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    name = data.get('name')
    password = data.get('password')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 🔥 Check OTP
    cursor.execute(
        "SELECT * FROM otp_verification WHERE email=%s AND otp=%s",
        (email, otp)
    )
    result = cursor.fetchone()

    if not result:
        cursor.close()
        conn.close()
        return jsonify({"message": "Invalid OTP"}), 400

    # 🔥 Check existing user
    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    existing = cursor.fetchone()

    if existing:
        cursor.close()
        conn.close()
        return jsonify({"message": "Email already registered"}), 400

    # 🔥 Insert user
    cursor.execute(
        "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
        (name, email, password)
    )
    cursor.execute("DELETE FROM otp_verification WHERE email=%s", (email,))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Registration successful"})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM users WHERE email=%s AND password=%s",
        (email, password)
    )

    user = cursor.fetchone()
    
    cursor.close()
    conn.close()

    if user:
        return jsonify({
            "message": "Login successful",
            "user_id": user['id'],
            "name": user['name'],
            "email": user['email']
            })
    else:
        return jsonify({"message": "Invalid credentials"}), 401

def send_email_otp(to_email, otp):
    sender_email = os.getenv("EMAIL_USER")
    app_password = os.getenv("EMAIL_PASS")

    subject = "🔐 Your OTP for Glosory Account Verification"
    body =f""" 
Hello,

Thank you for registering with Glosory 🛒

Your One-Time Password (OTP) is:

👉 {otp}

This OTP is valid for a limited time. Please do not share it with anyone.

If you did not request this, please ignore this email.

Regards,
Glosory Team
"""

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = to_email

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
        print("OTP sent to email")
    except Exception as e:
        print("Error:", e)

from flask import request, jsonify
import json

@app.route('/place-order', methods=['POST'])
def place_order():
    data = request.get_json()
    user_email = data.get('email')
    user_id = data.get('user_id')
    items = data.get('items', [])        # expected: list of { id, name, quantity, price }
    total = data.get('total')
    log_id = data.get('log_id')          # optional, sent from frontend/localStorage

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Start transaction
        conn.start_transaction()

        # 1) insert transaction
        cursor.execute(
            "INSERT INTO transactions (user_id, user_email, total_amount) VALUES (%s, %s, %s)",
            (user_id, user_email, total)
        )
        transaction_id = cursor.lastrowid

        # 2) insert transaction items
        for item in items:
            cursor.execute(
                "INSERT INTO transaction_items (transaction_id, product_id, quantity) VALUES (%s, %s, %s)",
                (transaction_id, item.get('id'), item.get('quantity', 1))
            )

        # 3) If log_id provided, validate ownership and update recommendation_logs
        log_updated = False
        if log_id:
            # Verify the log exists and belongs to this user (prevents tampering)
            cursor.execute(
                "SELECT user_id FROM recommendation_logs WHERE log_id = %s",
                (log_id,)
            )
            row = cursor.fetchone()
            if row:
                log_user_id = row[0]
                # If user_id is provided, ensure it matches the log's user_id
                if user_id is None or int(log_user_id) == int(user_id):
                    # Build purchased_item as names-only array
                    purchased_names = [i.get('name') for i in items if i.get('name')]
                    cursor.execute("""
                        UPDATE recommendation_logs
                        SET order_id = %s,
                            purchased_item = %s
                        WHERE log_id = %s
                    """, (
                        transaction_id,
                        json.dumps(purchased_names),
                        log_id
                    ))
                    log_updated = cursor.rowcount > 0
                else:
                    # Ownership mismatch: do not update the log
                    log_updated = False
            else:
                # log_id not found
                log_updated = False

        # Commit all DB changes
        conn.commit()

    except Exception as e:
        # Rollback on error
        conn.rollback()
        cursor.close()
        conn.close()
        # Log the error server-side as needed
        return jsonify({"error": "Failed to place order", "details": str(e)}), 500

    finally:
        cursor.close()
        conn.close()

    # Send confirmation email (outside DB transaction)
    try:
        send_order_email(user_email, total)
    except Exception:
        # Email failure should not break the order; log server-side if needed
        pass

    return jsonify({
        "message": "Order placed successfully",
        "transaction_id": transaction_id,
        "recommendation_log_updated": log_updated
    })

def send_order_email(to_email, total):
    import smtplib
    from email.mime.text import MIMEText

    sender_email = os.getenv("EMAIL_USER")
    app_password = os.getenv("EMAIL_PASS")


    subject = "🛒 Order Confirmed - Glosory"

    body = f"""
Hello,

Your order has been placed successfully 🎉

💰 Total Amount: ₹{total}

Thank you for shopping with Glosory 🛒

Regards,
Glosory Team
"""

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = to_email

    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.login(sender_email, app_password)
    server.send_message(msg)
    server.quit()

@app.route('/my-orders', methods=['POST'])
def my_orders():
    data = request.get_json()

    conn = get_db_connection()  # ✅ FIX
    cursor = conn.cursor(dictionary=True)

    user_id = int(data['user_id'])

    cursor.execute("""
        SELECT * FROM transactions 
        WHERE user_id=%s 
        ORDER BY id DESC
    """, (user_id,))

    orders = cursor.fetchall()

    result = []

    for order in orders:
        transaction_id = order['id']

        cursor.execute("""
            SELECT p.name, ti.quantity
            FROM transaction_items ti
            JOIN products p ON ti.product_id = p.id
            WHERE ti.transaction_id=%s
        """, (transaction_id,))

        items = cursor.fetchall()

        result.append({
            "order_id": transaction_id,
            "date": order['transaction_date'],
            "total": order['total_amount'],
            "items": items
        })

    cursor.close()
    conn.close()

    return jsonify(result)

@app.route('/log-recommendation', methods=['POST'])
def log_recommendation():
    data = request.get_json()
    user_id = data.get('user_id')
    cart_items = data.get('cart_items', [])           # ["Apples","Yogurt"]
    recommended_items = data.get('recommended_items', [])
    clicked_item = data.get('clicked_item')           # "Apples" or None

    conn = get_db_connection()
    cursor = conn.cursor()
    import json

    cursor.execute("""
        INSERT INTO recommendation_logs (user_id, cart_items, recommended_items, clicked_item)
        VALUES (%s, %s, %s, %s)
    """, (
        user_id,
        json.dumps(cart_items),
        json.dumps(recommended_items),
        clicked_item
    ))
    log_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Recommendation log created", "log_id": log_id})

from flask import request, jsonify

@app.route('/recommendation-log/<int:log_id>', methods=['DELETE'])
def delete_recommendation_log_by_id(log_id):
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')  # optional ownership check

    if not log_id:
        return jsonify({"error": "log_id required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Optional ownership check
        if user_id is not None:
            cursor.execute(
                "SELECT user_id FROM recommendation_logs WHERE log_id = %s",
                (log_id,)
            )
            row = cursor.fetchone()
            if not row:
                cursor.close()
                conn.close()
                return jsonify({"message": "Log not found"}), 404
            if int(row[0]) != int(user_id):
                cursor.close()
                conn.close()
                return jsonify({"error": "Unauthorized to delete this log"}), 403

        # Delete the row
        cursor.execute(
            "DELETE FROM recommendation_logs WHERE log_id = %s",
            (log_id,)
        )
        deleted = cursor.rowcount
        conn.commit()
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({"error": "Failed to delete log", "details": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

    if deleted:
        return jsonify({"message": "Recommendation log deleted", "log_id": log_id})
    else:
        return jsonify({"message": "Log not found or already deleted"}), 404
    
@app.route('/api/recommendation-eval/metrics')
def get_metrics():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # total logs
    cursor.execute("SELECT COUNT(*) as total FROM recommendation_logs")
    total = cursor.fetchone()['total']

    # clicked logs
    cursor.execute("""
        SELECT COUNT(*) as clicked 
        FROM recommendation_logs 
        WHERE clicked_item IS NOT NULL
    """)
    clicked = cursor.fetchone()['clicked']

    # converted logs (order placed)
    cursor.execute("""
        SELECT COUNT(*) as converted 
        FROM recommendation_logs 
        WHERE order_id IS NOT NULL
    """)
    converted = cursor.fetchone()['converted']

    # top purchased items
    cursor.execute("""
        SELECT purchased_item as name, COUNT(*) as count
        FROM recommendation_logs
        WHERE purchased_item IS NOT NULL
        GROUP BY purchased_item
        ORDER BY count DESC
        LIMIT 5
    """)
    top_items = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify({
        "total_logs": total,
        "ctr": clicked / total if total else 0,
        "conversion_rate": converted / total if total else 0,
        "avg_time_to_purchase_seconds": 0,  # optional
        "top_shown": top_items
    })
@app.route('/api/recommendation-eval/logs')
def get_logs():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM recommendation_logs
        ORDER BY log_id DESC
        LIMIT 50
    """)

    logs = cursor.fetchall()

    import json
    for log in logs:
        try:
            log['cart_items'] = json.loads(log['cart_items'])
        except Exception:
            log['cart_items']=log['cart_items'].split(',')

        try:
            log['recommended_items'] = json.loads(log['recommended_items'])
        except Exception:
            log['recommended_items']=log['recommended_items'].split(',')

    cursor.close()
    conn.close()

    return jsonify({"logs": logs})


if __name__ == '__main__':
    port=int(os.environ.get("PORT",5001))
    app.run(host='0.0.0.0', port=port)
