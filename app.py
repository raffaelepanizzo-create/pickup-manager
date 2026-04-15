from flask import Flask, render_template, request, redirect, url_for, flash
import pandas as pd
import os
import sqlite3
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "pickup_secret_key"

UPLOAD_FOLDER = "uploads"
DB_PATH = "pickup.db"
CAPACITY = 55

ALLOWED_EXTENSIONS = {"xlsx", "xls"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─── DATABASE ─────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                upload_datetime TEXT,
                ref_date TEXT,
                num_inserted INTEGER,
                filename TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pickup_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_date TEXT,
                stay_date TEXT,
                rns INTEGER,
                adr REAL,
                revenue REAL
            )
        """)
        conn.commit()

init_db()

# ─── HELPERS ─────────────────────────────────────────────

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_data_for_date(ref_date_str):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT stay_date, rns, adr, revenue FROM pickup_data WHERE ref_date=? ORDER BY stay_date",
            (ref_date_str,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_available_ref_dates():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT ref_date FROM pickup_data ORDER BY ref_date DESC"
        ).fetchall()
        return [r["ref_date"] for r in rows]

def calc_occ(rns):
    return round((rns / CAPACITY) * 100, 2) if CAPACITY > 0 else 0

def calc_revpar(revenue):
    return round(revenue / CAPACITY, 2) if CAPACITY > 0 else 0

def build_table(data):
    rows = []
    total_rns = 0
    total_rev = 0

    for d in data:
        rns = d["rns"] or 0
        rev = d["revenue"] or 0
        adr = d["adr"] or 0

        total_rns += rns
        total_rev += rev

        rows.append({
            "date": d["stay_date"],
            "rns": rns,
            "adr": adr,
            "revenue": rev,
            "occ": calc_occ(rns),
            "revpar": calc_revpar(rev),
        })

    total_adr = round(total_rev / total_rns, 2) if total_rns > 0 else 0

    rows.append({
        "date": "Totale",
        "rns": total_rns,
        "adr": total_adr,
        "revenue": total_rev,
        "occ": calc_occ(total_rns),
        "revpar": calc_revpar(total_rev),
        "is_total": True,
    })

    return rows

def build_pickup_table(today, yesterday):
    y_map = {d["stay_date"]: d for d in yesterday}
    t_map = {d["stay_date"]: d for d in today}

    all_dates = sorted(set(t_map.keys()) | set(y_map.keys()))

    rows = []
    total_rns = total_rev = total_var_rns = total_var_rev = 0

    for dt in all_dates:
        t = t_map.get(dt, {"rns": 0, "adr": 0, "revenue": 0})
        y = y_map.get(dt, {"rns": 0, "adr": 0, "revenue": 0})

        rns = t["rns"] or 0
        rev = t["revenue"] or 0
        adr = t["adr"] or 0

        var_rns = rns - (y["rns"] or 0)
        var_rev = rev - (y["revenue"] or 0)

        total_rns += rns
        total_rev += rev
        total_var_rns += var_rns
        total_var_rev += var_rev

        rows.append({
            "date": dt,
            "rns": rns,
            "var_rns": var_rns,
            "adr": adr,
            "revenue": rev,
            "var_rev": var_rev,
            "occ": calc_occ(rns),
            "revpar": calc_revpar(rev),
        })

    total_adr = round(total_rev / total_rns, 2) if total_rns > 0 else 0

    rows.append({
        "date": "Totale",
        "rns": total_rns,
        "var_rns": total_var_rns,
        "adr": total_adr,
        "revenue": total_rev,
        "var_rev": total_var_rev,
        "occ": calc_occ(total_rns),
        "revpar": calc_revpar(total_rev),
        "is_total": True,
    })

    return rows

# ─── PARSER EXCEL PMS ─────────────────────────────────────

def parse_excel_formato_specifico(filepath):
    if not os.path.exists(filepath):
        raise ValueError("File non trovato")

    if os.path.getsize(filepath) == 0:
        raise ValueError("File vuoto")

    df_raw = pd.read_excel(filepath, header=None, skiprows=2)

    if df_raw.empty:
        raise ValueError("File senza dati")

    if df_raw.shape[1] < 15:
        raise ValueError("Formato Excel non valido (colonne insufficienti)")

    df = pd.DataFrame()
    df["DATA"] = df_raw.iloc[:, 0]
    df["RNS"] = df_raw.iloc[:, 10]
    df["ADR"] = df_raw.iloc[:, 11]
    df["REVENUE"] = df_raw.iloc[:, 14]

    df["DATA"] = pd.to_datetime(df["DATA"].astype(str).str[:10], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["DATA"])

    df["RNS"] = pd.to_numeric(df["RNS"], errors="coerce").fillna(0).astype(int)
    df["REVENUE"] = pd.to_numeric(df["REVENUE"], errors="coerce").fillna(0)
    df["ADR"] = pd.to_numeric(df["ADR"], errors="coerce").fillna(0)

    mask = (df["ADR"] == 0) & (df["RNS"] > 0)
    df.loc[mask, "ADR"] = (df["REVENUE"] / df["RNS"]).round(2)

    if df.empty:
        raise ValueError("Nessun dato valido trovato")

    return df

# ─── ROUTES ─────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("pickup"))

@app.route("/pickup")
def pickup():
    available = get_available_ref_dates()

    if not available:
        return render_template("pickup.html", available=[])

    ref = request.args.get("ref_date", available[0])
    idx = available.index(ref)
    prev = available[idx + 1] if idx + 1 < len(available) else None

    data_today = get_data_for_date(ref)
    data_yest = get_data_for_date(prev) if prev else []

    table_today = build_pickup_table(data_today, data_yest)

    return render_template(
        "pickup.html",
        available=available,
        today=ref,
        yesterday=prev,
        table_today=table_today
    )

@app.route("/caricamento", methods=["GET", "POST"])
def caricamento():
    if request.method == "POST":
        ref_date = request.form.get("ref_date")
        file = request.files.get("file")

        if not ref_date:
            flash("Inserisci la data.", "error")
            return redirect(url_for("caricamento"))

        if not file or not file.filename:
            flash("Seleziona file.", "error")
            return redirect(url_for("caricamento"))

        if not allowed_file(file.filename):
            flash("Formato non valido.", "error")
            return redirect(url_for("caricamento"))

        filename = secure_filename(file.filename)
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        try:
            file.save(filepath)
            df = parse_excel_formato_specifico(filepath)

            with get_db() as conn:
                conn.execute("DELETE FROM pickup_data WHERE ref_date=?", (ref_date,))
                count = 0

                for _, r in df.iterrows():
                    conn.execute(
                        "INSERT INTO pickup_data VALUES (NULL,?,?,?,?,?)",
                        (
                            ref_date,
                            r["DATA"].strftime("%Y-%m-%d"),
                            int(r["RNS"]),
                            float(r["ADR"]),
                            float(r["REVENUE"])
                        )
                    )
                    count += 1

                conn.execute(
                    "INSERT INTO uploads VALUES (NULL,?,?,?,?)",
                    (datetime.now().strftime("%d/%m/%Y %H:%M"), ref_date, count, filename)
                )
                conn.commit()

            flash(f"Caricato: {count} righe", "success")
            return redirect(url_for("caricamento"))

        except Exception as e:
            flash(str(e), "error")
            return redirect(url_for("caricamento"))

    with get_db() as conn:
        uploads = conn.execute("SELECT * FROM uploads ORDER BY id DESC").fetchall()

    today = datetime.now().strftime("%Y-%m-%d")

    return render_template(
        "caricamento.html",
        uploads=[dict(u) for u in uploads],
        today=today
    )

# ─── AVVIO ─────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
