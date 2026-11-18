# Barbería Estilo

Sistema web de gestión de citas para una barbería/estética. Los clientes agendan en línea según la disponibilidad real del barbero, y el personal administra la agenda, los servicios y los usuarios desde un panel.

> Proyecto de la materia Infraestructura de Aplicaciones Web, UTNG.

## Funcionalidades

**Cliente**
- Registro, inicio de sesión y recuperación de contraseña.
- Agendar cita eligiendo servicio, barbero, fecha y hora disponible. Los horarios se calculan según la duración del servicio y se bloquean los traslapes.
- Consultar y cancelar sus citas.

**Administrador/Barbero**
- Agenda de citas con filtros por fecha y barbero, y cambio de estado (Pendiente, Confirmada, Completada, Cancelada).
- Tarjetas de resumen: citas de hoy, pendientes e ingresos del día.
- Catálogo de servicios: crear, editar, activar y desactivar.
- Usuarios y roles.

## Tecnologías

- Python 3 + Flask (patrón MVC: modelo en MySQL, vistas con plantillas Jinja2, controladores en `app.py`)
- MySQL 8 con PyMySQL
- Flask-WTF (protección CSRF)
- HTML5 + Tailwind CSS (por CDN)

## Requisitos

- Python 3.10 o superior
- MySQL 8 en ejecución
- Conexión a internet (Tailwind se carga por CDN)

## Instalación

1. Clona el repositorio y entra a la carpeta:
   ```powershell
   git clone https://github.com/1224100836jglo-ux/barberia-estilo.git
   cd barberia-estilo
   ```

2. Crea el entorno virtual e instala las dependencias:
   ```powershell
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Crea la base de datos ejecutando `schema.sql` en MySQL Workbench (abrir el archivo y ejecutarlo con el rayo), o desde la consola de MySQL:
   ```sql
   source C:/ruta/al/proyecto/schema.sql;
   ```

4. Crea tu archivo de configuración a partir de la plantilla y edítalo con tus datos:
   ```powershell
   copy config.example.py config.py
   ```
   - `DB_PASSWORD`: tu contraseña de MySQL.
   - `SECRET_KEY`: una cadena larga y aleatoria. Puedes generarla con:
     ```powershell
     python -c "import secrets; print(secrets.token_hex(32))"
     ```

5. Arranca la aplicación:
   ```powershell
   python app.py
   ```
   Abre http://127.0.0.1:5000

## Primer administrador

Todas las cuentas nuevas nacen como **cliente**. Para crear el primer administrador, regístrate en la aplicación y luego ejecuta en MySQL:

```sql
USE barberia;
UPDATE usuarios SET rol = 'admin' WHERE correo = 'tu-correo@ejemplo.com';
```

A partir de ahí, un administrador puede cambiar los roles desde la pantalla **Usuarios**. Los administradores aparecen como barberos al agendar.

## Datos y pruebas de ejemplo

```powershell
python seed_pruebas.py          # crea 2 barberos, 2 clientes y citas de ejemplo
python pruebas_rapidas.py       # ejecuta 21 pruebas automáticas
python seed_pruebas.py limpiar  # elimina los datos de prueba
```

Las cuentas de ejemplo usan la contraseña `Prueba1234`:
`barbero1@prueba.com`, `barbero2@prueba.com`, `cliente1@prueba.com` y `cliente2@prueba.com`.

Las pruebas verifican CSRF, separación de roles, permisos entre usuarios y la validación de traslapes de horario.

## Recuperación de contraseña

El enlace de recuperación es de un solo uso y vence a los 30 minutos. En el proyecto **no se envía por correo**: se imprime en la terminal donde corre Flask, simulando el envío. En producción se enviaría por SMTP.

## Estructura

```
barberia-estilo/
├── app.py                # rutas y lógica (controlador)
├── schema.sql            # estructura de la base de datos
├── config.example.py     # plantilla de configuración
├── requirements.txt
├── seed_pruebas.py       # datos de ejemplo
├── pruebas_rapidas.py    # pruebas automáticas
├── templates/            # vistas (Jinja2)
├── static/
└── prototipo/            # primer prototipo estático en HTML
```

## Seguridad

- Contraseñas almacenadas con hash.
- Protección CSRF en todos los formularios con método POST.
- Control de acceso por rol, validado en el servidor en cada petición.
- Consultas parametrizadas contra inyección SQL.
- Tokens de recuperación guardados como hash, de un solo uso y con vencimiento.

## Despliegue

`app.run(debug=True)` es solo para desarrollo. Para producción se propone Gunicorn detrás de Nginx como servidor web y proxy inverso, con HTTPS.

## Autor

Joseph Guadalupe Leon Ortiz, UTNG.