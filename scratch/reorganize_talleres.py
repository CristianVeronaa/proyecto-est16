import mysql.connector

def reorganize_talleres():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="control_est16"
        )
        cursor = conn.cursor(dictionary=True)
        
        # 1. Crear la categoría "Talleres"
        cursor.execute("SELECT id_pagina FROM paginas WHERE slug = 'categoria-talleres'")
        cat_talleres = cursor.fetchone()
        
        if not cat_talleres:
            print("Creando categoría 'Talleres'...")
            cursor.execute("""
                INSERT INTO paginas (slug, titulo, contenido, tipo, mostrar_en_menu, orden_menu, estado)
                VALUES ('categoria-talleres', 'Talleres', 'Conoce nuestros talleres tecnológicos.', 'categoria', 1, 2, 'publicado')
            """)
            conn.commit()
            cursor.execute("SELECT LAST_INSERT_ID() as id")
            id_cat = cursor.fetchone()['id']
            print(f"Categoría 'Talleres' creada con ID: {id_cat}")
        else:
            id_cat = cat_talleres['id_pagina']
            print(f"Categoría 'Talleres' ya existe con ID: {id_cat}")
            # Asegurarse que sea categoría y esté en el menú
            cursor.execute("UPDATE paginas SET tipo = 'categoria', mostrar_en_menu = 1 WHERE id_pagina = %s", (id_cat,))

        # 2. Mover los talleres existentes bajo esta categoría
        cursor.execute("UPDATE paginas SET id_padre = %s, mostrar_en_menu = 1 WHERE tipo = 'taller'", (id_cat,))
        print("Talleres movidos bajo la categoría 'Talleres'.")

        # 3. Asegurar que "Acerca de nosotros" esté en orden 1
        cursor.execute("UPDATE paginas SET orden_menu = 1 WHERE slug = 'acerca-de-nosotros'")
        
        # 4. (Opcional) Si hay una página llamada "Avisos" o quieres agruparlos
        # Por ahora el usuario solo pidió talleres como Acerca de nosotros.

        conn.commit()
        cursor.close()
        conn.close()
        print("Sincronización de menú completada.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    reorganize_talleres()
