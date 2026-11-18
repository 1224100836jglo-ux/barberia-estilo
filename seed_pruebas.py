import sys
from datetime import date, timedelta

import pymysql
from werkzeug.security import generate_password_hash

import config

PASSWORD = 'Prueba1234'
USUARIOS = [
    ('Carlos Mendoza', '4181110001', 'barbero1@prueba.com', 'admin'),
    ('Mateo Hernández', '4181110002', 'barbero2@prueba.com', 'admin'),
    ('Cliente Uno', '4182220001', 'cliente1@prueba.com', 'cliente'),
    ('Cliente Dos', '4182220002', 'cliente2@prueba.com', 'cliente'),
]

con = pymysql.connect(host=config.DB_HOST, user=config.DB_USER, password=config.DB_PASSWORD,
                      database=config.DB_NAME, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
cur = con.cursor()

# 1) Limpia datos de prueba anteriores
cur.execute("SELECT id FROM usuarios WHERE correo LIKE %s", ('%@prueba.com',))
ids = [r['id'] for r in cur.fetchall()]
if ids:
    marcas = ','.join(['%s'] * len(ids))
    cur.execute(f'DELETE FROM citas WHERE cliente_id IN ({marcas}) OR barbero_id IN ({marcas})', ids + ids)
    cur.execute(f'DELETE FROM usuarios WHERE id IN ({marcas})', ids)
con.commit()

if len(sys.argv) > 1 and sys.argv[1] == 'limpiar':
    print('Datos de prueba eliminados.')
    sys.exit()

# 2) Crea usuarios
h = generate_password_hash(PASSWORD)
nuevos = {}
for nombre, tel, correo, rol in USUARIOS:
    cur.execute('INSERT INTO usuarios (nombre, telefono, correo, password_hash, rol) VALUES (%s, %s, %s, %s, %s)',
                (nombre, tel, correo, h, rol))
    nuevos[correo] = cur.lastrowid

# 3) Crea citas de ejemplo
cur.execute('SELECT id FROM servicios WHERE activo = 1 ORDER BY id')
sv = [r['id'] for r in cur.fetchall()]
if len(sv) < 3:
    sys.exit('Necesitas al menos 3 servicios activos en la tabla servicios.')

hoy = date.today()
manana = hoy + timedelta(days=1)
c1, c2 = nuevos['cliente1@prueba.com'], nuevos['cliente2@prueba.com']
b1, b2 = nuevos['barbero1@prueba.com'], nuevos['barbero2@prueba.com']

citas = [
    (c1, b1, sv[2], manana, '10:00', 'Pendiente'),    # para la prueba de traslape
    (c1, b2, sv[0], hoy, '19:00', 'Confirmada'),
    (c2, b1, sv[1], hoy, '18:00', 'Completada'),      # suma a ingresos de hoy
    (c2, b2, sv[0], hoy, '12:00', 'Pendiente'),
    (c2, b1, sv[0], manana, '11:00', 'Cancelada'),
]
for c in citas:
    cur.execute('INSERT INTO citas (cliente_id, barbero_id, servicio_id, fecha, hora, estado) VALUES (%s, %s, %s, %s, %s, %s)', c)
con.commit()

print('Datos de prueba listos. Contraseña de todas las cuentas:', PASSWORD)
for _, _, correo, rol in USUARIOS:
    print(f'  {correo:22} ({rol})')