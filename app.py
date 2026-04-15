from flask import Flask, render_template, request, redirect, url_for, flash
import pandas as pd
import os, json, sqlite3
from datetime import datetime, date
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "pickup_secret_key"
UPLOAD_FOLDER = "uploads"
DB_PATH = "pickup.db"
CAPACITY = 55  # <-- Modifica con il numero di camere del tuo hotel

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

def get_data_for_date(ref_date_str):
        """Restituisce tutti i record per una data di riferimento."""
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
        """Costruisce una lista di righe con calcoli OCC% e REVPAR."""
        rows = []
        total_rns, total_revenue = 0, 0
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
        """Costruisce tabella pickup con varianza vs ieri."""
    yest_map = {d["stay_date"]: d for d in data_yesterday}
    today_map = {d["stay_date"]: d for d in data_today}

    all_dates = sorted(set(list(today_map.keys()) + list(yest_map.keys())))

    rows = []
    total_rns, total_var_rns, total_rev, total_var_rev = 0, 0, 0, 0

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

# ─── PARSING EXCEL FORMATO SPECIFICO ────────────────────────────────────────
#
# Il file Excel ha questa struttura (2 righe di intestazione):
#   Riga 1: titoli di gruppo (celle unite) - es. "Fino al 14/04/2026", "Fino al 15/04/2026", "PICKUP"
#   Riga 2: intestazioni colonne:
#     A=Giorno, B=Ubicazione/Ist, C=Camere Totali,
#     D=DISP(prev), E=CAM(prev), F=ADR(prev), G=%occ(prev), H=RevPAR(prev), I=Totale(prev),
#     J=DISP(curr), K=CAM(curr), L=ADR(curr), M=%occ(curr), N=RevPAR(curr), O=Totale(curr),
#     P=CAM(pickup), Q=ADR(pickup), R=Totale(pickup)
#   Righe 3+: dati giornalieri
#
# Colonne usate:
#   - DATA      = colonna A  (indice 0)  - data del giorno
#   - RNS curr  = colonna K  (indice 10) - camere occupate (periodo di riferimento attuale)
#   - ADR curr  = colonna L  (indice 11) - tariffa media (periodo di riferimento attuale)
#   - REV curr  = colonna O  (indice 14) - ricavo totale (periodo di riferimento attuale)

def parse_excel_formato_specifico(filepath):
        """
            Legge il file Excel con la struttura a doppia intestazione del PMS.
                Restituisce un DataFrame con colonne: DATA, RNS, ADR, REVENUE
                    """
    # Legge il file saltando le prime 2 righe di intestazione,
    # senza usare nessuna riga come header (header=None)
    df_raw = pd.read_excel(filepath, header=None, skiprows=2)

    # Mappa le colonne per posizione (0-based):
    # Col 0  = Giorno (data)
    # Col 10 = CAM periodo corrente (RNS)
    # Col 11 = ADR periodo corrente
    # Col 14 = Totale/Revenue periodo corrente
    COL_DATA    = 0
    COL_RNS     = 10
    COL_ADR     = 11
    COL_REVENUE = 14

    df = pd.DataFrame()
    df["DATA"]    = df_raw.iloc[:, COL_DATA]
    df["RNS"]     = df_raw.iloc[:, COL_RNS]
    df["ADR"]     = df_raw.iloc[:, COL_ADR]
    df["REVENUE"] = df_raw.iloc[:, COL_REVENUE]

    # Pulizia: converte la data (può essere stringa "01/04/2026 mer" o datetime)
    df["DATA"] = pd.to_datetime(df["DATA"].astype(str).str[:10], dayfirst=True, errors="coerce")

    # Rimuove righe senza data valida (es. righe totale o vuote)
    df = df.dropna(subset=["DATA"])

    # Converte i valori numerici
    df["RNS"]     = pd.to_numeric(df["RNS"],     errors="coerce").fillna(0).astype(int)
    df["REVENUE"] = pd.to_numeric(df["REVENUE"], errors="coerce").fillna(0)
    df["ADR"]     = pd.to_numeric(df["ADR"],     errors="coerce").fillna(0)

    # Calcola ADR se zero ma RNS e REVENUE sono presenti
    mask = (df["ADR"] == 0) & (df["RNS"] > 0)
    df.loc[mask, "ADR"] = (df.loc[mask, "REVENUE"] / df.loc[mask, "RNS"]).round(2)

    return df

def parse_excel_generico(filepath, skip_rows):
        """
            Parsing generico per file Excel con colonne nominate.
                Tenta di trovare colonne DATA, RNS, ADR, REVENUE per nome.
                    """
    df = pd.read_excel(filepath, skiprows=skip_rows)
    df.columns = [str(c).strip().upper() for c in df.columns]

    col_map = {}
    for col in df.columns:
                if "DATA" in col or "DATE" in col or "GIORNO" in col:
                                col_map[col] = "DATA"
elif col in ("RNS", "ROOMS", "CAMERE", "CAM", "RN", "ROOM NIGHTS"):
            col_map[col] = "RNS"
elif "ADR" in col or "TARIFFA" in col or "RATE" in col:
            col_map[col] = "ADR"
elif "REVENUE" in col or "RICAVO" in col or "TOTALE" in col:
            col_map[col] = "REVENUE"
    df.rename(columns=col_map, inplace=True)

    required = {"DATA", "RNS", "REVENUE"}
    if not required.issubset(set(df.columns)):
                raise ValueError(f"Colonne mancanti. Trovate: {list(df.columns)}. Necessarie: DATA, RNS, REVENUE")

    if "ADR" not in df.columns:
                df["ADR"] = df.apply(
                                lambda r: round(r["REVENUE"] / r["RNS"], 2) if r["RNS"] > 0 else 0, axis=1
                )

    df["DATA"]    = pd.to_datetime(df["DATA"], dayfirst=True, errors="coerce")
    df            = df.dropna(subset=["DATA"])
    df["RNS"]     = pd.to_numeric(df["RNS"],     errors="coerce").fillna(0).astype(int)
    df["REVENUE"] = pd.to_numeric(df["REVENUE"], errors="coerce").fillna(0)
    df["ADR"]     = pd.to_numeric(df["ADR"],     errors="coerce").fillna(0)

    return df

# ─── ROUTES ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
        return redirect(url_for("pickup"))

@app.route("/pickup")
def pickup():
        available = get_available_ref_dates()
    if not available:
                return render_template("pickup.html", available=[], today=None, yesterday=None,
                                                                      table_yest=[], table_today=[], variance_rns=0,
                                                                      variance_rev=0, chart_labels=[], chart_today=[], chart_yest=[])

    ref_date_str = request.args.get("ref_date", available[0])

    idx = available.index(ref_date_str) if ref_date_str in available else 0
    prev_date_str = available[idx + 1] if idx + 1 < len(available) else None

    data_today = get_data_for_date(ref_date_str)
    data_yesterday = get_data_for_date(prev_date_str) if prev_date_str else []

    table_yest = build_table(data_yesterday) if data_yesterday else []
    table_today = build_pickup_table(data_today, data_yesterday)

    tot_today_rns = sum(d["rns"] or 0 for d in data_today)
    tot_yest_rns  = sum(d["rns"] or 0 for d in data_yesterday)
    tot_today_rev = sum(d["revenue"] or 0 for d in data_today)
    tot_yest_rev  = sum(d["revenue"] or 0 for d in data_yesterday)
    variance_rns  = tot_today_rns - tot_yest_rns
    variance_rev  = round(tot_today_rev - tot_yest_rev, 2)

    ref_dt  = datetime.strptime(ref_date_str, "%Y-%m-%d")
    prev_dt = datetime.strptime(prev_date_str, "%Y-%m-%d") if prev_date_str else None
    chart_labels = [
                prev_dt.strftime("%-d° %B %Y") if prev_dt else "—",
                ref_dt.strftime("%-d° %B %Y"),
    ]
    chart_today = [round(tot_yest_rev, 2), round(tot_today_rev, 2)]

    return render_template("pickup.html",
                                                      available=available,
                                                      today=ref_date_str,
                                                      yesterday=prev_date_str,
                                                      table_yest=table_yest,
                                                      table_today=table_today,
                                                      variance_rns=variance_rns,
                                                      variance_rev=variance_rev,
                                                      chart_labels=chart_labels,
                                                      chart_today=chart_today,
                                                      ref_date=ref_date_str,
                                                      ref_dt=ref_dt,
                                                      prev_dt=prev_dt,
                                                      capacity=CAPACITY,
                          )

@app.route("/caricamento", methods=["GET", "POST"])
def caricamento():
        if request.method == "POST":
                    ref_date_str = request.form.get("ref_date")
                    skip_rows    = int(request.form.get("skip_rows", 0))
                    file         = request.files.get("file")
                    formato = "specifico"  # forza sempre il formato PMS

        if not file or not ref_date_str:
                        flash("Seleziona un file e una data di riferimento.", "error")
                        return redirect(url_for("caricamento"))

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        try:
                        if formato == "specifico":
                                            df = parse_excel_formato_specifico(filepath)
        else:
                            df = parse_excel_generico(filepath, skip_rows)

            with get_db() as conn:
                                conn.execute("DELETE FROM pickup_data WHERE ref_date=?", (ref_date_str,))
                                inserted = 0
                                for _, row in df.iterrows():
                                                        conn.execute(
                                                                                    "INSERT INTO pickup_data (ref_date, stay_date, rns, adr, revenue) VALUES (?,?,?,?,?)",
                                                                                    (ref_date_str, row["DATA"].strftime("%Y-%m-%d"),
                                                                                                              int(row["RNS"]), float(row["ADR"]), float(row["REVENUE"]))
                                                        )
                                                        inserted += 1
                                                    conn.execute(
                                                                            "INSERT INTO uploads (upload_datetime, ref_date, num_inserted, filename) VALUES (?,?,?,?)",
                                                                            (datetime.now().strftime("%d/%m/%Y %H:%M"), ref_date_str, inserted, filename)
                                                    )
                conn.commit()

            flash(f"Caricamento completato: {inserted} righe inserite.", "success")
            return redirect(url_for("caricamento"))

except Exception as e:
            flash(f"Errore durante il caricamento: {str(e)}", "error")
            return redirect(url_for("caricamento"))

    with get_db() as conn:
                uploads = conn.execute(
                                "SELECT * FROM uploads ORDER BY id DESC"
                ).fetchall()
    return render_template("caricamento.html", uploads=[dict(u) for u in uploads])

if __name__ == "__main__":
        port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
