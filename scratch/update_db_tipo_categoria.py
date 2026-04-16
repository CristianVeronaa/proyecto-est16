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
        
        # Modificar el enum de tipo
        cursor.execute("ALTER TABLE paginas MODIFY COLUMN tipo ENUM('pagina', 'taller', 'categoria') DEFAULT 'pagina'")
        print("Tipo 'categoria' añadido correctamente.")
        
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    update_db()
