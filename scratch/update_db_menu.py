import mysql.connector

def update_db():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="control_est16"
        )
        cursor = conn.cursor()
        
        # Agregar columnas
        try:
            cursor.execute("ALTER TABLE paginas ADD COLUMN mostrar_en_menu BOOLEAN DEFAULT FALSE")
            print("Columna mostrar_en_menu añadida.")
        except mysql.connector.Error as err:
            if err.errno == 1060: # Dulplicate column name
                print("Columna mostrar_en_menu ya existe.")
            else: raise err

        try:
            cursor.execute("ALTER TABLE paginas ADD COLUMN orden_menu INT DEFAULT 0")
            print("Columna orden_menu añadida.")
        except mysql.connector.Error as err:
            if err.errno == 1060: # Dulplicate column name
                print("Columna orden_menu ya existe.")
            else: raise err
            
        # Poner "Acerca de nosotros" en el menú
        cursor.execute("UPDATE paginas SET mostrar_en_menu = 1, orden_menu = 1 WHERE slug = 'acerca-de-nosotros'")
        print("Acerca de nosotros marcado para mostrar en menú.")
        
        # Crear página Visión como hijo de Acerca de nosotros
        cursor.execute("SELECT id_pagina FROM paginas WHERE slug = 'acerca-de-nosotros'")
        parent = cursor.fetchone()
        if parent:
            id_padre = parent[0]
            # Verificar si ya existe visión
            cursor.execute("SELECT id_pagina FROM paginas WHERE slug = 'vision'")
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO paginas (slug, titulo, contenido, id_padre, mostrar_en_menu, orden_menu, estado, tipo)
                    VALUES ('vision', 'Visión', 'Nuestra visión es ser la mejor escuela...', %s, 1, 1, 'publicado', 'pagina')
                """, (id_padre,))
                print("Página Visión creada.")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Base de datos actualizada correctamente.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    update_db()
