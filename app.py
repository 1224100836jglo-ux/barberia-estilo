import hashlib
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

import pymysql
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
csrf = CSRFProtect(app)


@app.errorhandler(CSRFError)
def error_csrf(e):
    flash('El formulario expiró o no es válido. Intenta de nuevo.', 'error')
    return redirect(request.referrer or url_for('login'))


def db():
    return pymysql.connect(
        host=config.DB_HOST, user=config.DB_USER, password=config.DB_PASSWORD,
        database=config.DB_NAME, charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
    )


APERTURA, CIERRE, PASO = 10 * 60, 20 * 60, 30   # 10:00 a 20:00, bloques de 30 min


def minutos(td):
    """Convierte el TIME de MySQL (timedelta) a minutos."""
    return int(td.total_seconds() // 60)


def a_hhmm(td):
    m = minutos(td)
    return f'{m // 60:02d}:{m % 60:02d}'


def calcular_horas(cur, barbero_id, fecha, duracion):
    """Devuelve los bloques del día y cuáles están libres para ese barbero y duración."""
    cur.execute(
        """SELECT c.hora, s.duracion_min FROM citas c
           JOIN servicios s ON s.id = c.servicio_id
           WHERE c.barbero_id = %s AND c.fecha = %s AND c.estado <> 'Cancelada'""",
        (barbero_id, fecha),
    )
    ocupadas = [(minutos(r['hora']), minutos(r['hora']) + r['duracion_min']) for r in cur.fetchall()]

    ahora = None
    if fecha == date.today():
        n = datetime.now()
        ahora = n.hour * 60 + n.minute

    resultado = []
    for ini in range(APERTURA, CIERRE, PASO):
        fin = ini + duracion
        libre = fin <= CIERRE
        if libre and any(ini < o_fin and fin > o_ini for o_ini, o_fin in ocupadas):
            libre = False
        if libre and ahora is not None and ini <= ahora:
            libre = False
        resultado.append({'hora': f'{ini // 60:02d}:{ini % 60:02d}', 'libre': libre})
    return resultado


def requiere_rol(rol):
    """Protege una ruta: exige sesión iniciada y el rol indicado (se consulta en la base)."""
    def decorador(f):
        @wraps(f)
        def envoltura(*args, **kwargs):
            if 'usuario_id' not in session:
                return redirect(url_for('login'))
            with db() as con, con.cursor() as cur:
                cur.execute('SELECT rol FROM usuarios WHERE id = %s', (session['usuario_id'],))
                u = cur.fetchone()
            if not u:
                session.clear()
                return redirect(url_for('login'))
            session['rol'] = u['rol']
            if u['rol'] != rol:
                return redirect(url_for('inicio'))
            return f(*args, **kwargs)
        return envoltura
    return decorador


# ------------------------- SESIÓN -------------------------
@app.route('/')
def inicio():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('panel' if session['rol'] == 'admin' else 'agendar'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form.get('correo', '').strip().lower()
        password = request.form.get('password', '')
        with db() as con, con.cursor() as cur:
            cur.execute('SELECT * FROM usuarios WHERE correo = %s', (correo,))
            u = cur.fetchone()
        if u and check_password_hash(u['password_hash'], password):
            session.clear()
            session['usuario_id'] = u['id']
            session['nombre'] = u['nombre']
            session['rol'] = u['rol']
            return redirect(url_for('inicio'))
        flash('Correo o contraseña incorrectos.', 'error')
    return render_template('login.html')


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        telefono = request.form.get('telefono', '').strip()
        correo = request.form.get('correo', '').strip().lower()
        p1 = request.form.get('pass', '')
        p2 = request.form.get('pass2', '')

        if not (nombre and telefono and correo and p1):
            flash('Completa todos los campos.', 'error')
        elif len(p1) < 8:
            flash('La contraseña debe tener al menos 8 caracteres.', 'error')
        elif p1 != p2:
            flash('Las contraseñas no coinciden.', 'error')
        else:
            try:
                with db() as con, con.cursor() as cur:
                    cur.execute(
                        'INSERT INTO usuarios (nombre, telefono, correo, password_hash) VALUES (%s, %s, %s, %s)',
                        (nombre, telefono, correo, generate_password_hash(p1)),
                    )
                    con.commit()
                flash('Cuenta creada. Ya puedes iniciar sesión.', 'ok')
                return redirect(url_for('login'))
            except pymysql.err.IntegrityError:
                flash('Ese correo ya está registrado.', 'error')
    return render_template('registro.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))
# ------------------------- RECUPERAR CONTRASEÑA -------------------------
VIGENCIA_TOKEN_MIN = 30


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    if request.method == 'POST':
        correo = request.form.get('correo', '').strip().lower()
        with db() as con, con.cursor() as cur:
            cur.execute('SELECT id FROM usuarios WHERE correo = %s', (correo,))
            u = cur.fetchone()
            if u:
                token = secrets.token_urlsafe(32)
                cur.execute('DELETE FROM reset_tokens WHERE usuario_id = %s', (u['id'],))
                cur.execute(
                    'INSERT INTO reset_tokens (usuario_id, token_hash, expira) VALUES (%s, %s, %s)',
                    (u['id'], hash_token(token), datetime.now() + timedelta(minutes=VIGENCIA_TOKEN_MIN)),
                )
                con.commit()
                enlace = url_for('restablecer', token=token, _external=True)
                # Simula el envío del correo: el enlace se imprime en la terminal del servidor
                print(f'\n[RECUPERACIÓN] Enlace para {correo} (vence en {VIGENCIA_TOKEN_MIN} min):\n{enlace}\n', flush=True)
        # Misma respuesta exista o no el correo, para no revelar qué cuentas existen
        flash('Si el correo está registrado, se generó un enlace de recuperación.', 'ok')
        return redirect(url_for('login'))
    return render_template('recuperar.html')


@app.route('/restablecer/<token>', methods=['GET', 'POST'])
def restablecer(token):
    with db() as con, con.cursor() as cur:
        cur.execute(
            'SELECT usuario_id FROM reset_tokens WHERE token_hash = %s AND expira > %s',
            (hash_token(token), datetime.now()),
        )
        t = cur.fetchone()
        if not t:
            flash('El enlace no es válido o ya venció. Solicita uno nuevo.', 'error')
            return redirect(url_for('recuperar'))

        if request.method == 'POST':
            p1 = request.form.get('pass', '')
            p2 = request.form.get('pass2', '')
            if len(p1) < 8:
                flash('La contraseña debe tener al menos 8 caracteres.', 'error')
            elif p1 != p2:
                flash('Las contraseñas no coinciden.', 'error')
            else:
                cur.execute('UPDATE usuarios SET password_hash = %s WHERE id = %s',
                            (generate_password_hash(p1), t['usuario_id']))
                cur.execute('DELETE FROM reset_tokens WHERE usuario_id = %s', (t['usuario_id'],))
                con.commit()
                flash('Contraseña actualizada. Ya puedes iniciar sesión.', 'ok')
                return redirect(url_for('login'))
    return render_template('restablecer.html')
# ------------------------- CLIENTE -------------------------
@app.route('/agendar', methods=['GET', 'POST'])
@requiere_rol('cliente')
def agendar():
    with db() as con, con.cursor() as cur:
        cur.execute('SELECT * FROM servicios WHERE activo = 1 ORDER BY id')
        servicios = cur.fetchall()
        cur.execute("SELECT id, nombre FROM usuarios WHERE rol = 'admin' ORDER BY nombre")
        barberos = cur.fetchall()

        if request.method == 'POST':
            try:
                servicio_id = int(request.form.get('servicio', ''))
                barbero_id = int(request.form.get('barbero', ''))
                fecha = date.fromisoformat(request.form.get('fecha', ''))
            except ValueError:
                flash('Datos inválidos. Intenta de nuevo.', 'error')
                return redirect(url_for('agendar'))

            hora = request.form.get('hora', '')
            servicio = next((s for s in servicios if s['id'] == servicio_id), None)
            barbero = next((b for b in barberos if b['id'] == barbero_id), None)
            if not servicio or not barbero or fecha < date.today():
                flash('Revisa el servicio, el barbero y la fecha.', 'error')
                return redirect(url_for('agendar'))

            libres = {h['hora'] for h in calcular_horas(cur, barbero_id, fecha, servicio['duracion_min']) if h['libre']}
            if hora not in libres:
                flash('Ese horario ya no está disponible. Elige otro.', 'error')
                return redirect(url_for('agendar'))

            cur.execute(
                'INSERT INTO citas (cliente_id, barbero_id, servicio_id, fecha, hora) VALUES (%s, %s, %s, %s, %s)',
                (session['usuario_id'], barbero_id, servicio_id, fecha, hora),
            )
            con.commit()
            flash('Cita agendada. Queda pendiente de confirmación.', 'ok')
            return redirect(url_for('mis_citas'))

    return render_template('agendar.html', servicios=servicios, barberos=barberos, hoy=date.today().isoformat())


@app.route('/api/horas')
@requiere_rol('cliente')
def api_horas():
    try:
        barbero_id = int(request.args.get('barbero', ''))
        servicio_id = int(request.args.get('servicio', ''))
        fecha = date.fromisoformat(request.args.get('fecha', ''))
    except ValueError:
        return jsonify([])
    with db() as con, con.cursor() as cur:
        cur.execute('SELECT duracion_min FROM servicios WHERE id = %s AND activo = 1', (servicio_id,))
        s = cur.fetchone()
        if not s:
            return jsonify([])
        return jsonify(calcular_horas(cur, barbero_id, fecha, s['duracion_min']))


@app.route('/mis-citas')
@requiere_rol('cliente')
def mis_citas():
    with db() as con, con.cursor() as cur:
        cur.execute(
            """SELECT c.id, c.fecha, c.hora, c.estado, s.nombre AS servicio, s.precio, u.nombre AS barbero
               FROM citas c
               JOIN servicios s ON s.id = c.servicio_id
               JOIN usuarios u ON u.id = c.barbero_id
               WHERE c.cliente_id = %s
               ORDER BY c.fecha DESC, c.hora DESC""",
            (session['usuario_id'],),
        )
        citas = cur.fetchall()
    for c in citas:
        c['hora_txt'] = a_hhmm(c['hora'])
    return render_template('mis_citas.html', citas=citas)


@app.route('/mis-citas/<int:cita_id>/cancelar', methods=['POST'])
@requiere_rol('cliente')
def cancelar_cita(cita_id):
    with db() as con, con.cursor() as cur:
        n = cur.execute(
            "UPDATE citas SET estado = 'Cancelada' WHERE id = %s AND cliente_id = %s AND estado IN ('Pendiente', 'Confirmada')",
            (cita_id, session['usuario_id']),
        )
        con.commit()
    flash('Cita cancelada.' if n else 'No se pudo cancelar esa cita.', 'ok' if n else 'error')
    return redirect(url_for('mis_citas'))


# ------------------------- ADMIN: AGENDA DE CITAS -------------------------
TRANSICIONES = {
    'Pendiente': {'Confirmada', 'Completada', 'Cancelada'},
    'Confirmada': {'Completada', 'Cancelada'},
}


@app.route('/panel')
@requiere_rol('admin')
def panel():
    hoy = date.today()
    fecha = request.args.get('fecha')
    if fecha is None:            # sin parámetro: muestra el día de hoy
        fecha = hoy.isoformat()
    barbero = request.args.get('barbero', '')

    condiciones, params = [], []
    if fecha:
        try:
            date.fromisoformat(fecha)
            condiciones.append('c.fecha = %s')
            params.append(fecha)
        except ValueError:
            fecha = ''
    if barbero.isdigit():
        condiciones.append('c.barbero_id = %s')
        params.append(int(barbero))
    donde = ('WHERE ' + ' AND '.join(condiciones)) if condiciones else ''

    with db() as con, con.cursor() as cur:
        cur.execute(
            f"""SELECT c.id, c.fecha, c.hora, c.estado, cl.nombre AS cliente, cl.telefono,
                       s.nombre AS servicio, s.precio, b.nombre AS barbero
                FROM citas c
                JOIN usuarios cl ON cl.id = c.cliente_id
                JOIN usuarios b ON b.id = c.barbero_id
                JOIN servicios s ON s.id = c.servicio_id
                {donde}
                ORDER BY c.fecha, c.hora""",
            params,
        )
        citas = cur.fetchall()

        cur.execute("SELECT COUNT(*) AS n FROM citas WHERE fecha = %s AND estado <> 'Cancelada'", (hoy,))
        st_hoy = cur.fetchone()['n']
        cur.execute("SELECT COUNT(*) AS n FROM citas WHERE estado = 'Pendiente'")
        st_pend = cur.fetchone()['n']
        cur.execute(
            """SELECT COALESCE(SUM(s.precio), 0) AS total FROM citas c
               JOIN servicios s ON s.id = c.servicio_id
               WHERE c.fecha = %s AND c.estado = 'Completada'""",
            (hoy,),
        )
        st_ing = cur.fetchone()['total']
        cur.execute("SELECT id, nombre FROM usuarios WHERE rol = 'admin' ORDER BY nombre")
        barberos = cur.fetchall()

    for c in citas:
        c['hora_txt'] = a_hhmm(c['hora'])
    return render_template('panel.html', citas=citas, barberos=barberos, fecha=fecha, barbero=barbero,
                           st_hoy=st_hoy, st_pend=st_pend, st_ing=st_ing)


@app.route('/panel/<int:cita_id>/estado', methods=['POST'])
@requiere_rol('admin')
def cambiar_estado(cita_id):
    nuevo = request.form.get('estado', '')
    with db() as con, con.cursor() as cur:
        cur.execute('SELECT estado FROM citas WHERE id = %s', (cita_id,))
        c = cur.fetchone()
        if not c or nuevo not in TRANSICIONES.get(c['estado'], set()):
            flash('Ese cambio de estado no es válido.', 'error')
        else:
            cur.execute('UPDATE citas SET estado = %s WHERE id = %s', (nuevo, cita_id))
            con.commit()
            flash(f'Cita APT-{cita_id} marcada como {nuevo}.', 'ok')
    return redirect(request.referrer or url_for('panel'))


# ------------------------- ADMIN: CATÁLOGO DE SERVICIOS -------------------------
@app.route('/servicios')
@requiere_rol('admin')
def servicios():
    with db() as con, con.cursor() as cur:
        cur.execute('SELECT * FROM servicios ORDER BY activo DESC, id')
        lista = cur.fetchall()
    editar = None
    if request.args.get('editar', '').isdigit():
        editar = next((s for s in lista if s['id'] == int(request.args['editar'])), None)
    return render_template('servicios.html', servicios=lista, editar=editar)


@app.route('/servicios/guardar', methods=['POST'])
@requiere_rol('admin')
def guardar_servicio():
    sid = request.form.get('id', '')
    nombre = request.form.get('nombre', '').strip()
    try:
        precio = Decimal(request.form.get('precio', ''))
        duracion = int(request.form.get('duracion', ''))
    except (InvalidOperation, ValueError):
        flash('Precio o duración inválidos.', 'error')
        return redirect(url_for('servicios'))

    if not nombre or len(nombre) > 100 or not precio.is_finite() or precio <= 0 or precio > 99999 or not 5 <= duracion <= 480:
        flash('Revisa nombre, precio (mayor a 0) y duración (5 a 480 min).', 'error')
        return redirect(url_for('servicios'))

    with db() as con, con.cursor() as cur:
        if sid.isdigit():
            cur.execute('UPDATE servicios SET nombre = %s, precio = %s, duracion_min = %s WHERE id = %s',
                        (nombre, precio, duracion, int(sid)))
            flash('Servicio actualizado.', 'ok')
        else:
            cur.execute('INSERT INTO servicios (nombre, precio, duracion_min) VALUES (%s, %s, %s)',
                        (nombre, precio, duracion))
            flash('Servicio creado.', 'ok')
        con.commit()
    return redirect(url_for('servicios'))


@app.route('/servicios/<int:sid>/estado', methods=['POST'])
@requiere_rol('admin')
def alternar_servicio(sid):
    with db() as con, con.cursor() as cur:
        cur.execute('UPDATE servicios SET activo = 1 - activo WHERE id = %s', (sid,))
        con.commit()
    flash('Estado del servicio actualizado.', 'ok')
    return redirect(url_for('servicios'))


# ------------------------- ADMIN: USUARIOS Y ROLES -------------------------
@app.route('/usuarios')
@requiere_rol('admin')
def usuarios():
    with db() as con, con.cursor() as cur:
        cur.execute('SELECT id, nombre, correo, telefono, rol FROM usuarios ORDER BY rol, nombre')
        lista = cur.fetchall()
    return render_template('usuarios.html', usuarios=lista)


@app.route('/usuarios/<int:uid>/rol', methods=['POST'])
@requiere_rol('admin')
def cambiar_rol(uid):
    rol = request.form.get('rol', '')
    if rol not in ('cliente', 'admin'):
        flash('Rol inválido.', 'error')
    elif uid == session['usuario_id']:
        flash('No puedes cambiar tu propio rol.', 'error')
    else:
        with db() as con, con.cursor() as cur:
            cur.execute('UPDATE usuarios SET rol = %s WHERE id = %s', (rol, uid))
            con.commit()
        flash('Rol actualizado.', 'ok')
    return redirect(url_for('usuarios'))


if __name__ == '__main__':
    app.run(debug=True)