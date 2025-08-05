from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import logging
import csv
import io
import json

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'a_very_secure_random_key_change_me')

# Database connection function for PostgreSQL
def get_db_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    result = urlparse(database_url)
    conn = psycopg2.connect(
        database=result.path[1:],  # Remove leading '/'
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        cursor_factory=RealDictCursor,
        sslmode="require"  # Render requires SSL for PostgreSQL
    )
    return conn
# Initialize the database with tables
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_out (
            id SERIAL PRIMARY KEY,
            date TEXT,
            branch TEXT,
            product TEXT,
            quantity_out INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS business_entries (
            id SERIAL PRIMARY KEY,
            branch TEXT,
            date TEXT,
            opening_cash REAL,
            sales REAL,
            paid REAL,
            bank REAL,
            debt_opening REAL,
            debt_given REAL,
            debt_paid REAL,
            cumulative_opening REAL,
            cumulative_sales REAL,
            cumulative_closing REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            branch TEXT,
            date TEXT,
            content TEXT
        )
    ''')
    conn.commit()
    conn.close()
    logging.info("Database initialized")

init_db()

branches = {
    "Admin": generate_password_hash("pass123"),
    "Banda depot": generate_password_hash("banda789"),
    "Jinja road showroom": generate_password_hash("jinja456"),
    "Kabalagala showroom": generate_password_hash("kaba123"),
    "Rubaga showroom": generate_password_hash("rubaga321"),
    "Kawempe depot": generate_password_hash("kawempe654"),
    "Gayaza depot": generate_password_hash("gayaza987"),
    "Natete depot": generate_password_hash("natete111"),
    "Bulenga depot": generate_password_hash("bulenga222"),
    "Bulaga depot": generate_password_hash("bulaga333"),
    "Najjera depot": generate_password_hash("najjera444"),
    "Fortportal depot": generate_password_hash("fortportal555"),
    "Mbarara showroom": generate_password_hash("mbarara666"),
    "Arua depot": generate_password_hash("arua777"),
    "Channel street": generate_password_hash("street345"),
    "Factory outlet": generate_password_hash("outlet145"),
    "Gulu": generate_password_hash("gulu897"),
    "Hoima": generate_password_hash("oima456"),
    "Kyengera": generate_password_hash("gera098"),
    "Lira": generate_password_hash("lira267"),
    "Masaka": generate_password_hash("saka775"),
    "Mbale": generate_password_hash("bale354"),
    "Nansana": generate_password_hash("sana129"),
    "Lugogo": generate_password_hash("gog551")
}

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        branch = request.form['branch']
        password = request.form['password']
        if branch in branches and check_password_hash(branches[branch], password):
            session['branch'] = branch
            logging.info(f"User logged in: {branch}")
            if branch == "Admin":
                return redirect(url_for('admin'))
            return redirect(url_for('stock'))
        return render_template('index.html', error="Invalid branch or password", branches=branches)
    return render_template('index.html', branches=branches)

@app.route('/stock')
def stock():
    if 'branch' not in session:
        return redirect(url_for('login'))

    branch = session['branch']
    premium_stock = [
        "Bonel single layer", "Bonel double layer", "Bonluxe", "Bonvisco", "Bonnex",
        "Pocket Spring", "Pocket hybrid", "Pocket hybrid extra firm", "High density",
        "Fit slip", "Orthopaedic", "Fibre pillow"
    ]
    standard_stock = [
        "Deluxe", "Deluxe quitted", "Tape edge c", "Pvc",
        "1foam sheet", "Ordinary pillow"
    ]

    return render_template(
        'stock.html',
        branch=branch,
        premium_stock=premium_stock,
        standard_stock=standard_stock
    )

@app.route('/admin')
def admin():
    if 'branch' not in session or session['branch'] != "Admin":
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Stock Entries
    cursor.execute("SELECT DISTINCT branch FROM stock_out")
    branches = cursor.fetchall()
    stock_data_by_branch = {}
    for branch in branches:
        branch_name = branch['branch']
        cursor.execute(
            "SELECT id, date, product, SUM(quantity_out) AS quantity_out FROM stock_out WHERE branch = %s GROUP BY id, date, product ORDER BY date DESC",
            (branch_name,)
        )
        stock_data_by_branch[branch_name] = cursor.fetchall()

    # Business Entries
    cursor.execute('''
        SELECT id, branch, date, opening_cash, sales, paid, bank,
               debt_opening, debt_given, debt_paid,
               cumulative_opening, cumulative_sales, cumulative_closing
        FROM business_entries
        ORDER BY branch, date DESC
    ''')
    business_entries_raw = cursor.fetchall()
    business_entries = []
    for entry in business_entries_raw:
        entry_dict = dict(entry)
        entry_dict['closing_balance'] = entry_dict['opening_cash'] + entry_dict['sales'] - entry_dict['paid'] - entry_dict['bank']
        entry_dict['debt_closing'] = entry_dict['debt_opening'] + entry_dict['debt_given'] - entry_dict['debt_paid']
        business_entries.append(entry_dict)

    # Chart Data: Product totals per branch
    cursor.execute("SELECT product, branch, SUM(quantity_out) AS total FROM stock_out GROUP BY product, branch")
    chart_rows = cursor.fetchall()
    chart_data = {}
    product_totals = {}
    for row in chart_rows:
        product = row['product']
        branch = row['branch']
        total = row['total']
        if product not in chart_data:
            chart_data[product] = {}
            product_totals[product] = {}
        chart_data[product][branch] = total
        product_totals[product][branch] = total

    # Calculate top selling branch per product
    top_selling_branches = {}
    for product, totals in product_totals.items():
        if totals:
            top_branch = max(totals, key=totals.get)
            top_selling_branches[product] = {
                'branch': top_branch,
                'total': totals[top_branch]
            }

    # Messages
    cursor.execute("SELECT branch, date, content FROM messages ORDER BY date DESC")
    messages = cursor.fetchall()

    conn.close()
    return render_template(
        'admin.html',
        stock_data_by_branch=stock_data_by_branch,
        business_entries=business_entries,
        chart_data=chart_data,
        top_selling_branches=top_selling_branches,
        messages=messages
    )

@app.route('/logout')
def logout():
    session.pop('branch', None)
    logging.info("User logged out")
    return redirect(url_for('login'))

@app.route('/update_stock', methods=['POST'])
def update_stock():
    if 'branch' not in session:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    branch = session['branch']
    product = data['product']
    quantity_out = int(data['quantityOut'])
    date = data['date']

    if not date or quantity_out < 0:
        logging.warning(f"Invalid input: date={date}, quantity_out={quantity_out}")
        return jsonify({'error': 'Invalid date or negative quantity'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT quantity_out FROM stock_out WHERE branch = %s AND product = %s AND date = %s",
            (branch, product, date)
        )
        existing_record = cursor.fetchone()

        if existing_record:
            new_quantity = existing_record['quantity_out'] + quantity_out
            cursor.execute(
                "UPDATE stock_out SET quantity_out = %s WHERE branch = %s AND product = %s AND date = %s",
                (new_quantity, branch, product, date)
            )
            logging.info(f"Updated stock: {product}, {date}, new qty={new_quantity}")
        else:
            cursor.execute(
                "INSERT INTO stock_out (date, branch, product, quantity_out) VALUES (%s, %s, %s, %s)",
                (date, branch, product, quantity_out)
            )
            logging.info(f"Inserted stock: {product}, {date}, qty={quantity_out}")

        conn.commit()
        conn.close()
        return jsonify({'message': f"Stock updated for {product} on {date}."})
    except psycopg2.Error as e:
        logging.error(f"Database error in update_stock: {str(e)}")
        return jsonify({'error': f"Failed to update stock: {str(e)}"}), 500

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'branch' not in session:
        return jsonify({'error': 'Unauthorized'}), 403

    branch = session['branch']
    data = request.json
    message_content = data.get('message')
    date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if not message_content:
        return jsonify({'error': 'Message content cannot be empty'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (branch, date, content) VALUES (%s, %s, %s)",
            (branch, date, message_content)
        )
        conn.commit()
        conn.close()
        logging.info(f"Message sent from {branch} at {date}")
        return jsonify({'success': True, 'message': 'Message sent successfully'})
    except psycopg2.Error as e:
        logging.error(f"Database error in send_message: {str(e)}")
        return jsonify({'error': f"Failed to send message: {str(e)}"}), 500

@app.route('/delete_stock/<int:stock_id>', methods=['POST'])
def delete_stock(stock_id):
    if 'branch' not in session or session['branch'] != "Admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    data = request.json
    qty_to_delete = data.get('quantity')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT quantity_out FROM stock_out WHERE id = %s", (stock_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"success": False, "message": "Stock item not found"}), 404

    current_qty = row['quantity_out']
    if qty_to_delete > current_qty:
        conn.close()
        return jsonify({"success": False, "message": "Not enough stock available"}), 400

    new_qty = current_qty - qty_to_delete
    if new_qty > 0:
        cursor.execute("UPDATE stock_out SET quantity_out = %s WHERE id = %s", (new_qty, stock_id))
        logging.info(f"Admin partially deleted stock ID {stock_id}, new qty={new_qty}")
    else:
        cursor.execute("DELETE FROM stock_out WHERE id = %s", (stock_id,))
        logging.info(f"Admin fully deleted stock ID {stock_id}")

    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"Deleted {qty_to_delete} units from stock ID {stock_id}. New quantity: {new_qty}"})

@app.route('/report')
def report():
    if 'branch' not in session:
        return redirect(url_for('login'))

    branch = session['branch']
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date, product, SUM(quantity_out) AS total_quantity
            FROM stock_out
            WHERE branch = %s
            GROUP BY date, product
            ORDER BY date DESC
            """,
            (branch,)
        )
        stock_data = cursor.fetchall()
        conn.close()
        logging.info(f"Fetched {len(stock_data)} stock records for {branch}")
        return render_template('report.html', branch=branch, stock_data=stock_data)
    except psycopg2.Error as e:
        logging.error(f"Database error in report: {str(e)}")
        return render_template('report.html', branch=branch, stock_data=[], error=f"Database error: {str(e)}")

@app.route('/entry_form')
def entry_form():
    if 'branch' not in session:
        return redirect(url_for('login'))
    return render_template('entry_form.html', branch=session['branch'])

@app.route('/submit_entry', methods=['POST'])
def submit_entry():
    if 'branch' not in session:
        return redirect(url_for('login'))

    branch = session['branch']
    date = request.form.get('date')

    if not date:
        logging.warning("No date provided, using current date as fallback")
        date = datetime.now().strftime('%Y-%m-%d')

    try:
        opening_cash = float(request.form.get('opening_cash', 0))
        sales = float(request.form.get('sales', 0))
        paid = float(request.form.get('paid', 0))
        bank = float(request.form.get('bank', 0))
        debt_opening = float(request.form.get('debt_opening', 0))
        debt_given = float(request.form.get('debt_given', 0))
        debt_paid = float(request.form.get('debt_paid', 0))
        cumulative_opening = float(request.form.get('cumulative_opening', 0))
        cumulative_sales = float(request.form.get('cumulative_sales', 0))
        cumulative_closing = float(request.form.get('cumulative_closing', 0))
    except ValueError:
        return render_template('entry_form.html', error="Invalid numeric input", branch=branch)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO business_entries (
                branch, date, opening_cash, sales, paid, bank,
                debt_opening, debt_given, debt_paid,
                cumulative_opening, cumulative_sales, cumulative_closing
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            branch, date, opening_cash, sales, paid, bank,
            debt_opening, debt_given, debt_paid,
            cumulative_opening, cumulative_sales, cumulative_closing
        ))
        conn.commit()
        conn.close()
        logging.info(f"Business entry submitted for {branch} on {date}")
    except psycopg2.Error as e:
        logging.error(f"Database error in submit_entry: {str(e)}")
        return render_template('entry_form.html', error=f"Database error: {str(e)}", branch=branch)

    return redirect(url_for('business_report'))

@app.route('/business_report')
def business_report():
    if 'branch' not in session:
        return redirect(url_for('login'))

    branch = session['branch']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT branch, date, opening_cash, sales, paid, bank,
               debt_opening, debt_given, debt_paid,
               cumulative_opening, cumulative_sales, cumulative_closing
        FROM business_entries
        WHERE branch = %s
        ORDER BY date DESC
    ''', (branch,))
    entries_raw = cursor.fetchall()
    conn.close()

    entries = []
    for entry in entries_raw:
        entry_dict = dict(entry)
        entry_dict['closing_balance'] = entry_dict['opening_cash'] + entry_dict['sales'] - entry_dict['paid'] - entry_dict['bank']
        entry_dict['debt_closing'] = entry_dict['debt_opening'] + entry_dict['debt_given'] - entry_dict['debt_paid']
        entries.append(entry_dict)

    return render_template('business_report.html', entries=entries)

@app.route('/admin_business_report')
def admin_business_report():
    if 'branch' not in session or session['branch'] != "Admin":
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT branch, date, opening_cash, sales, paid, bank,
               debt_opening, debt_given, debt_paid,
               cumulative_opening, cumulative_sales, cumulative_closing
        FROM business_entries
        ORDER BY branch, date DESC
    ''')
    entries_raw = cursor.fetchall()
    conn.close()

    entries = []
    for entry in entries_raw:
        entry_dict = dict(entry)
        entry_dict['closing_balance'] = entry_dict['opening_cash'] + entry_dict['sales'] - entry_dict['paid'] - entry_dict['bank']
        entry_dict['debt_closing'] = entry_dict['debt_opening'] + entry_dict['debt_given'] - entry_dict['debt_paid']
        entries.append(entry_dict)

    return render_template('business_report.html', entries=entries)

@app.route('/delete_business_entry/<int:entry_id>', methods=['POST'])
def delete_business_entry(entry_id):
    if 'branch' not in session or session['branch'] != "Admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM business_entries WHERE id = %s", (entry_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"success": False, "message": "Business entry not found"}), 404

    cursor.execute("DELETE FROM business_entries WHERE id = %s", (entry_id,))
    conn.commit()
    conn.close()
    logging.info(f"Admin deleted business entry ID {entry_id}")
    return jsonify({"success": True, "message": "Business entry deleted successfully"})

@app.route('/edit_business_entry/<int:entry_id>', methods=['POST'])
def edit_business_entry(entry_id):
    if 'branch' not in session or session['branch'] != "Admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    data = request.json
    date = data.get('date')
    branch = data.get('branch')

    try:
        opening_cash = float(data.get('opening_cash', 0))
        sales = float(data.get('sales', 0))
        paid = float(data.get('paid', 0))
        bank = float(data.get('bank', 0))
        debt_opening = float(data.get('debt_opening', 0))
        debt_given = float(data.get('debt_given', 0))
        debt_paid = float(data.get('debt_paid', 0))
        cumulative_opening = float(data.get('cumulative_opening', 0))
        cumulative_sales = float(data.get('cumulative_sales', 0))
        cumulative_closing = float(data.get('cumulative_closing', 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid numeric input"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM business_entries WHERE id = %s", (entry_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"success": False, "message": "Business entry not found"}), 404

    cursor.execute('''
        UPDATE business_entries SET
            date = %s, branch = %s, opening_cash = %s, sales = %s, paid = %s, bank = %s,
            debt_opening = %s, debt_given = %s, debt_paid = %s,
            cumulative_opening = %s, cumulative_sales = %s, cumulative_closing = %s
        WHERE id = %s
    ''', (
        date, branch, opening_cash, sales, paid, bank,
        debt_opening, debt_given, debt_paid,
        cumulative_opening, cumulative_sales, cumulative_closing,
        entry_id
    ))
    conn.commit()
    conn.close()
    logging.info(f"Admin edited business entry ID {entry_id}")
    return jsonify({"success": True, "message": "Business entry updated successfully"})

@app.route('/download_stock_csv')
def download_stock_csv():
    if 'branch' not in session or session['branch'] != "Admin":
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, date, branch, product, quantity_out FROM stock_out ORDER BY branch, date DESC")
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Date', 'Branch', 'Product', 'Quantity Out'])
    for row in rows:
        writer.writerow([row['id'], row['date'], row['branch'], row['product'], row['quantity_out']])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"stock_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )

@app.route('/download_business_csv')
def download_business_csv():
    if 'branch' not in session or session['branch'] != "Admin":
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, branch, date, opening_cash, sales, paid, bank,
               debt_opening, debt_given, debt_paid,
               cumulative_opening, cumulative_sales, cumulative_closing
        FROM business_entries
        ORDER BY branch, date DESC
    ''')
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'ID', 'Branch', 'Date', 'Opening Cash', 'Sales', 'Paid', 'Bank',
        'Opening Debt', 'Debt Given', 'Debt Paid',
        'Cumulative Opening', 'Cumulative Sales', 'Cumulative Closing',
        'Closing Balance', 'Debt Closing'
    ])
    for row in rows:
        closing_balance = row['opening_cash'] + row['sales'] - row['paid'] - row['bank']
        debt_closing = row['debt_opening'] + row['debt_given'] - row['debt_paid']
        writer.writerow([
            row['id'], row['branch'], row['date'], row['opening_cash'], row['sales'],
            row['paid'], row['bank'], row['debt_opening'], row['debt_given'],
            row['debt_paid'], row['cumulative_opening'], row['cumulative_sales'],
            row['cumulative_closing'], closing_balance, debt_closing
        ])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"business_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)

