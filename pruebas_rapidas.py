import re
from datetime import date, timedelta

import pymysql

import config
from app import app

PASS = 'Prueba1234'
resultados = []


def db():
    return pymysql.connect(host=config.DB_HOST, user=config.DB_USER, password=config.DB_PASSWORD,
                           database=config.DB_NAME, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)


def uno(sql, params=()):
    with db() as con, con.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def revisar(nombre, condicion):
    resultados.append(bool(condicion))
    print('OK    ' if condicion else 'FALLA ', nombre)


def token(c, ruta):
    html = c.get(ruta).get_data(as_text=True)
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ''


def entrar(correo):
    c = app.test_client()
    c.post('/login', data={'correo': correo, 'password': PASS, 'csrf_token': token(c, '/login')})
    return c


def logueado(c):
    with c.session_transaction() as s:
        return 'usuario_id' in s


# ---------- Datos de apoyo ----------
cliente2_id = uno("SELECT id FROM usuarios WHERE correo = 'cliente2@prueba.com'")['id']
barbero1_id = uno("SELECT id FROM usuarios WHERE correo = 'barbero1@prueba.com'")['id']
servicio_id = uno('SELECT id FROM servicios WHERE activo = 1 ORDER BY id LIMIT 1')['id']
cita = uno("""SELECT id FROM citas WHERE estado = 'Pendiente'
              AND cliente_id = (SELECT id FROM usuarios WHERE correo = 'cliente1@prueba.com') LIMIT 1""")['id']
completada = uno("SELECT id FROM citas WHERE estado = 'Completada' LIMIT 1")['id']
manana = (date.today() + timedelta(days=1)).isoformat()
estado = lambda i: uno('SELECT estado FROM citas WHERE id = %s', (i,))['estado']
rol_de = lambda i: uno('SELECT rol FROM usuarios WHERE id = %s', (i,))['rol']
total_citas = lambda: uno('SELECT COUNT(*) AS n FROM citas')['n']

print('\n--- Sesión y CSRF ---')
c = app.test_client()
c.post('/login', data={'correo': 'cliente1@prueba.com', 'password': PASS})
revisar('Login sin token es rechazado', not logueado(c))

c = app.test_client()
c.post('/login', data={'correo': 'cliente1@prueba.com', 'password': 'mala', 'csrf_token': token(c, '/login')})
revisar('Contraseña incorrecta no inicia sesión', not logueado(c))

cl = entrar('cliente1@prueba.com')
revisar('Login correcto con token', logueado(cl))
revisar('Sin sesión, /panel redirige al login', app.test_client().get('/panel').status_code == 302)

print('\n--- Roles ---')
for ruta in ('/panel', '/servicios', '/usuarios'):
    revisar(f'Cliente NO accede a {ruta}', cl.get(ruta).status_code == 302)
ad = entrar('barbero1@prueba.com')
for ruta in ('/panel', '/servicios', '/usuarios'):
    revisar(f'Admin accede a {ruta}', ad.get(ruta).status_code == 200)
for ruta in ('/agendar', '/mis-citas'):
    revisar(f'Admin NO accede a {ruta}', ad.get(ruta).status_code == 302)

print('\n--- Citas ---')
cl.post(f'/mis-citas/{cita}/cancelar')   # sin token
revisar('Cancelar sin token es rechazado', estado(cita) == 'Pendiente')

c2 = entrar('cliente2@prueba.com')
c2.post(f'/mis-citas/{cita}/cancelar', data={'csrf_token': token(c2, '/agendar')})
revisar('Un cliente NO cancela la cita de otro', estado(cita) == 'Pendiente')

antes = total_citas()
datos = {'servicio': servicio_id, 'barbero': barbero1_id, 'fecha': manana, 'hora': '10:00'}
cl.post('/agendar', data={**datos, 'csrf_token': token(cl, '/agendar')})
revisar('NO permite traslape de horario', total_citas() == antes)

cl.post('/agendar', data={**datos, 'hora': '15:00', 'csrf_token': token(cl, '/agendar')})
revisar('Agendar en horario libre funciona', total_citas() == antes + 1)

print('\n--- Admin ---')
ad.post(f'/panel/{cita}/estado', data={'estado': 'Confirmada'})   # sin token
revisar('Cambiar estado sin token es rechazado', estado(cita) == 'Pendiente')

ad.post(f'/panel/{cita}/estado', data={'estado': 'Confirmada', 'csrf_token': token(ad, '/servicios')})
revisar('Admin confirma una cita', estado(cita) == 'Confirmada')

ad.post(f'/panel/{completada}/estado', data={'estado': 'Pendiente', 'csrf_token': token(ad, '/servicios')})
revisar('No se puede regresar una cita completada a pendiente', estado(completada) == 'Completada')

ad.post(f'/usuarios/{cliente2_id}/rol', data={'rol': 'admin'})   # sin token
revisar('Cambiar rol sin token es rechazado', rol_de(cliente2_id) == 'cliente')

c2.post(f'/usuarios/{cliente2_id}/rol', data={'rol': 'admin', 'csrf_token': token(c2, '/agendar')})
revisar('Un cliente NO puede hacerse admin', rol_de(cliente2_id) == 'cliente')

print(f'\n{sum(resultados)}/{len(resultados)} pruebas correctas')