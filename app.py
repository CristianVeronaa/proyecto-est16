from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

# LLAVE SECRETA: Necesaria para sesiones seguras
app.secret_key = 'est16_proyecto_secreto_key'

# Configuración para subida de archivos (Avisos)
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 1. CONEXIÓN A LA BASE DE DATOS (Portable)
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASS', ''),
        database=os.getenv('DB_NAME', 'control_est16')
    )

# 1.1 CONTEXT PROCESSOR: Menú dinámico para todas las plantillas
@app.context_processor
def inject_menu():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Obtenemos las páginas que deben estar en el menú y no tienen padre (niveles superiores)
        cursor.execute("SELECT id_pagina, titulo, slug, tipo FROM paginas WHERE mostrar_en_menu = 1 AND id_padre IS NULL ORDER BY orden_menu ASC")
        parents = cursor.fetchall()
        
        for p in parents:
            # Para cada padre, buscamos sus hijos que también deben estar en el menú
            cursor.execute("SELECT titulo, slug FROM paginas WHERE id_padre = %s AND mostrar_en_menu = 1 ORDER BY orden_menu ASC", (p['id_pagina'],))
            p['children'] = cursor.fetchall()
        
        cursor.close(); conn.close()
        return dict(menu_dinamico=parents)
    except Exception as e:
        print(f"Error en inject_menu: {e}")
        return dict(menu_dinamico=[])

# 2. RUTA PRINCIPAL: Avisos públicos
@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Avisos (Aumentamos a 6)
        cursor.execute("SELECT * FROM publicaciones ORDER BY fecha_creacion DESC LIMIT 6")
        avisos = cursor.fetchall()

        # Para cada aviso, buscamos sus adjuntos adicionales
        for aviso in avisos:
            cursor.execute("SELECT * FROM publicacion_adjuntos WHERE id_post = %s", (aviso['id_post'],))
            aviso['adjuntos'] = cursor.fetchall()
        
        # Talleres dinámicos
        cursor.execute("SELECT * FROM paginas WHERE tipo = 'taller' AND estado = 'publicado' AND mostrar_en_inicio = 1")
        talleres = cursor.fetchall()
        
        # Páginas destacadas
        cursor.execute("SELECT * FROM paginas WHERE tipo = 'pagina' AND estado = 'publicado' AND mostrar_en_inicio = 1")
        paginas_inicio = cursor.fetchall()
        
    except mysql.connector.Error as e:
        print(f"Error en index: {e}")
        avisos = []
        talleres = []
        paginas_inicio = []
    
    cursor.close(); conn.close()
    return render_template('index.html', avisos=avisos, talleres=talleres, paginas_inicio=paginas_inicio)

# RUTA PARA VER AVISO INDIVIDUAL
@app.route('/aviso/<int:id_post>')
def ver_aviso_detalle(id_post):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM publicaciones WHERE id_post = %s", (id_post,))
    aviso = cursor.fetchone()
    
    if not aviso:
        flash('El aviso no existe.', 'warning')
        return redirect(url_for('index'))
    
    cursor.execute("SELECT * FROM publicacion_adjuntos WHERE id_post = %s", (id_post,))
    adjuntos = cursor.fetchall()
    
    # Clasificar adjuntos en imagenes y documentos
    imagenes = []
    documentos = []
    
    ext_imagenes = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    
    for adj in adjuntos:
        ext = os.path.splitext(adj['archivo_url'].lower())[1]
        if ext in ext_imagenes:
            imagenes.append(adj)
        else:
            documentos.append(adj)
            
    cursor.close(); conn.close()
    return render_template('aviso.html', aviso=aviso, imagenes=imagenes, documentos=documentos)

# 3. LOGIN MULTI-ROL
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo_o_curp = request.form.get('usuario', '') 
        password = request.form.get('password', '')

        if not correo_o_curp or not password:
            flash('Por favor llena todos los campos', 'warning')
            return render_template('login.html')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Buscamos al usuario (Admin, Maestro o Padre)
        query = "SELECT * FROM usuarios WHERE curp = %s"
        cursor.execute(query, (correo_o_curp,))
        usuario = cursor.fetchone()

        if usuario and usuario['password_hash'] == password:
            # Verificar si el usuario está activo
            if usuario.get('estado') == 'pendiente':
                flash('Tu cuenta aún está pendiente de aprobación por el administrador.', 'warning')
                cursor.close()
                conn.close()
                return render_template('login.html')
            elif usuario.get('estado') == 'rechazado':
                flash('Tu cuenta ha sido rechazada. Contacta a la institución.', 'danger')
                cursor.close()
                conn.close()
                return render_template('login.html')

            session['usuario_id'] = usuario['id_usuario']
            session['rol'] = usuario['rol']
            session['nombre_usuario'] = usuario['curp']

            if usuario['rol'] == 'admin':
                return redirect(url_for('admin')) 
            elif usuario['rol'] == 'maestro':
                return redirect(url_for('profe_dashboard'))
            elif usuario['rol'] == 'padre':
                return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
            
        cursor.close()
        conn.close()

    return render_template('login.html')

# 3.5 REGISTRO DE PADRES (Auto-Registro Público)
@app.route('/registro-padre', methods=['GET', 'POST'])
def registro_padre():
    if request.method == 'POST':
        curp = request.form.get('curp', '').upper()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        email = request.form.get('email', '')
        telefono = request.form.get('telefono', '')
        
        # Validaciones
        if not curp or not password or not password_confirm or not email:
            flash('Por favor completa todos los campos obligatorios', 'warning')
            return render_template('registro_padre.html')
        
        if len(telefono) < 10:
            flash('El teléfono debe tener al menos 10 dígitos', 'danger')
            return render_template('registro_padre.html')
        
        if len(curp) != 18:
            flash('El CURP debe tener exactamente 18 caracteres', 'danger')
            return render_template('registro_padre.html')
        
        if len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'danger')
            return render_template('registro_padre.html')
        
        if password != password_confirm:
            flash('Las contraseñas no coinciden', 'danger')
            return render_template('registro_padre.html')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Verificar que el CURP no exista ya
            cursor.execute("SELECT id_usuario FROM usuarios WHERE curp = %s", (curp,))
            if cursor.fetchone():
                flash('Este CURP ya está registrado en el sistema', 'danger')
                cursor.close()
                conn.close()
                return render_template('registro_padre.html')
            
            # Crear el usuario padre (Inicia como PENDIENTE)
            cursor.execute("""
                INSERT INTO usuarios (curp, password_hash, rol, estado, email, telefono) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (curp, password, 'padre', 'pendiente', email, telefono))
            conn.commit()
            cursor.close()
            conn.close()
            
            flash('¡Registro exitoso! Tu cuenta está en espera de aprobación por el administrador.', 'info')
            return redirect(url_for('login'))
            
        except Exception as e:
            print(f"Error en registro_padre: {e}")
            flash('Error al registrar. Intenta nuevamente', 'danger')
    
    return render_template('registro_padre.html')

# 3.6 REGISTRO DE MAESTROS (Solo accesible por ADMIN)
@app.route('/admin/registro-maestro', methods=['GET', 'POST'])
def registro_maestro():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        curp = request.form.get('curp', '').upper()
        nombre = request.form.get('nombre', '')
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        email = request.form.get('email', '')
        telefono = request.form.get('telefono', '')
        
        # Validaciones
        if not curp or not nombre or not password or not password_confirm or not email:
            flash('Por favor completa todos los campos obligatorios', 'warning')
            return render_template('registro_maestro.html')
        
        if len(curp) != 18:
            flash('El CURP debe tener exactamente 18 caracteres', 'danger')
            return render_template('registro_maestro.html')
        
        if len(nombre) < 3:
            flash('El nombre debe tener al menos 3 caracteres', 'danger')
            return render_template('registro_maestro.html')
        
        if len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'danger')
            return render_template('registro_maestro.html')
        
        if password != password_confirm:
            flash('Las contraseñas no coinciden', 'danger')
            return render_template('registro_maestro.html')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Verificar que el CURP no exista ya
            cursor.execute("SELECT id_usuario FROM usuarios WHERE curp = %s", (curp,))
            if cursor.fetchone():
                flash('Este CURP ya está registrado en el sistema', 'danger')
                cursor.close()
                conn.close()
                return render_template('registro_maestro.html')
            
            # Crear el usuario maestro (Activo por defecto ya que lo crea el admin)
            cursor.execute("""
                INSERT INTO usuarios (curp, password_hash, rol, estado, email, telefono) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (curp, password, 'maestro', 'activo', email, telefono))
            conn.commit()
            
            # Obtener el ID del usuario creado
            cursor.execute("SELECT id_usuario FROM usuarios WHERE curp = %s", (curp,))
            usuario = cursor.fetchone()
            usuario_id = usuario['id_usuario']
            
            # Crear registro en tabla profesores
            cursor.execute("""
                INSERT INTO profesores (id_usuario, nombre) 
                VALUES (%s, %s)
            """, (usuario_id, nombre))
            conn.commit()
            cursor.close()
            conn.close()
            
            flash('¡Maestro registrado con éxito!', 'success')
            return redirect(url_for('gestionar_usuarios'))
            
        except Exception as e:
            print(f"Error en registro_maestro: {e}")
            flash('Error al registrar. Intenta nuevamente', 'danger')
    
    return render_template('registro_maestro.html')

# 4. DASHBOARD PADRES (Boleta y Reportes)
@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    id_tutor = session.get('usuario_id')
    
    # 1. Obtener lista de hijos del tutor
    cursor.execute("SELECT * FROM alumnos WHERE id_tutor = %s", (id_tutor,))
    lista_alumnos = cursor.fetchall()

    datos_hijos = []
    for alumno in lista_alumnos:
        id_alumno = alumno['id_alumno']
        
        # 2. Obtener Calificaciones
        # 2. Obtener Calificaciones Agrupadas por Grado
        cursor.execute("SELECT * FROM calificaciones WHERE id_alumno = %s ORDER BY grado ASC, trimestre ASC", (id_alumno,))
        notas_raw = cursor.fetchall()
        
        # Organizar notas por grado: {1: [notas], 2: [notas], 3: [notas]}
        notas_por_grado = {}
        for n in notas_raw:
            g = n['grado'] if n['grado'] else 1 # Default 1 si es vieja
            if g not in notas_por_grado:
                notas_por_grado[g] = []
            notas_por_grado[g].append(n)
        
        # 3. Obtener Reportes Disciplinarios
        cursor.execute("SELECT * FROM reportes WHERE id_alumno = %s ORDER BY fecha DESC", (id_alumno,))
        reportes = cursor.fetchall()
        
        # 4. Calcular Promedio General (de todas las notas existentes)
        promedio = 0.0
        if notas_raw:
            suma_notas = sum(float(n['calificacion']) for n in notas_raw)
            promedio = round(suma_notas / len(notas_raw), 1)
        
        # 5. Obtener Historial de Inasistencias (Faltas y Retardos)
        cursor.execute("""
            SELECT materia, fecha, estado 
            FROM asistencia 
            WHERE id_alumno = %s AND estado != 'asistencia'
            ORDER BY fecha DESC
        """, (id_alumno,))
        faltas = cursor.fetchall()
        
        # 6. Empaquetar datos para el alumno
        datos_hijos.append({
            'info': alumno,
            'notas_por_grado': notas_por_grado,
            'reportes': reportes,
            'promedio': promedio,
            'faltas': faltas
        })
    
    cursor.close()
    conn.close()
    return render_template('dashboard.html', datos_hijos=datos_hijos)

# 5. ASIGNAR MAESTROS (¡Actualizado con Turno!)
@app.route('/admin/asignar_maestros', methods=['GET', 'POST'])
def asignar_maestros():
    if session.get('rol') != 'admin':
        return redirect(url_for('login'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if request.method == 'POST':
            id_profesor = request.form.get('id_profesor')
            materia = request.form.get('materia')
            grado = request.form.get('grado')
            grupo = request.form.get('grupo').upper()
            turno = request.form.get('turno')
            
            cursor.execute("""
                INSERT INTO asignaciones (id_profesor, materia, grado, grupo, turno)
                VALUES (%s, %s, %s, %s, %s)
            """, (id_profesor, materia, grado, grupo, turno))
            conn.commit()
            flash('Asignación realizada con éxito', 'success')
        
        cursor.execute("""
            SELECT a.*, p.nombre AS nombre_profesor
            FROM asignaciones a
            LEFT JOIN profesores p ON a.id_profesor = p.id_profesor
            ORDER BY a.grado, a.grupo
        """)
        asignaciones = cursor.fetchall()
        
        cursor.execute("SELECT id_profesor, nombre FROM profesores ORDER BY nombre")
        maestros = cursor.fetchall()
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error en asignar_maestros: {e}")
        asignaciones = []
        maestros = []
    
    return render_template('asignar_maestros.html', asignaciones=asignaciones, maestros=maestros)

# 6. DASHBOARD PROFESOR (¡Actualizado con Turno!)
@app.route('/profe_dashboard')
def profe_dashboard():
    if 'usuario_id' not in session or session['rol'] != 'maestro':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT id_profesor FROM profesores WHERE id_usuario = %s", (session['usuario_id'],))
    profe = cursor.fetchone()
    
    if profe:
        # Ahora traemos también el turno para mostrarlo en las tarjetas
        cursor.execute("SELECT * FROM asignaciones WHERE id_profesor = %s", (profe['id_profesor'],))
        mis_clases = cursor.fetchall()
    else:
        mis_clases = []

    cursor.close()
    conn.close()
    return render_template('profe_dashboard.html', clases=mis_clases)

# 7. CARGA MASIVA DE CALIFICACIONES
@app.route('/guardar_notas_masivas', methods=['POST'])
def guardar_notas_masivas():
    if session.get('rol') != 'maestro':
        return redirect(url_for('login'))

    materia = request.form.get('materia')
    trimestre = request.form.get('trimestre')
    grado = request.form.get('grado')
    grupo = request.form.get('grupo')
    turno = request.form.get('turno')

    conn = get_db_connection()
    cursor = conn.cursor()

    for key, value in request.form.items():
        if key.startswith('calificacion_') and value != '':
            id_alumno = key.split('_')[1]
            calificacion = value

            # Borrar anterior e insertar nueva (Ahora incluyendo grado)
            cursor.execute("""
                DELETE FROM calificaciones 
                WHERE id_alumno = %s AND materia = %s AND trimestre = %s AND grado = %s
            """, (id_alumno, materia, trimestre, grado))
            
            cursor.execute("""
                INSERT INTO calificaciones (id_alumno, grado, materia, trimestre, calificacion) 
                VALUES (%s, %s, %s, %s, %s)
            """, (id_alumno, grado, materia, trimestre, calificacion))

    conn.commit()
    cursor.close()
    conn.close()
    flash('Calificaciones actualizadas', 'success')
    return redirect(url_for('lista_alumnos', grado=grado, grupo=grupo, materia=materia, turno=turno))

# 8. PANEL ADMIN
@app.route('/admin')
def admin():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM publicaciones ORDER BY fecha_creacion DESC")
    publicaciones = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('admin.html', publicaciones=publicaciones)

# 9. GESTIÓN DE USUARIOS
@app.route('/admin/usuarios')
def gestionar_usuarios():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM usuarios")
        usuarios = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error en gestionar_usuarios: {e}")
        usuarios = []
    return render_template('usuarios.html', usuarios=usuarios)

@app.route('/admin/eliminar_usuario/<int:id_usuario>', methods=['POST'])
def eliminar_usuario(id_usuario):
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    if id_usuario == session.get('usuario_id'):
        flash('No puedes eliminar tu propia cuenta', 'danger')
        return redirect(url_for('gestionar_usuarios'))
    
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id_usuario = %s", (id_usuario,))
    conn.commit()
    cursor.close(); conn.close()
    flash('Usuario eliminado', 'success')
    return redirect(url_for('gestionar_usuarios'))

@app.route('/admin/reset-password/<int:id_usuario>', methods=['POST'])
def reset_password_user(id_usuario):
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    nueva_pass = request.form.get('nueva_pass')
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s", (nueva_pass, id_usuario))
    conn.commit()
    cursor.close(); conn.close()
    flash('Contraseña reestablecida correctamente', 'success')
    return redirect(url_for('gestionar_usuarios'))

# 10. GESTIÓN DE ALUMNOS (ADMIN)
@app.route('/admin/alumnos')
def gestionar_alumnos():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT a.*, u.curp AS curp_tutor 
        FROM alumnos a 
        LEFT JOIN usuarios u ON a.id_tutor = u.id_usuario 
        ORDER BY a.grado, a.grupo, a.nombre
    """)
    alumnos = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('admin_alumnos.html', alumnos=alumnos)

@app.route('/admin/editar_alumno/<int:id_alumno>', methods=['GET', 'POST'])
def editar_alumno(id_alumno):
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        apellido = request.form.get('apellido')
        grado = request.form.get('grado')
        grupo = request.form.get('grupo').upper()
        turno = request.form.get('turno')
        
        cursor.execute("""
            UPDATE alumnos 
            SET nombre=%s, apellido=%s, grado=%s, grupo=%s, turno=%s 
            WHERE id_alumno=%s
        """, (nombre, apellido, grado, grupo, turno, id_alumno))
        conn.commit()
        flash('Datos del alumno actualizados', 'success')
        return redirect(url_for('gestionar_alumnos'))

    cursor.execute("SELECT * FROM alumnos WHERE id_alumno = %s", (id_alumno,))
    alumno = cursor.fetchone()
    cursor.close(); conn.close()
    return render_template('editar_alumno.html', alumno=alumno)

@app.route('/admin/registrar_alumno', methods=['GET', 'POST'])
def registrar_alumno():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        apellido = request.form.get('apellido')
        curp_tutor = request.form.get('curp_tutor')
        grado = request.form.get('grado')
        grupo = request.form.get('grupo').upper()
        turno = request.form.get('turno')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id_usuario FROM usuarios WHERE curp = %s", (curp_tutor,))
            tutor = cursor.fetchone()
            
            if not tutor:
                flash('El tutor no existe en el sistema', 'danger')
                cursor.close(); conn.close()
                return render_template('registrar_alumno.html')
            
            cursor.execute("""
                INSERT INTO alumnos (nombre, apellido, id_tutor, grado, grupo, turno) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (nombre, apellido, tutor['id_usuario'], grado, grupo, turno))
            conn.commit()
            cursor.close(); conn.close()
            flash('Alumno registrado exitosamente', 'success')
            return redirect(url_for('gestionar_alumnos'))
        except Exception as e:
            print(f"Error al registrar alumno: {e}")
            flash('Error al registrar el alumno', 'danger')
    
    return render_template('registrar_alumno.html')

# 11. LISTA DE ALUMNOS (ASISTENCIA Y CALIFICACIONES)
@app.route('/lista_alumnos/<int:grado>/<grupo>/<materia>/<turno>', methods=['GET', 'POST'])
def lista_alumnos(grado, grupo, materia, turno):
    if session.get('rol') != 'maestro': return redirect(url_for('login'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # IMPORTANTE: Filtramos por grado, grupo Y turno
        cursor.execute("SELECT * FROM alumnos WHERE grado = %s AND grupo = %s AND turno = %s ORDER BY nombre", (grado, grupo, turno))
        alumnos = cursor.fetchall()
        
        resultado_alumnos = []
        for alumno in alumnos:
            resultado_alumnos.append({'alumno': alumno})
        
        cursor.close(); conn.close()
    except Exception as e:
        print(f"Error en lista_alumnos: {e}")
        resultado_alumnos = []
        
    return render_template('lista_alumnos.html', alumnos=resultado_alumnos, grado=grado, grupo=grupo, materia=materia, turno=turno)

# 12.1 GUARDAR ASISTENCIA
@app.route('/guardar_asistencia', methods=['POST'])
def guardar_asistencia():
    if session.get('rol') != 'maestro': return redirect(url_for('login'))
    
    materia = request.form.get('materia')
    grado = request.form.get('grado')
    grupo = request.form.get('grupo')
    turno = request.form.get('turno')
    fecha = request.form.get('fecha_asistencia')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Obtenemos los alumnos de ese grupo
        cursor.execute("SELECT id_alumno FROM alumnos WHERE grado = %s AND grupo = %s", (grado, grupo))
        alumnos = cursor.fetchall()
        
        for alumno in alumnos:
            id_alumno = alumno['id_alumno']
            # El estado viene del form (asistencia, falta, retardo, justificada)
            # Si no está en el form, por defecto es 'asistencia' (asumiendo que solo mandamos los que faltan o similar, 
            # pero mejor mandar todos por claridad)
            estado = request.form.get(f'asistencia_{id_alumno}', 'asistencia')
            
            # Insertar registro de asistencia (o actualizar si ya existe para esa fecha/materia)
            cursor.execute("""
                INSERT INTO asistencia (id_alumno, materia, fecha, estado) 
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE estado = %s
            """, (id_alumno, materia, fecha, estado, estado))
            
        conn.commit()
        cursor.close(); conn.close()
        flash(f'Asistencia del {fecha} guardada correctamente', 'success')
    except Exception as e:
        print(f"Error al guardar asistencia: {e}")
        flash('Error al guardar la asistencia', 'danger')
        
    return redirect(url_for('lista_alumnos', grado=grado, grupo=grupo, materia=materia, turno=turno))

# 12.2 GUARDAR REPORTE DISCIPLINARIO
@app.route('/admin/guardar_reporte', methods=['POST'])
def guardar_reporte():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    
    id_alumno = request.form.get('id_alumno')
    tipo_reporte = request.form.get('tipo_reporte')
    descripcion = request.form.get('descripcion')
    fecha = request.form.get('fecha')
    
    # Hidden fields for redirect
    materia = request.form.get('materia')
    grado = request.form.get('grado')
    grupo = request.form.get('grupo')
    turno = request.form.get('turno')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reportes (id_alumno, tipo_reporte, descripcion, fecha)
            VALUES (%s, %s, %s, %s)
        """, (id_alumno, tipo_reporte, descripcion, fecha))
        conn.commit()
        cursor.close(); conn.close()
        flash('Reporte creado exitosamente', 'success')
    except Exception as e:
        print(f"Error al guardar reporte: {e}")
        flash('Error al crear el reporte', 'danger')
        
    return redirect(url_for('gestionar_alumnos'))


# 12. ELIMINAR ASIGNACIÓN
@app.route('/admin/eliminar_asignacion/<int:id_asignacion>', methods=['POST'])
def eliminar_asignacion(id_asignacion):
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM asignaciones WHERE id_asignacion = %s", (id_asignacion,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Asignacion eliminada', 'success')
    except Exception as e:
        print(f"Error al eliminar asignación: {e}")
        flash('Error al eliminar la asignación', 'danger')
    return redirect(url_for('asignar_maestros'))


# 14. PUBLICAR AVISO (SOPORTE MULTI-ARCHIVO)
@app.route('/admin', methods=['POST'])
def crear_publicacion():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    
    try:
        titulo = request.form.get('titulo')
        contenido = request.form.get('contenido')
        archivos = request.files.getlist('archivo') # Captura varios archivos
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Primero insertamos la publicación base (quitamos id_admin si no existe)
        cursor.execute("INSERT INTO publicaciones (titulo, contenido, fecha_creacion) VALUES (%s, %s, NOW())",
                       (titulo, contenido))
        id_post = cursor.lastrowid
        
        # Ahora procesamos cada archivo subido
        es_primero = True
        ext_imagenes = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        
        for archivo in archivos:
            if archivo and archivo.filename:
                filename = secure_filename(archivo.filename)
                archivo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                
                ext = os.path.splitext(filename.lower())[1]
                tipo = 'imagen' if ext in ext_imagenes else 'documento'
                
                # Guardar en adjuntos
                cursor.execute("INSERT INTO publicacion_adjuntos (id_post, archivo_url, tipo_archivo) VALUES (%s, %s, %s)",
                               (id_post, filename, tipo))
                
                # El primer archivo de tipo imagen será el 'imagen_url' principal
                if es_primero and tipo == 'imagen':
                    cursor.execute("UPDATE publicaciones SET imagen_url = %s WHERE id_post = %s", (filename, id_post))
                    es_primero = False
        
        conn.commit()
        cursor.close()
        conn.close()
        flash('Aviso y archivos publicados exitosamente', 'success')
    except Exception as e:
        print(f"Error al crear publicación: {e}")
        flash(f'Error al publicar el aviso: {e}', 'danger')
    return redirect(url_for('admin'))

# 15. ELIMINAR PUBLICACIÓN
@app.route('/admin/eliminar_publicacion/<int:id_post>', methods=['POST'])
def eliminar_publicacion(id_post):
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Eliminar adjuntos físicos si fuera necesario (opcional por ahora)
        cursor.execute("DELETE FROM publicaciones WHERE id_post = %s", (id_post,))
        conn.commit()
        cursor.close(); conn.close()
        flash('Publicación eliminada correctamente', 'success')
    except Exception as e:
        flash(f'Error al eliminar: {e}', 'danger')
    return redirect(url_for('admin'))

# 13. EDITAR PUBLICACIÓN (ACTUALIZADO PARA MULTI-ARCHIVO)
@app.route('/admin/editar_publicacion/<int:id_post>', methods=['GET', 'POST'])
def editar_publicacion(id_post):
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM publicaciones WHERE id_post = %s", (id_post,))
        pub = cursor.fetchone()
        
        if not pub:
            flash('Publicacion no encontrada', 'danger')
            cursor.close(); conn.close()
            return redirect(url_for('admin'))
        
        if request.method == 'POST':
            titulo = request.form.get('titulo')
            contenido = request.form.get('contenido')
            archivos = request.files.getlist('archivo')
            limpiar_anteriores = request.form.get('limpiar_adjuntos') == 'si'
            
            # Actualizar datos básicos
            cursor.execute("UPDATE publicaciones SET titulo = %s, contenido = %s WHERE id_post = %s",
                           (titulo, contenido, id_post))
            
            if limpiar_anteriores:
                cursor.execute("DELETE FROM publicacion_adjuntos WHERE id_post = %s", (id_post,))
                cursor.execute("UPDATE publicaciones SET imagen_url = NULL WHERE id_post = %s", (id_post,))
            
            # Procesar nuevos archivos
            es_primero = (pub['imagen_url'] is None)
            ext_imagenes = ['.jpg', '.jpeg', '.png', '.gif', '.webp']

            for archivo in archivos:
                if archivo and archivo.filename:
                    filename = secure_filename(archivo.filename)
                    archivo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    
                    ext = os.path.splitext(filename.lower())[1]
                    tipo = 'imagen' if ext in ext_imagenes else 'documento'
                    
                    cursor.execute("INSERT INTO publicacion_adjuntos (id_post, archivo_url, tipo_archivo) VALUES (%s, %s, %s)",
                                   (id_post, filename, tipo))
                    
                    if es_primero and tipo == 'imagen':
                        cursor.execute("UPDATE publicaciones SET imagen_url = %s WHERE id_post = %s", (filename, id_post))
                        es_primero = False
            
            conn.commit()
            flash('Publicacion actualizada correctamente', 'success')
            cursor.close(); conn.close()
            return redirect(url_for('admin'))
        
        # Obtener adjuntos actuales para mostrar en el form
        cursor.execute("SELECT * FROM publicacion_adjuntos WHERE id_post = %s", (id_post,))
        adjuntos = cursor.fetchall()
        
        cursor.close(); conn.close()
        return render_template('editar_publicacion.html', pub=pub, adjuntos=adjuntos)
    except Exception as e:
        print(f"Error en editar_publicacion: {e}")
        flash(f'Error: {e}', 'danger')
        return redirect(url_for('admin'))

# RUTA PARA CAMBIAR LA IMAGEN DE PORTADA
@app.route('/admin/cambiar_portada/<int:id_post>/<int:id_adjunto>', methods=['POST'])
def cambiar_portada(id_post, id_adjunto):
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Obtener el nombre del archivo del adjunto
        cursor.execute("SELECT archivo_url FROM publicacion_adjuntos WHERE id_adjunto = %s", (id_adjunto,))
        adj = cursor.fetchone()
        
        if adj:
            cursor.execute("UPDATE publicaciones SET imagen_url = %s WHERE id_post = %s", (adj['archivo_url'], id_post))
            conn.commit()
            flash('Portada actualizada correctamente', 'success')
        
        cursor.close(); conn.close()
    except Exception as e:
        flash(f'Error al cambiar portada: {e}', 'danger')
        
    return redirect(url_for('editar_publicacion', id_post=id_post))


# 16. APROBACIÓN DE PADRES
@app.route('/admin/pendientes')
def padres_pendientes():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios WHERE rol = 'padre' AND estado = 'pendiente'")
    pendientes = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('padres_pendientes.html', pendientes=pendientes)

@app.route('/admin/aprobar_padre/<int:id_usuario>/<action>')
def gestionar_aprobacion(id_usuario, action):
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    
    nuevo_estado = 'activo' if action == 'aprobar' else 'rechazado'
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET estado = %s WHERE id_usuario = %s", (nuevo_estado, id_usuario))
    conn.commit()
    cursor.close(); conn.close()
    
    mensaje = "Usuario aprobado" if action == 'aprobar' else "Usuario rechazado"
    flash(mensaje, 'success' if action == 'aprobar' else 'warning')
    return redirect(url_for('padres_pendientes'))

# 17. PERFIL DE USUARIO (Cambio de datos y contraseña)
@app.route('/perfil', methods=['GET', 'POST'])
def perfil():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        # Datos básicos
        nuevo_email = request.form.get('email')
        nuevo_tel = request.form.get('telefono')
        nuevo_nombre = request.form.get('nombre')
        
        # Cambio de contraseña (opcional)
        pass_actual = request.form.get('pass_actual')
        pass_nueva = request.form.get('pass_nueva')
        pass_confirm = request.form.get('pass_confirm')
        
        try:
            # 1. Actualizar datos básicos (para todos)
            cursor.execute("UPDATE usuarios SET email = %s, telefono = %s WHERE id_usuario = %s", (nuevo_email, nuevo_tel, session['usuario_id']))
            
            # 2. Si es maestro, actualizar nombre en tabla profesores
            if session.get('rol') == 'maestro' and nuevo_nombre:
                cursor.execute("UPDATE profesores SET nombre = %s WHERE id_usuario = %s", (nuevo_nombre, session['usuario_id']))
            
            # 3. Procesar cambio de contraseña si se llenaron los campos
            if pass_actual and pass_nueva:
                cursor.execute("SELECT password_hash FROM usuarios WHERE id_usuario = %s", (session['usuario_id'],))
                usuario = cursor.fetchone()
                
                if usuario['password_hash'] != pass_actual:
                    flash('La contraseña actual es incorrecta. Datos de perfil guardados, pero la contraseña no cambió.', 'warning')
                elif pass_nueva != pass_confirm:
                    flash('Las nuevas contraseñas no coinciden.', 'danger')
                elif len(pass_nueva) < 6:
                    flash('La nueva contraseña es demasiado corta.', 'danger')
                else:
                    cursor.execute("UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s", (pass_nueva, session['usuario_id']))
                    flash('Contraseña y perfil actualizados con éxito.', 'success')
            else:
                flash('Datos de perfil actualizados correctamente.', 'success')
            
            conn.commit()
        except Exception as e:
            print(f"Error en perfil: {e}")
            flash('Error al actualizar los datos.', 'danger')
            
    # Obtener datos actuales para el formulario
    cursor.execute("SELECT u.curp, u.telefono, p.nombre FROM usuarios u LEFT JOIN profesores p ON u.id_usuario = p.id_usuario WHERE u.id_usuario = %s", (session['usuario_id'],))
    datos = cursor.fetchone()
    cursor.close(); conn.close()
    
    return render_template('perfil.html', datos=datos)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# 18. SOLICITUD DE RECUPERACIÓN (Público con Código de Verificación)
import random

@app.route('/olvide-password', methods=['GET', 'POST'])
def olvide_password():
    if request.method == 'POST':
        action = request.form.get('action')
        curp = request.form.get('curp', '').upper()

        if action == 'enviar_codigo':
            conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id_usuario, email FROM usuarios WHERE curp = %s", (curp,))
            usuario = cursor.fetchone()
            
            if usuario and usuario['email']:
                # Generar código de 6 dígitos
                codigo = str(random.randint(100000, 999999))
                session['reset_codigo'] = codigo
                session['reset_user_id'] = usuario['id_usuario']
                
                # SIMULACIÓN: Envío de correo electrónico
                print(f"\n--- [CORREO SIMULADO] ---")
                print(f"De: sistema@est16.edu.mx")
                print(f"Para: {usuario['email']}")
                print(f"Asunto: Recuperación de Contraseña - EST 16")
                print(f"----------------------------------------")
                print(f"Hola, recibimos una solicitud para restablecer tu contraseña.")
                print(f"Tu código de verificación es: {codigo}")
                print(f"----------------------------------------\n")
                
                flash(f'Hemos enviado un código de verificación a tu correo: {usuario["email"]}', 'success')
                return render_template('verificar_codigo.html', curp=curp)
            else:
                flash('No se encontró un usuario con ese CURP o no tiene correo electrónico registrado.', 'danger')
                cursor.close(); conn.close()
                
        elif action == 'verificar_codigo':
            codigo_usuario = request.form.get('codigo')
            if codigo_usuario == session.get('reset_codigo'):
                flash('Código verificado. Crea tu nueva contraseña.', 'success')
                return render_template('nueva_password_recovery.html')
            else:
                flash('Código incorrecto.', 'danger')
                return render_template('verificar_codigo.html', curp=curp)
                
        elif action == 'restablecer_final':
            nueva_pass = request.form.get('nueva_pass')
            pass_confirm = request.form.get('pass_confirm')
            
            if nueva_pass != pass_confirm:
                flash('Las contraseñas no coinciden', 'danger')
                return render_template('nueva_password_recovery.html')
            
            user_id = session.get('reset_user_id')
            conn = get_db_connection(); cursor = conn.cursor()
            cursor.execute("UPDATE usuarios SET password_hash = %s WHERE id_usuario = %s", (nueva_pass, user_id))
            conn.commit()
            cursor.close(); conn.close()
            
            # Limpiar sesión de reset
            session.pop('reset_codigo', None)
            session.pop('reset_user_id', None)
            
            flash('Tu contraseña ha sido actualizada. Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))

    return render_template('olvide_password.html')

# 20. SISTEMA DE BÚSQUEDA
@app.route('/buscar')
def buscar():
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    search_pattern = f"%{query}%"
    
    # Buscar en Páginas y Talleres
    cursor.execute("""
        SELECT 'pagina' as tipo_item, titulo, contenido, slug, imagen_url, tipo
        FROM paginas 
        WHERE (titulo LIKE %s OR contenido LIKE %s OR slug LIKE %s) 
        AND estado = 'publicado'
    """, (search_pattern, search_pattern, search_pattern))
    res_paginas = cursor.fetchall()
    
    # Buscar en Publicaciones (Avisos)
    cursor.execute("""
        SELECT 'aviso' as tipo_item, titulo, contenido, id_post as slug, imagen_url, 'aviso' as tipo
        FROM publicaciones 
        WHERE (titulo LIKE %s OR contenido LIKE %s)
    """, (search_pattern, search_pattern))
    res_avisos = cursor.fetchall()
    
    cursor.close(); conn.close()
    
    resultados = res_paginas + res_avisos
    return render_template('resultados_busqueda.html', resultados=resultados, query=query)

# 21. RUTA DINÁMICA DE PÁGINAS
@app.route('/p/<slug>')
def ver_pagina(slug):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Obtener página
    cursor.execute("SELECT * FROM paginas WHERE slug = %s AND estado = 'publicado'", (slug,))
    pagina = cursor.fetchone()
    
    if not pagina:
        flash('La página no existe o no está disponible.', 'warning')
        return redirect(url_for('index'))
    
    # Obtener subpáginas (hijos)
    cursor.execute("SELECT titulo, slug FROM paginas WHERE id_padre = %s AND estado = 'publicado'", (pagina['id_pagina'],))
    subpaginas = cursor.fetchall()
    
    # Obtener página padre (si existe) para breadcrumbs
    padre = None
    if pagina['id_padre']:
        cursor.execute("SELECT titulo, slug FROM paginas WHERE id_pagina = %s", (pagina['id_padre'],))
        padre = cursor.fetchone()
        
    cursor.close(); conn.close()
    return render_template('p.html', pagina=pagina, subpaginas=subpaginas, padre=padre)

# 22. GESTIÓN DE PÁGINAS (ADMIN)
@app.route('/admin/paginas')
def gestionar_paginas():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p1.*, p2.titulo AS nombre_padre 
        FROM paginas p1 
        LEFT JOIN paginas p2 ON p1.id_padre = p2.id_pagina
        ORDER BY p1.tipo, p1.titulo
    """)
    paginas = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('admin_paginas.html', paginas=paginas)

@app.route('/admin/nueva_pagina', methods=['GET', 'POST'])
def crear_pagina():
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        titulo = request.form.get('titulo')
        slug = request.form.get('slug', '').lower().replace(' ', '-')
        contenido = request.form.get('contenido')
        id_padre = request.form.get('id_padre')
        if not id_padre or str(id_padre).strip() == "" or id_padre == "None":
            id_padre = None
            
        tipo = request.form.get('tipo', 'pagina')
        estado = request.form.get('estado', 'publicado')
        mostrar_en_inicio = 1 if request.form.get('mostrar_en_inicio') else 0
        mostrar_en_menu = 1 if request.form.get('mostrar_en_menu') else 0
        orden_menu = request.form.get('orden_menu') or 0
        
        archivo = request.files.get('archivo')
        imagen_url = None
        if archivo and archivo.filename:
            filename = secure_filename(archivo.filename)
            archivo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            imagen_url = filename
            
        try:
            cursor.execute("""
                INSERT INTO paginas (slug, titulo, contenido, imagen_url, id_padre, estado, mostrar_en_inicio, tipo, mostrar_en_menu, orden_menu)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (slug, titulo, contenido, imagen_url, id_padre, estado, mostrar_en_inicio, tipo, mostrar_en_menu, orden_menu))
            conn.commit()
            flash('Página creada exitosamente', 'success')
            return redirect(url_for('gestionar_paginas'))
        except Exception as e:
            flash(f'Error al crear página: {e}', 'danger')

    cursor.execute("SELECT id_pagina, titulo FROM paginas ORDER BY titulo")
    padres = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('editar_pagina.html', padres=padres, modo='crear')

@app.route('/admin/editar_pagina/<int:id_pagina>', methods=['GET', 'POST'])
def editar_pagina(id_pagina):
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        titulo = request.form.get('titulo')
        slug = request.form.get('slug', '').lower().replace(' ', '-')
        contenido = request.form.get('contenido')
        id_padre = request.form.get('id_padre')
        if not id_padre or str(id_padre).strip() == "" or id_padre == "None":
            id_padre = None
            
        tipo = request.form.get('tipo', 'pagina')
        estado = request.form.get('estado', 'publicado')
        mostrar_en_inicio = 1 if request.form.get('mostrar_en_inicio') else 0
        mostrar_en_menu = 1 if request.form.get('mostrar_en_menu') else 0
        orden_menu = request.form.get('orden_menu') or 0
        
        archivo = request.files.get('archivo')
        
        cursor.execute("SELECT imagen_url FROM paginas WHERE id_pagina = %s", (id_pagina,))
        actual = cursor.fetchone()
        imagen_url = actual['imagen_url']
        
        if archivo and archivo.filename:
            filename = secure_filename(archivo.filename)
            archivo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            imagen_url = filename
            
        cursor.execute("""
            UPDATE paginas 
            SET slug=%s, titulo=%s, contenido=%s, imagen_url=%s, id_padre=%s, estado=%s, mostrar_en_inicio=%s, tipo=%s, mostrar_en_menu=%s, orden_menu=%s
            WHERE id_pagina=%s
        """, (slug, titulo, contenido, imagen_url, id_padre, estado, mostrar_en_inicio, tipo, mostrar_en_menu, orden_menu, id_pagina))
        conn.commit()
        flash('Página actualizada', 'success')
        return redirect(url_for('gestionar_paginas'))

    cursor.execute("SELECT * FROM paginas WHERE id_pagina = %s", (id_pagina,))
    pagina = cursor.fetchone()
    cursor.execute("SELECT id_pagina, titulo FROM paginas WHERE id_pagina != %s ORDER BY titulo", (id_pagina,))
    padres = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('editar_pagina.html', pagina=pagina, padres=padres, modo='editar')

@app.route('/admin/eliminar_pagina/<int:id_pagina>', methods=['POST'])
def eliminar_pagina(id_pagina):
    if session.get('rol') != 'admin': return redirect(url_for('login'))
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("DELETE FROM paginas WHERE id_pagina = %s", (id_pagina,))
    conn.commit()
    cursor.close(); conn.close()
    flash('Página eliminada correctamente', 'success')
    return redirect(url_for('gestionar_paginas'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)