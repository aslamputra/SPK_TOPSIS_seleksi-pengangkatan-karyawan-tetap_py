from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import numpy as np
import os

app = Flask(__name__)
app.secret_key = 'secret'
DATABASE = 'database.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def dashboard():
    conn = get_db()

    # Ambil data alternatif dan kriteria
    alt = conn.execute('SELECT * FROM alternatif').fetchall()
    krit = conn.execute('SELECT * FROM kriteria').fetchall()
    alt_count = len(alt)
    krit_count = len(krit)

    # Buat matriks nilai
    matrix = []
    alt_names = []
    for a in alt:
        row = []
        alt_names.append(a['nama_alternatif'])
        for k in krit:
            val = conn.execute(
                'SELECT nilai FROM nilai WHERE id_alternatif=? AND id_kriteria=?',
                (a['id'], k['id'])
            ).fetchone()
            row.append(val['nilai'] if val else 0)
        matrix.append(row)

    result = []
    if matrix and matrix[0]:
        import numpy as np
        X = np.array(matrix, dtype=float)

        # Normalisasi
        R = np.zeros_like(X)
        for j in range(len(krit)):
            col = X[:, j]
            norm = np.sqrt(np.sum(col ** 2))
            R[:, j] = col / norm if norm != 0 else 0

        # Bobot
        W = np.array([k['bobot'] for k in krit])
        V = R * W

        # Ideal positif dan negatif sesuai atribut
        A_plus = np.zeros(len(krit))
        A_min = np.zeros(len(krit))
        for j, k in enumerate(krit):
            if k['atribut'].lower() == 'benefit':
                A_plus[j] = np.max(V[:, j])
                A_min[j] = np.min(V[:, j])
            else:  # cost
                A_plus[j] = np.min(V[:, j])
                A_min[j] = np.max(V[:, j])

        # Hitung jarak dan skor
        D_plus = np.sqrt(np.sum((V - A_plus) ** 2, axis=1))
        D_min = np.sqrt(np.sum((V - A_min) ** 2, axis=1))
        scores = D_min / (D_plus + D_min)

        result = sorted(zip(alt_names, scores), key=lambda x: x[1], reverse=True)

    conn.close()
    return render_template(
        'dashboard.html',
        alt_count=alt_count,
        krit_count=krit_count,
        result=result,
        kriteria=krit
    )

@app.route('/kriteria')
def kriteria():
    conn = get_db()
    data = conn.execute('SELECT * FROM kriteria').fetchall()
    conn.close()
    return render_template('kriteria.html', data=data)

@app.route('/kriteria/add', methods=['POST'])
def kriteria_add():
    nama = request.form['nama']
    bobot = float(request.form['bobot'])
    atribut = request.form['atribut']
    conn = get_db()
    total_bobot = conn.execute('SELECT SUM(bobot) FROM kriteria').fetchone()[0] or 0.0
    if total_bobot + bobot > 1.0:
        flash('Total bobot melebihi batas maksimum 1.00')
        conn.close()
        return redirect(url_for('kriteria'))
    conn.execute('INSERT INTO kriteria (nama_kriteria, bobot, atribut) VALUES (?, ?, ?)', (nama, bobot, atribut))
    conn.commit()
    conn.close()
    return redirect(url_for('kriteria'))

@app.route('/kriteria/edit/<int:id>', methods=['POST'])
def kriteria_edit(id):
    nama = request.form['nama']
    bobot = float(request.form['bobot'])
    atribut = request.form['atribut']
    conn = get_db()
    total_bobot = conn.execute('SELECT SUM(bobot) FROM kriteria WHERE id != ?', (id,)).fetchone()[0] or 0.0
    if total_bobot + bobot > 1.0:
        flash('Total bobot melebihi batas maksimum 1.00')
        conn.close()
        return redirect(url_for('kriteria'))
    conn.execute('UPDATE kriteria SET nama_kriteria=?, bobot=?, atribut=? WHERE id=?', (nama, bobot, atribut, id))
    conn.commit()
    conn.close()
    return redirect(url_for('kriteria'))

@app.route('/kriteria/delete/<int:id>')
def kriteria_delete(id):
    conn = get_db()
    conn.execute('DELETE FROM kriteria WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('kriteria'))

@app.route('/alternatif')
def alternatif():
    conn = get_db()
    data = conn.execute('SELECT * FROM alternatif').fetchall()
    conn.close()
    return render_template('alternatif.html', data=data)

@app.route('/alternatif/add', methods=['POST'])
def alternatif_add():
    nama = request.form['nama']
    conn = get_db()
    conn.execute('INSERT INTO alternatif (nama_alternatif) VALUES (?)', (nama,))
    conn.commit()
    conn.close()
    return redirect(url_for('alternatif'))

@app.route('/alternatif/edit/<int:id>', methods=['POST'])
def alternatif_edit(id):
    nama = request.form['nama']
    conn = get_db()
    conn.execute('UPDATE alternatif SET nama_alternatif=? WHERE id=?', (nama, id))
    conn.commit()
    conn.close()
    return redirect(url_for('alternatif'))

@app.route('/alternatif/delete/<int:id>')
def alternatif_delete(id):
    conn = get_db()
    conn.execute('DELETE FROM alternatif WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('alternatif'))

@app.route('/nilai')
def nilai():
    conn = get_db()
    hasil = conn.execute('''
        SELECT a.id as id_alternatif, a.nama_alternatif, k.nama_kriteria, n.nilai
        FROM nilai n
        JOIN alternatif a ON n.id_alternatif = a.id
        JOIN kriteria k ON n.id_kriteria = k.id
        ORDER BY a.nama_alternatif, k.nama_kriteria
    ''').fetchall()
    conn.close()

    # Group by alternatif
    grouped = {}
    for row in hasil:
        alt_id = row['id_alternatif']
        if alt_id not in grouped:
            grouped[alt_id] = {
                'id_alternatif': alt_id,
                'nama_alternatif': row['nama_alternatif'],
                'nilai_list': []
            }
        grouped[alt_id]['nilai_list'].append({
            'nama_kriteria': row['nama_kriteria'],
            'nilai': row['nilai']
        })

    return render_template('nilai.html', grouped=grouped.values())

@app.route('/nilai/add/form')
def nilai_add_form():
    conn = get_db()
    alternatif = conn.execute('SELECT * FROM alternatif').fetchall()
    kriteria = conn.execute('SELECT * FROM kriteria').fetchall()
    conn.close()
    return render_template('nilai_add.html', alternatif=alternatif, kriteria=kriteria)


@app.route('/nilai/add', methods=['POST'])
def nilai_add():
    id_alt = int(request.form['id_alternatif'])  # Pastikan ini dikirim benar
    conn = get_db()
    kriteria = conn.execute('SELECT * FROM kriteria').fetchall()

    for k in kriteria:
        val = float(request.form.get(f'nilai_{k["id"]}', 0))
        conn.execute('INSERT INTO nilai (id_alternatif, id_kriteria, nilai) VALUES (?, ?, ?)',
                     (id_alt, k['id'], val))

    conn.commit()
    conn.close()
    return redirect(url_for('nilai'))

@app.route('/nilai/edit/<int:id>', methods=['GET', 'POST'])
def nilai_edit(id):
    conn = get_db()
    if request.method == 'POST':
        kriteria = conn.execute('SELECT * FROM kriteria').fetchall()
        for k in kriteria:
            val = float(request.form.get(f'nilai_{k["id"]}', 0))
            exists = conn.execute('SELECT 1 FROM nilai WHERE id_alternatif=? AND id_kriteria=?', (id, k['id'])).fetchone()
            if exists:
                conn.execute('UPDATE nilai SET nilai=? WHERE id_alternatif=? AND id_kriteria=?', (val, id, k['id']))
            else:
                conn.execute('INSERT INTO nilai (id_alternatif, id_kriteria, nilai) VALUES (?, ?, ?)', (id, k['id'], val))
        conn.commit()
        conn.close()
        return redirect(url_for('nilai'))
    else:
        alternatif = conn.execute('SELECT * FROM alternatif WHERE id=?', (id,)).fetchone()
        nilai_data = conn.execute('''
            SELECT k.id AS id_kriteria, k.nama_kriteria, IFNULL(n.nilai, 0) AS nilai
            FROM kriteria k
            LEFT JOIN nilai n ON k.id = n.id_kriteria AND n.id_alternatif = ?
        ''', (id,)).fetchall()
        conn.close()
        return render_template('nilai_edit.html', alternatif=alternatif, nilai_list=nilai_data)


@app.route('/nilai/delete/<int:id>')
def nilai_delete(id):
    conn = get_db()
    conn.execute('DELETE FROM nilai WHERE id_alternatif=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('nilai'))

@app.route('/ranking')
def ranking():
    conn = get_db()
    alt = conn.execute('SELECT * FROM alternatif').fetchall()
    krit = conn.execute('SELECT * FROM kriteria').fetchall()
    matrix = []
    for a in alt:
        row = []
        for k in krit:
            val = conn.execute('SELECT nilai FROM nilai WHERE id_alternatif=? AND id_kriteria=?',
                               (a['id'], k['id'])).fetchone()
            row.append(val['nilai'] if val else 0)
        matrix.append(row)
    conn.close()

    if not matrix or not matrix[0]:
        return render_template('ranking.html', result=[])

    import numpy as np
    X = np.array(matrix, dtype=float)

    # Normalisasi
    R = np.zeros_like(X)
    for j in range(len(krit)):
        col = X[:, j]
        norm = np.sqrt(np.sum(col**2))
        R[:, j] = col / norm if norm != 0 else 0

    # Pembobotan
    W = np.array([k['bobot'] for k in krit])
    V = R * W

    # Ideal positif dan negatif tergantung atribut
    A_plus = np.zeros(len(krit))
    A_min = np.zeros(len(krit))
    for j, k in enumerate(krit):
        if k['atribut'].lower() == 'benefit':
            A_plus[j] = np.max(V[:, j])
            A_min[j] = np.min(V[:, j])
        else:  # cost
            A_plus[j] = np.min(V[:, j])  # cost ideal lebih rendah
            A_min[j] = np.max(V[:, j])  # cost ideal lebih tinggi

    # Jarak ke solusi ideal
    D_plus = np.sqrt(np.sum((V - A_plus) ** 2, axis=1))
    D_min = np.sqrt(np.sum((V - A_min) ** 2, axis=1))

    # Nilai preferensi
    scores = D_min / (D_plus + D_min)
    ranking_result = sorted(zip([a['nama_alternatif'] for a in alt], scores), key=lambda x: x[1], reverse=True)

    return render_template('ranking.html', result=ranking_result)


def init_db():
    if not os.path.exists(DATABASE):
        conn = get_db()
        conn.execute('''CREATE TABLE IF NOT EXISTS kriteria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_kriteria TEXT,
            bobot REAL,
            atribut TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS alternatif (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_alternatif TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS nilai (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_alternatif INTEGER,
            id_kriteria INTEGER,
            nilai REAL)''')
        conn.commit()
        conn.close()

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
