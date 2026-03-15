from flask import Flask, render_template, request, redirect, url_for, jsonify, session
import sqlite3
import os
from datetime import datetime, timedelta
import hashlib
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'medipol-itiraf-secret-2024'

ITIRAF_KATEGORILER = ['itiraf', 'ask', 'overheard', 'komik', 'okul', 'pismanlik', 'protesto', 'diger']
KATEGORI_ETIKETLER = {
    'itiraf': 'İtiraf', 'ask': 'Aşk', 'overheard': 'Overheard',
    'komik': 'Komik', 'okul': 'Okul', 'pismanlik': 'Pişmanlık',
    'protesto': 'Protesto', 'diger': 'Diğer',
    'ilan': 'İlan', 'soru': 'Soru-Cevap', 'kayip': 'Kayıp Eşya'
}

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')
ADMIN_PASSWORD = hashlib.sha256('admin123'.encode()).hexdigest()

# ── E-POSTA AYARLARI ──────────────────────────────
EMAIL_GONDEREN  = 'burakadsiz96@gmail.com'   # gönderen gmail
EMAIL_SIFRE     = 'pnmt xoyv zqvx juap'       # Gmail uygulama şifresi
EMAIL_ALICI     = 'burakadsiz96@gmail.com'   # bildirim gidecek adres
# ──────────────────────────────────────────────────

def mail_gonder(konu, icerik):
    """Arka planda e-posta gönderir, hata olsa bile siteyi durdurmaz."""
    def _gonder():
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = konu
            msg['From']    = EMAIL_GONDEREN
            msg['To']      = EMAIL_ALICI
            msg.attach(MIMEText(icerik, 'html', 'utf-8'))
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
                s.login(EMAIL_GONDEREN, EMAIL_SIFRE)
                s.sendmail(EMAIL_GONDEREN, EMAIL_ALICI, msg.as_string())
        except Exception as e:
            print(f'[Mail hatası] {e}')
    threading.Thread(target=_gonder, daemon=True).start()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS itiraflar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            baslik TEXT NOT NULL,
            icerik TEXT NOT NULL,
            nick TEXT DEFAULT 'Anonim',
            kategori TEXT DEFAULT 'itiraf',
            tarih DATETIME DEFAULT CURRENT_TIMESTAMP,
            onaylandi INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS yorumlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            itiraf_id INTEGER NOT NULL,
            nick TEXT DEFAULT 'Anonim',
            yorum TEXT NOT NULL,
            tarih DATETIME DEFAULT CURRENT_TIMESTAMP,
            onaylandi INTEGER DEFAULT 0,
            FOREIGN KEY (itiraf_id) REFERENCES itiraflar(id)
        );

        CREATE TABLE IF NOT EXISTS reaksiyonlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            itiraf_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            ip TEXT,
            UNIQUE(itiraf_id, ip, emoji)
        );
    ''')
    # Örnek itiraf ekle
    cursor = conn.execute("SELECT COUNT(*) FROM itiraflar")
    if cursor.fetchone()[0] == 0:
        conn.execute("""
            INSERT INTO itiraflar (baslik, icerik, nick, kategori)
            VALUES ('Hoş Geldiniz!', 'Medipol İtiraf Ediyor sitesine hoş geldiniz! Anonim olarak itiraflarınızı paylaşabilirsiniz.', 'Admin', 'itiraf')
        """)
    # Migration: yorumlar tablosuna onaylandi ekle
    try:
        conn.execute("ALTER TABLE yorumlar ADD COLUMN onaylandi INTEGER DEFAULT 0")
        conn.execute("UPDATE yorumlar SET onaylandi = 1")
        conn.commit()
    except:
        pass
    # Migration: itiraflar tablosuna sabitlendi ekle
    try:
        conn.execute("ALTER TABLE itiraflar ADD COLUMN sabitlendi INTEGER DEFAULT 0")
        conn.commit()
    except:
        pass
    conn.commit()
    conn.close()

@app.route('/')
def index():
    kategori = request.args.get('kategori', 'itiraf')
    sayfa = int(request.args.get('sayfa', 1))
    limit = 10
    offset = (sayfa - 1) * limit

    conn = get_db()

    # "itiraf" sekmesi tüm itiraf alt kategorilerini gösterir
    if kategori == 'itiraf':
        placeholders = ','.join(['?' for _ in ITIRAF_KATEGORILER])
        itiraflar = conn.execute(f"""
            SELECT i.*, COUNT(y.id) as yorum_sayisi
            FROM itiraflar i
            LEFT JOIN yorumlar y ON y.itiraf_id = i.id
            WHERE i.kategori IN ({placeholders}) AND i.onaylandi = 1
            GROUP BY i.id
            ORDER BY i.sabitlendi DESC, i.tarih DESC
            LIMIT ? OFFSET ?
        """, ITIRAF_KATEGORILER + [limit, offset]).fetchall()
        toplam = conn.execute(f"SELECT COUNT(*) FROM itiraflar WHERE kategori IN ({placeholders}) AND onaylandi = 1", ITIRAF_KATEGORILER).fetchone()[0]
    else:
        itiraflar = conn.execute("""
            SELECT i.*, COUNT(y.id) as yorum_sayisi
            FROM itiraflar i
            LEFT JOIN yorumlar y ON y.itiraf_id = i.id
            WHERE i.kategori = ? AND i.onaylandi = 1
            GROUP BY i.id
            ORDER BY i.sabitlendi DESC, i.tarih DESC
            LIMIT ? OFFSET ?
        """, (kategori, limit, offset)).fetchall()
        toplam = conn.execute("SELECT COUNT(*) FROM itiraflar WHERE kategori = ? AND onaylandi = 1", (kategori,)).fetchone()[0]

    yedi_gun_once = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    populer = conn.execute("""
        SELECT i.id, i.baslik, COUNT(y.id) as yorum_sayisi
        FROM itiraflar i
        LEFT JOIN yorumlar y ON y.itiraf_id = i.id
        WHERE i.tarih >= ? AND i.onaylandi = 1
        GROUP BY i.id
        ORDER BY yorum_sayisi DESC
        LIMIT 10
    """, (yedi_gun_once,)).fetchall()

    yeni_yorumlar = conn.execute("""
        SELECT y.nick, y.yorum, y.tarih, i.baslik, i.id as itiraf_id
        FROM yorumlar y
        JOIN itiraflar i ON i.id = y.itiraf_id
        WHERE y.onaylandi = 1
        ORDER BY y.tarih DESC
        LIMIT 8
    """).fetchall()

    conn.close()

    toplam_sayfa = (toplam + limit - 1) // limit

    return render_template('index.html',
        itiraflar=itiraflar,
        kategori=kategori,
        sayfa=sayfa,
        toplam_sayfa=toplam_sayfa,
        populer=populer,
        yeni_yorumlar=yeni_yorumlar,
        kategori_etiketler=KATEGORI_ETIKETLER
    )

@app.route('/itiraf/<int:id>')
def itiraf_detay(id):
    conn = get_db()
    itiraf = conn.execute("SELECT * FROM itiraflar WHERE id = ? AND onaylandi = 1", (id,)).fetchone()
    if not itiraf:
        return redirect(url_for('index'))

    yorumlar = conn.execute("""
        SELECT * FROM yorumlar WHERE itiraf_id = ? AND onaylandi = 1 ORDER BY tarih ASC
    """, (id,)).fetchall()

    reaksiyonlar = conn.execute("""
        SELECT emoji, COUNT(*) as sayi FROM reaksiyonlar WHERE itiraf_id = ? GROUP BY emoji
    """, (id,)).fetchall()

    populer = conn.execute("""
        SELECT i.id, i.baslik, COUNT(y.id) as yorum_sayisi
        FROM itiraflar i
        LEFT JOIN yorumlar y ON y.itiraf_id = i.id
        WHERE i.onaylandi = 1
        GROUP BY i.id
        ORDER BY yorum_sayisi DESC
        LIMIT 10
    """).fetchall()

    yeni_yorumlar = conn.execute("""
        SELECT y.nick, y.yorum, y.tarih, i.baslik, i.id as itiraf_id
        FROM yorumlar y
        JOIN itiraflar i ON i.id = y.itiraf_id
        WHERE y.onaylandi = 1
        ORDER BY y.tarih DESC
        LIMIT 8
    """).fetchall()

    conn.close()
    return render_template('detay.html',
        itiraf=itiraf,
        yorumlar=yorumlar,
        reaksiyonlar=reaksiyonlar,
        populer=populer,
        yeni_yorumlar=yeni_yorumlar
    )

@app.route('/itiraf-et', methods=['GET', 'POST'])
def itiraf_et():
    if request.method == 'GET':
        return render_template('itiraf_et.html', kategori_etiketler=KATEGORI_ETIKETLER)

    baslik = request.form.get('baslik', '').strip()
    icerik = request.form.get('icerik', '').strip()
    nick = request.form.get('nick', 'Anonim').strip() or 'Anonim'
    kategori = request.form.get('kategori', 'itiraf')

    if not baslik or not icerik:
        return redirect(url_for('itiraf_et'))

    conn = get_db()
    conn.execute("INSERT INTO itiraflar (baslik, icerik, nick, kategori, onaylandi) VALUES (?, ?, ?, ?, 0)",
                 (baslik, icerik, nick, kategori))
    conn.commit()
    conn.close()

    # Admin'e bildirim maili gönder
    mail_gonder(
        f'🤫 Yeni İtiraf Bekleniyor: {baslik}',
        f'''
        <h2>Yeni bir itiraf onay bekliyor!</h2>
        <table style="border-collapse:collapse; width:100%; font-family:sans-serif;">
            <tr><td style="padding:8px; font-weight:bold;">Başlık</td><td style="padding:8px;">{baslik}</td></tr>
            <tr style="background:#f9f9f9"><td style="padding:8px; font-weight:bold;">Nick</td><td style="padding:8px;">{nick}</td></tr>
            <tr><td style="padding:8px; font-weight:bold;">Kategori</td><td style="padding:8px;">{kategori}</td></tr>
            <tr style="background:#f9f9f9"><td style="padding:8px; font-weight:bold;">İçerik</td><td style="padding:8px;">{icerik[:300]}</td></tr>
        </table>
        <br>
        <a href="http://localhost:5000/admin/panel" style="background:#1a2b4a; color:#fff; padding:10px 20px; border-radius:6px; text-decoration:none;">
            Admin Paneline Git →
        </a>
        '''
    )

    return redirect(url_for('itiraf_et') + '?itiraf=beklemede')

@app.route('/yorum-yap', methods=['POST'])
def yorum_yap():
    itiraf_id = request.form.get('itiraf_id')
    nick = request.form.get('nick', 'Anonim').strip() or 'Anonim'
    yorum = request.form.get('yorum', '').strip()

    if not yorum or not itiraf_id:
        return redirect(url_for('index'))

    conn = get_db()
    conn.execute("INSERT INTO yorumlar (itiraf_id, nick, yorum, onaylandi) VALUES (?, ?, ?, 0)",
                 (itiraf_id, nick, yorum))
    itiraf_baslik = conn.execute("SELECT baslik FROM itiraflar WHERE id = ?", (itiraf_id,)).fetchone()
    conn.commit()
    conn.close()

    baslik_str = itiraf_baslik['baslik'] if itiraf_baslik else '?'
    mail_gonder(
        f'💬 Yeni Yorum Onay Bekliyor — {baslik_str}',
        f'''
        <h2>Yeni bir yorum onay bekliyor!</h2>
        <table style="border-collapse:collapse; width:100%; font-family:sans-serif;">
            <tr><td style="padding:8px; font-weight:bold;">İtiraf</td><td style="padding:8px;">{baslik_str}</td></tr>
            <tr style="background:#f9f9f9"><td style="padding:8px; font-weight:bold;">Nick</td><td style="padding:8px;">{nick}</td></tr>
            <tr><td style="padding:8px; font-weight:bold;">Yorum</td><td style="padding:8px;">{yorum[:300]}</td></tr>
        </table>
        <br>
        <a href="http://localhost:5000/admin/panel?sekme=yorumlar" style="background:#1a2b4a; color:#fff; padding:10px 20px; border-radius:6px; text-decoration:none;">
            Yorumları Yönet →
        </a>
        '''
    )

    return redirect(url_for('itiraf_detay', id=itiraf_id) + '?yorum=beklemede')

@app.route('/reaksiyon', methods=['POST'])
def reaksiyon():
    data = request.get_json()
    itiraf_id = data.get('itiraf_id')
    emoji = data.get('emoji')
    ip = request.remote_addr

    conn = get_db()
    try:
        conn.execute("INSERT INTO reaksiyonlar (itiraf_id, emoji, ip) VALUES (?, ?, ?)",
                     (itiraf_id, emoji, ip))
        conn.commit()
        result = {'status': 'added'}
    except sqlite3.IntegrityError:
        conn.execute("DELETE FROM reaksiyonlar WHERE itiraf_id = ? AND ip = ? AND emoji = ?",
                     (itiraf_id, ip, emoji))
        conn.commit()
        result = {'status': 'removed'}

    sayi = conn.execute("SELECT COUNT(*) FROM reaksiyonlar WHERE itiraf_id = ? AND emoji = ?",
                        (itiraf_id, emoji)).fetchone()[0]
    conn.close()
    result['sayi'] = sayi
    return jsonify(result)

@app.route('/ara')
def ara():
    q = request.args.get('q', '').strip()
    if not q:
        return redirect(url_for('index'))

    conn = get_db()
    itiraflar = conn.execute("""
        SELECT i.*, COUNT(y.id) as yorum_sayisi
        FROM itiraflar i
        LEFT JOIN yorumlar y ON y.itiraf_id = i.id
        WHERE (i.baslik LIKE ? OR i.icerik LIKE ?) AND i.onaylandi = 1
        GROUP BY i.id
        ORDER BY i.tarih DESC
    """, (f'%{q}%', f'%{q}%')).fetchall()

    populer = conn.execute("""
        SELECT i.id, i.baslik, COUNT(y.id) as yorum_sayisi
        FROM itiraflar i
        LEFT JOIN yorumlar y ON y.itiraf_id = i.id
        WHERE i.onaylandi = 1
        GROUP BY i.id
        ORDER BY yorum_sayisi DESC
        LIMIT 10
    """).fetchall()

    yeni_yorumlar = conn.execute("""
        SELECT y.nick, y.yorum, y.tarih, i.baslik, i.id as itiraf_id
        FROM yorumlar y
        JOIN itiraflar i ON i.id = y.itiraf_id
        WHERE y.onaylandi = 1
        ORDER BY y.tarih DESC
        LIMIT 8
    """).fetchall()

    conn.close()
    return render_template('ara.html', itiraflar=itiraflar, q=q, populer=populer, yeni_yorumlar=yeni_yorumlar)

@app.route('/sss')
def sss():
    return render_template('sss.html')

@app.route('/iletisim')
def iletisim():
    return render_template('iletisim.html')

# Admin routes
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_panel'))
        return render_template('admin_login.html', hata='Hatalı şifre!')
    return render_template('admin_login.html')

@app.route('/admin/panel')
def admin_panel():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    sekme = request.args.get('sekme', 'itiraflar')
    filtre = request.args.get('filtre', 'hepsi')
    conn = get_db()

    # İstatistikler
    stats = {
        'toplam_itiraf': conn.execute("SELECT COUNT(*) FROM itiraflar").fetchone()[0],
        'bekleyen_itiraf': conn.execute("SELECT COUNT(*) FROM itiraflar WHERE onaylandi = 0").fetchone()[0],
        'toplam_yorum': conn.execute("SELECT COUNT(*) FROM yorumlar").fetchone()[0],
        'bekleyen_yorum': conn.execute("SELECT COUNT(*) FROM yorumlar WHERE onaylandi = 0").fetchone()[0],
        'bugun_itiraf': conn.execute("SELECT COUNT(*) FROM itiraflar WHERE DATE(tarih) = DATE('now')").fetchone()[0],
    }

    # İtiraflar (filtreli)
    if filtre == 'bekleyen':
        itiraflar = conn.execute("SELECT * FROM itiraflar WHERE onaylandi = 0 ORDER BY tarih DESC").fetchall()
    elif filtre == 'sabitli':
        itiraflar = conn.execute("SELECT * FROM itiraflar WHERE sabitlendi = 1 ORDER BY tarih DESC").fetchall()
    else:
        itiraflar = conn.execute("SELECT * FROM itiraflar ORDER BY sabitlendi DESC, tarih DESC").fetchall()

    yorumlar = conn.execute("""
        SELECT y.*, i.baslik as itiraf_baslik
        FROM yorumlar y
        JOIN itiraflar i ON i.id = y.itiraf_id
        ORDER BY y.onaylandi ASC, y.tarih DESC
    """).fetchall()
    conn.close()
    return render_template('admin_panel.html', itiraflar=itiraflar, yorumlar=yorumlar,
                           sekme=sekme, filtre=filtre, stats=stats,
                           bekleyen_yorum=stats['bekleyen_yorum'])

@app.route('/admin/sil/<int:id>')
def admin_sil(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    conn = get_db()
    conn.execute("DELETE FROM itiraflar WHERE id = ?", (id,))
    conn.execute("DELETE FROM yorumlar WHERE itiraf_id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/onayla/<int:id>')
def admin_onayla(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    conn = get_db()
    itiraf = conn.execute("SELECT onaylandi FROM itiraflar WHERE id = ?", (id,)).fetchone()
    yeni_durum = 0 if itiraf['onaylandi'] == 1 else 1
    conn.execute("UPDATE itiraflar SET onaylandi = ? WHERE id = ?", (yeni_durum, id))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/sabitle/<int:id>')
def admin_sabitle(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    conn = get_db()
    itiraf = conn.execute("SELECT sabitlendi FROM itiraflar WHERE id = ?", (id,)).fetchone()
    yeni = 0 if itiraf['sabitlendi'] == 1 else 1
    conn.execute("UPDATE itiraflar SET sabitlendi = ? WHERE id = ?", (yeni, id))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/toplu-onayla', methods=['POST'])
def admin_toplu_onayla():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    ids = request.form.getlist('secili_ids')
    if ids:
        conn = get_db()
        for itiraf_id in ids:
            conn.execute("UPDATE itiraflar SET onaylandi = 1 WHERE id = ?", (itiraf_id,))
        conn.commit()
        conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/yorum-onayla/<int:id>')
def admin_yorum_onayla(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    conn = get_db()
    yorum = conn.execute("SELECT onaylandi FROM yorumlar WHERE id = ?", (id,)).fetchone()
    yeni = 0 if yorum['onaylandi'] == 1 else 1
    conn.execute("UPDATE yorumlar SET onaylandi = ? WHERE id = ?", (yeni, id))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel', sekme='yorumlar'))

@app.route('/admin/yorum-sil/<int:id>')
def admin_yorum_sil(id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    conn = get_db()
    conn.execute("DELETE FROM yorumlar WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel', sekme='yorumlar'))

@app.route('/admin/cikis')
def admin_cikis():
    session.pop('admin', None)
    return redirect(url_for('index'))

import os as _os
import subprocess as _subprocess

DEPLOY_TOKEN = 'medipol-deploy-2026'

@app.route('/deploy/<token>')
def deploy_hook(token):
    if token != DEPLOY_TOKEN:
        return 'Yetkisiz', 403
    try:
        result = _subprocess.check_output(
            ['git', 'pull'],
            cwd=_os.path.dirname(__file__),
            stderr=_subprocess.STDOUT
        ).decode()
        return f'OK\n{result}', 200
    except Exception as e:
        return f'Hata: {e}', 500

init_db()
if __name__ == '__main__':
    port = int(_os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
