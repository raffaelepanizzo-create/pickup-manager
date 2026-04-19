from flask import Flask, render_template, request, redirect, url_for, flash, session
import pandas as pd
import os
import sqlite3
from datetime import datetime
import calendar
from werkzeug.utils import secure_filename
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pickup_secret_key_dev")

UPLOAD_FOLDER = os.environ.get("PICKUP_UPLOAD_FOLDER", "uploads")
DB_PATH = os.environ.get("PICKUP_DB_PATH", "pickup.db")
CAPACITY = 55
ALLOWED_EXTENSIONS = {"xlsx", "xls"}

APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "changeme")

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                month INTEGER PRIMARY KEY,
                target_occ REAL DEFAULT 0,
                target_revenue REAL DEFAULT 0
            )
        """)
        for m in range(1, 13):
            conn.execute("INSERT OR IGNORE INTO settings (month, target_occ, target_revenue) VALUES (?, 0, 0)", (m,))
        conn.commit()


init_db()


# ─── AUTH ───────────────────────────────────────────────────────────────────

def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped_view


# ─── HELPERS ────────────────────────────────────────────────────────────────

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_data_for_date(ref_date_str):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT stay_date, rns, adr, revenue
            FROM pickup_data
            WHERE ref_date = ?
            ORDER BY stay_date
            """,
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
    total_rns = 0
    total_var_rns = 0
    total_rev = 0
    total_var_rev = 0

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


def build_daily_chart_series(data_today, data_yest):
    today_map = {d["stay_date"]: d for d in data_today}
    yest_map = {d["stay_date"]: d for d in data_yest}
    all_dates = sorted(set(today_map.keys()) | set(yest_map.keys()))

    labels = [f"{d[8:10]}/{d[5:7]}" for d in all_dates]
    today_rns = [(today_map.get(d, {}).get("rns") or 0) for d in all_dates]
    yest_rns = [(yest_map.get(d, {}).get("rns") or 0) for d in all_dates]
    today_rev = [round((today_map.get(d, {}).get("revenue") or 0), 2) for d in all_dates]
    yest_rev = [round((yest_map.get(d, {}).get("revenue") or 0), 2) for d in all_dates]
    today_occ = [calc_occ(today_map.get(d, {}).get("rns") or 0) for d in all_dates]
    today_revpar = [calc_revpar(today_map.get(d, {}).get("revenue") or 0) for d in all_dates]

    return {
        "labels": labels,
        "today_rns": today_rns,
        "yest_rns": yest_rns,
        "today_rev": today_rev,
        "yest_rev": yest_rev,
        "today_occ": today_occ,
        "today_revpar": today_revpar,
    }


# ─── PARSER EXCEL PMS ───────────────────────────────────────────────────────

def parse_excel_formato_specifico(filepath):
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

    if df_raw.shape[1] < 15:
        raise ValueError(
            f"Formato Excel non valido: trovate solo {df_raw.shape[1]} colonne, ma ne servono almeno 15."
        )

    df = pd.DataFrame()
    df["DATA"] = df_raw.iloc[:, 0]
    df["RNS"] = df_raw.iloc[:, 10]
    df["ADR"] = df_raw.iloc[:, 11]
    df["REVENUE"] = df_raw.iloc[:, 14]

    df["DATA"] = pd.to_datetime(
        df["DATA"].astype(str).str[:10],
        dayfirst=True,
        errors="coerce"
    )

    if df["DATA"].notna().sum() == 0:
        raise ValueError("Nessuna data valida trovata nella colonna A del file PMS.")

    df = df.dropna(subset=["DATA"]).copy()

    df["RNS"] = pd.to_numeric(df["RNS"], errors="coerce").fillna(0).astype(int)
    df["ADR"] = pd.to_numeric(df["ADR"], errors="coerce").fillna(0.0)
    df["REVENUE"] = pd.to_numeric(df["REVENUE"], errors="coerce").fillna(0.0)

    mask = (df["ADR"] == 0) & (df["RNS"] > 0)
    df.loc[mask, "ADR"] = (df.loc[mask, "REVENUE"] / df.loc[mask, "RNS"]).round(2)

    if df.empty:
        raise ValueError("Nessun dato valido trovato nel file.")

    return df


# ─── FILTER CONTEXT (Data di riferimento + Mese) ─────────────────────────

MONTH_NAMES_IT = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]
MONTH_ABBR_IT = [
    "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
    "Lug", "Ago", "Set", "Ott", "Nov", "Dic",
]


def get_available_months():
    """Return the sorted list (asc) of YYYY-MM that are present in pickup_data.stay_date."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT substr(stay_date, 1, 7) AS ym FROM pickup_data ORDER BY ym"
        ).fetchall()
    return [r["ym"] for r in rows]


def _default_month_for_ref(ref_date):
    """Return YYYY-MM derived from ref_date (YYYY-MM-DD) or None."""
    if not ref_date or len(ref_date) < 7:
        return None
    return ref_date[:7]


def _neighbor_month(months, current, delta):
    """Return the neighbour (prev/next) month in `months` list, or None if not available."""
    if not months or current not in months:
        return None
    idx = months.index(current) + delta
    if idx < 0 or idx >= len(months):
        return None
    return months[idx]


def resolve_filters(ref_date_arg=None, month_arg=None):
    """
    Resolve ref_date and month from query args (or provided values),
    returning a dict with all the data needed by base.html filter bar.
    """
    available = get_available_ref_dates()
    available_months = get_available_months()

    # Normalize ref_date
    ref_date = ref_date_arg if ref_date_arg is not None else request.args.get("ref_date")
    if ref_date not in available:
        ref_date = available[0] if available else None

    # Normalize month
    month = month_arg if month_arg is not None else request.args.get("month")
    if not month or len(month) != 7 or month[4] != "-":
        month = _default_month_for_ref(ref_date)
    # If month is not in the available list, keep user-chosen value (popup still works)

    if month:
        try:
            month_num = int(month[5:7])
            month_name = MONTH_NAMES_IT[month_num - 1]
            month_abbr = MONTH_ABBR_IT[month_num - 1]
            month_label = f"{month_abbr}/{month[:4]}"
        except (ValueError, IndexError):
            month_name = ""
            month_abbr = ""
            month_label = ""
    else:
        month_name = ""
        month_abbr = ""
        month_label = ""

    prev_month = _neighbor_month(available_months, month, -1) if month else None
    next_month = _neighbor_month(available_months, month, 1) if month else None

    return {
        "available": available,
        "available_months": available_months,
        "ref_date": ref_date,
        "month": month,
        "month_name": month_name,
        "month_abbr": month_abbr,
        "month_label": month_label,
        "prev_month": prev_month,
        "next_month": next_month,
    }


@app.context_processor
def inject_filters():
    """Expose filter context to all templates when user is logged in."""
    if not session.get("logged_in"):
        return {}
    try:
        return resolve_filters()
    except Exception:
        return {}


# ─── ROUTES ─────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == APP_USERNAME and password == APP_PASSWORD:
            session["logged_in"] = True
            session["username"] = username
            flash("Accesso effettuato.", "success")
            return redirect(url_for("pickup"))

        flash("Credenziali non valide.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logout effettuato.", "success")
    return redirect(url_for("login"))


@app.route("/")
def index():
    return redirect(url_for("pickup"))


@app.route("/pickup")
@login_required
def pickup():
    available = get_available_ref_dates()

    if not available:
        return render_template(
            "pickup.html",
            today=None,
            yesterday=None,
            table_yest=[],
            table_today=[],
            variance_rns=0,
            variance_rev=0,
            chart_labels=[],
            chart_today=[],
            ref_dt=None,
            prev_dt=None,
            capacity=CAPACITY,
            daily_labels=[],
            daily_rns_today=[],
            daily_rns_yest=[],
            daily_rev_today=[],
            daily_rev_yest=[],
            daily_occ_today=[],
            daily_revpar_today=[],
            daily_target_occ=[],
            daily_target_rev=[],
            daily_target_rns=[],
        )

    # Resolve ref_date (use first available if missing/invalid)
    ref_date = request.args.get("ref_date", available[0])
    if ref_date not in available:
        ref_date = available[0]

    idx = available.index(ref_date)
    prev_date = available[idx + 1] if idx + 1 < len(available) else None

    # Resolve month (default: month of ref_date)
    month = request.args.get("month")
    if not month or len(month) != 7 or month[4] != "-":
        month = ref_date[:7]

    data_today = get_data_for_date(ref_date)
    data_yest = get_data_for_date(prev_date) if prev_date else []

    # Filter data for selected month (by stay_date prefix YYYY-MM)
    data_today_m = [d for d in data_today if (d["stay_date"] or "").startswith(month)]
    data_yest_m = [d for d in data_yest if (d["stay_date"] or "").startswith(month)]

    table_yest = build_table(data_yest_m) if data_yest_m else []
    table_today = build_pickup_table(data_today_m, data_yest_m)

    # Totals reference the filtered month for variance boxes
    tot_today_rns = sum(d["rns"] or 0 for d in data_today_m)
    tot_yest_rns = sum(d["rns"] or 0 for d in data_yest_m)
    tot_today_rev = sum(d["revenue"] or 0 for d in data_today_m)
    tot_yest_rev = sum(d["revenue"] or 0 for d in data_yest_m)

    variance_rns = tot_today_rns - tot_yest_rns
    variance_rev = round(tot_today_rev - tot_yest_rev, 2)

    ref_dt = datetime.strptime(ref_date, "%Y-%m-%d")
    prev_dt = datetime.strptime(prev_date, "%Y-%m-%d") if prev_date else None

    chart_labels = [
        prev_dt.strftime("%d/%m/%Y") if prev_dt else "—",
        ref_dt.strftime("%d/%m/%Y"),
    ]
    chart_today = [round(tot_yest_rev, 2), round(tot_today_rev, 2)]

    daily = build_daily_chart_series(data_today_m, data_yest_m)

    # Carica target mensili dalla tabella settings
    with get_db() as conn:
        settings_rows = conn.execute("SELECT month, target_occ, target_revenue FROM settings").fetchall()
    targets_by_month = {r["month"]: {"occ": r["target_occ"] or 0, "rev": r["target_revenue"] or 0} for r in settings_rows}

    # Daily targets computed on the filtered-month dates
    today_map_for_targets = {d["stay_date"]: d for d in data_today_m}
    yest_map_for_targets = {d["stay_date"]: d for d in data_yest_m}
    all_dates_sorted = sorted(set(today_map_for_targets.keys()) | set(yest_map_for_targets.keys()))

    daily_target_occ = []
    daily_target_rev = []
    daily_target_rns = []
    for d in all_dates_sorted:
        year_int = int(d[0:4])
        month_int = int(d[5:7])
        days_in_month = calendar.monthrange(year_int, month_int)[1]
        tgt = targets_by_month.get(month_int, {"occ": 0, "rev": 0})
        occ_target = tgt["occ"]
        rev_target_daily = round((tgt["rev"] or 0) / days_in_month, 2) if days_in_month else 0
        rns_target_daily = round((occ_target / 100.0) * CAPACITY, 2)
        daily_target_occ.append(occ_target)
        daily_target_rev.append(rev_target_daily)
        daily_target_rns.append(rns_target_daily)

    return render_template(
        "pickup.html",
        today=ref_date,
        yesterday=prev_date,
        table_yest=table_yest,
        table_today=table_today,
        variance_rns=variance_rns,
        variance_rev=variance_rev,
        chart_labels=chart_labels,
        chart_today=chart_today,
        ref_dt=ref_dt,
        prev_dt=prev_dt,
        capacity=CAPACITY,
        daily_labels=daily["labels"],
        daily_rns_today=daily["today_rns"],
        daily_rns_yest=daily["yest_rns"],
        daily_rev_today=daily["today_rev"],
        daily_rev_yest=daily["yest_rev"],
        daily_occ_today=daily["today_occ"],
        daily_revpar_today=daily["today_revpar"],
        daily_target_occ=daily_target_occ,
        daily_target_rev=daily_target_rev,
        daily_target_rns=daily_target_rns,
    )


@app.route("/caricamento", methods=["GET", "POST"])
@login_required
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

        original_filename = secure_filename(file.filename)
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{original_filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        try:
            file.save(filepath)
            df = parse_excel_formato_specifico(filepath)

            with get_db() as conn:
                conn.execute("DELETE FROM pickup_data WHERE ref_date = ?", (ref_date_str,))
                inserted = 0

                for _, row in df.iterrows():
                    conn.execute(
                        """
                        INSERT INTO pickup_data (ref_date, stay_date, rns, adr, revenue)
                        VALUES (?, ?, ?, ?, ?)
                        """,
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
                    """
                    INSERT INTO uploads (upload_datetime, ref_date, num_inserted, filename)
                    VALUES (?, ?, ?, ?)
                    """,
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

    today = datetime.now().strftime("%Y-%m-%d")

    return render_template(
        "caricamento.html",
        uploads=[dict(u) for u in uploads],
        today=today
    )


@app.route("/impostazioni", methods=["GET", "POST"])
@login_required
def impostazioni():
    with get_db() as conn:
        if request.method == "POST":
            for m in range(1, 13):
                occ = request.form.get(f"occ_{m}", "0").replace(",", ".").strip() or "0"
                rev = request.form.get(f"rev_{m}", "0").replace(",", ".").strip() or "0"
                try:
                    occ_val = float(occ)
                    rev_val = float(rev)
                except ValueError:
                    occ_val = 0.0
                    rev_val = 0.0
                conn.execute(
                    "UPDATE settings SET target_occ = ?, target_revenue = ? WHERE month = ?",
                    (occ_val, rev_val, m),
                )
            conn.commit()
            flash("Impostazioni salvate.", "success")
            return redirect(url_for("impostazioni"))

        rows = conn.execute("SELECT month, target_occ, target_revenue FROM settings ORDER BY month").fetchall()

    month_names = [
        "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
        "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
    ]
    targets = []
    for r in rows:
        targets.append({
            "month": r["month"],
            "name": month_names[r["month"] - 1],
            "target_occ": r["target_occ"] or 0,
            "target_revenue": r["target_revenue"] or 0,
        })

    return render_template("settings.html", targets=targets)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
