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
CAPACITY = 55  # numero camere hotel
ALLOWED_EXTENSIONS = {"xlsx", "xls"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─── DATABASE ───────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                upload_datetime TEXT NOT NULL,
                ref_date TEXT NOT NULL,
                num_inserted INTEGER,
                filename TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pickup_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_date TEXT NOT NULL,
                stay_date TEXT NOT NULL,
                rns INTEGER,
                adr REAL,
                revenue REAL
            )
        """)
        conn.commit()


init_db()

# ─── HELPERS ────────────────────────────────────────────────────────────────

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
    total_revenue = 0

    for d in data:
        rns = d["rns"] or 0
        revenue = d["revenue"] or 0
        adr = d["adr"] or 0

        total_rns += rns
        total_revenue += revenue

        rows.append({
            "date": d["stay_date"],
            "rns": rns,
            "adr": adr,
            "revenue": revenue,
            "occ": calc_occ(rns),
            "revpar": calc_revpar(revenue),
        })

    total_adr = round(total_revenue / total_rns, 2) if total_rns > 0 else 0

    rows.append({
        "date": "Totale",
        "rns": total_rns,
        "adr": total_adr,
        "revenue": total_revenue,
        "occ": calc_occ(total_rns),
        "revpar": calc_revpar(total_revenue),
        "is_total": True,
    })

    return rows


def build_pickup_table(data_today, data_yesterday):
    yest_map = {d["stay_date"]: d for d in data_yesterday}
    today_map = {d["stay_date"]: d for d in data_today}
    all_dates = sorted(set(list(today_map.keys()) + list(yest_map.keys())))

    rows = []
    total_rns = total_var_rns = total_rev = total_var_rev = 0

    for dt in all_dates:
        t = today_map.get(dt, {"rns": 0, "adr": 0, "revenue": 0})
        y = yest_map.get(dt, {"rns": 0, "adr": 0, "revenue": 0})

        rns = t["rns"] or 0
        revenue = t["revenue"] or 0
        adr = t["adr"] or 0
        var_rns = rns - (y["rns"] or 0)
        var_rev = revenue - (y["revenue"] or 0)

        total_rns += rns
        total_rev += revenue
        total_var_rns += var_rns
        total_var_rev += var_rev

        rows.append({
            "date": dt,
            "rns": rns,
            "var_rns": var_rns,
            "adr": adr,
            "revenue": revenue,
            "var_rev": var_rev,
            "occ": calc_occ(rns),
            "revpar": calc_revpar(revenue),
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


# ─── PARSING EXCEL PMS ──────────────────────────────────────────────────────

def parse_excel_formato_specifico(filepath):
    """
    Legge il file Excel PMS con doppia intestazione.
    Colonne attese:
    A  = data
    K  = camere occupate / RNS
    L  = ADR
    O  = revenue
    """

    if not os.path.exists(filepath):
        raise ValueError("Il file caricato non esiste.")

    if os.path.getsize(filepath) == 0:
        raise ValueError("Il file caricato è vuoto.")

    try:
        df_raw = pd.read_excel(filepath, header=None, skiprows=2)
    except Exception as e:
        raise ValueError(f"Impossibile leggere il file Excel: {str(e)}")

    if df_raw.empty:
        raise ValueError("Il file Excel non contiene righe leggibili dopo le intestazioni.")

    # Indici richiesti: 0, 10, 11, 14 → servono almeno 15 colonne
    required_min_columns = 15
    if df_raw.shape[1] < required_min_columns:
        raise ValueError(
            f"Formato Excel non valido: trovate solo {df_raw.shape[1]} colonne, "
            f"ma il file PMS ne richiede almeno {required_min_columns}."
        )

    COL_DATA = 0
    COL_RNS = 10
    COL_ADR = 11
    COL_REVENUE = 14

    df = pd.DataFrame()
    df["DATA"] = df_raw.iloc[:, COL_DATA]
    df["RNS"] = df_raw.iloc[:, COL_RNS]
    df["ADR"] = df_raw.iloc[:, COL_ADR]
    df["REVENUE"] = df_raw.iloc[:, COL_REVENUE]

    # Normalizzazione date
    df["DATA"] = pd.to_datetime(
        df["DATA"].astype(str).str[:10],
        dayfirst=True,
        errors="coerce"
    )

    valid_dates = df["DATA"].notna().sum()
    if valid_dates == 0:
        raise ValueError(
            "Nessuna data valida trovata nel file. Controlla che la colonna A contenga le date del PMS."
        )

    df = df.dropna(subset=["DATA"]).copy()

    # Conversioni numeriche
    df["RNS"] = pd.to_numeric(df["RNS"], errors="coerce").fillna(0).astype(int)
    df["REVENUE"] = pd.to_numeric(df["REVENUE"], errors="coerce").fillna(0.0)
    df["ADR"] = pd.to_numeric(df["ADR"], errors="coerce").fillna(0.0)

    # Calcolo ADR mancante
    mask = (df["ADR"] == 0) & (df["RNS"] > 0)
    df.loc[mask, "ADR"] = (df.loc[mask, "REVENUE"] / df.loc[mask, "RNS"]).round(2)

    # Scarta righe completamente inutili
    df = df[(df["RNS"] > 0) | (df["REVENUE"] > 0) | (df["ADR"] > 0)].copy()

    if df.empty:
        raise ValueError(
            "Il file è stato letto, ma non contiene righe utili da importare "
            "(RNS, ADR e Revenue risultano tutti vuoti o zero)."
        )

    return df


# ─── ROUTES ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("pickup"))


@app.route("/pickup")
def pickup():
    available = get_available_ref_dates()

    if not available:
        return render_template(
            "pickup.html",
            available=[],
            today=None,
            yesterday=None,
            table_yest=[],
            table_today=[],
            variance_rns=0,
            variance_rev=0,
            chart_labels=[],
            chart_today=[],
        )

    ref_date_str = request.args.get("ref_date", available[0])
    idx = available.index(ref_date_str) if ref_date_str in available else 0
    prev_date_str = available[idx + 1] if idx + 1 < len(available) else None

    data_today = get_data_for_date(ref_date_str)
    data_yesterday = get_data_for_date(prev_date_str) if prev_date_str else []

    table_yest = build_table(data_yesterday) if data_yesterday else []
    table_today = build_pickup_table(data_today, data_yesterday)

    tot_today_rns = sum(d["rns"] or 0 for d in data_today)
    tot_yest_rns = sum(d["rns"] or 0 for d in data_yesterday)
    tot_today_rev = sum(d["revenue"] or 0 for d in data_today)
    tot_yest_rev = sum(d["revenue"] or 0 for d in data_yesterday)

    variance_rns = tot_today_rns - tot_yest_rns
    variance_rev = round(tot_today_rev - tot_yest_rev, 2)

    ref_dt = datetime.strptime(ref_date_str, "%Y-%m-%d")
    prev_dt = datetime.strptime(prev_date_str, "%Y-%m-%d") if prev_date_str else None

    chart_labels = [
        prev_dt.strftime("%d/%m/%Y") if prev_dt else "—",
        ref_dt.strftime("%d/%m/%Y"),
    ]
    chart_today = [round(tot_yest_rev, 2), round(tot_today_rev, 2)]

    return render_template(
        "pickup.html",
        available=available,
        today=ref_date_str,
        yesterday=prev_date_str,
        table_yest=table_yest,
        table_today=table_today,
        variance_rns=variance_rns,
        variance_rev=variance_rev,
        chart_labels=chart_labels,
        chart_today=chart_today,
        capacity=CAPACITY,
    )


@app.route("/caricamento", methods=["GET", "POST"])
def caricamento():
    if request.method == "POST":
        ref_date_str = request.form.get("ref_date")
        file = request.files.get("file")

        if not ref_date_str:
            flash("Inserisci la data di riferimento.", "error")
            return redirect(url_for("caricamento"))

        if not file or not file.filename:
            flash("Seleziona un file Excel da caricare.", "error")
            return redirect(url_for("caricamento"))

        if not allowed_file(file.filename):
            flash("Formato file non valido. Carica solo file Excel .xlsx o .xls", "error")
            return redirect(url_for("caricamento"))

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        try:
            file.save(filepath)

            df = parse_excel_formato_specifico(filepath)

            with get_db() as conn:
                conn.execute("DELETE FROM pickup_data WHERE ref_date=?", (ref_date_str,))
                inserted = 0

                for _, row in df.iterrows():
                    conn.execute(
                        "INSERT INTO pickup_data (ref_date, stay_date, rns, adr, revenue) VALUES (?,?,?,?,?)",
                        (
                            ref_date_str,
                            row["DATA"].strftime("%Y-%m-%d"),
                            int(row["RNS"]),
                            float(row["ADR"]),
                            float(row["REVENUE"]),
                        )
                    )
                    inserted += 1

                conn.execute(
                    "INSERT INTO uploads (upload_datetime, ref_date, num_inserted, filename) VALUES (?,?,?,?)",
                    (
                        datetime.now().strftime("%d/%m/%Y %H:%M"),
                        ref_date_str,
                        inserted,
                        filename,
                    )
                )
                conn.commit()

            flash(f"Caricamento completato: {inserted} righe inserite.", "success")
            return redirect(url_for("caricamento"))

        except Exception as e:
            flash(f"Errore durante il caricamento: {str(e)}", "error")
            return redirect(url_for("caricamento"))

    with get_db() as conn:
        uploads = conn.execute("SELECT * FROM uploads ORDER BY id DESC").fetchall()

    return render_template("caricamento.html", uploads=[dict(u) for u in uploads])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
