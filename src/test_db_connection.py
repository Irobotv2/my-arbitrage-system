import mysql.connector

# Database connection details
db_config = {
    'user': 'root',
    'password': 'NewPassword1!',
    'host': '127.0.0.1',
    'database': 'ArbitrageSystem',
    'raise_on_warnings': True
}

try:
    # Establish a database connection
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()

    # Execute a simple query
    cursor.execute("SHOW TABLES")

    # Print the results
    for table in cursor:
        print(table)

except mysql.connector.Error as err:
    print(f"Error: {err}")

finally:
    cursor.close()
    connection.close()
