import mysql.connector
from mysql.connector import Error

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'arbitrage_user',
    'password': 'Newpassword1!',
    'database': 'arbitrage_system',
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL database: {e}")
        return None

def execute_query(connection, query, params=None):
    cursor = connection.cursor(dictionary=True)
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor.fetchall()
    except Error as e:
        print(f"Error executing query: {e}")
        return None
    finally:
        cursor.close()

def get_token_symbol(connection, token_address):
    query = "SELECT symbol FROM tokens WHERE address = %s"
    result = execute_query(connection, query, (token_address,))
    return result[0]['symbol'] if result else token_address[:6]  # Return first 6 chars of address if symbol not found

def list_v3_pairs():
    connection = get_db_connection()
    if not connection:
        return

    try:
        # Get all V3 pools
        v3_pools = execute_query(connection, """
            SELECT pool_address, token0_address, token1_address
            FROM uniswap_v3_pools
        """)

        print("=== Uniswap V3 Token Pairs ===")
        for pool in v3_pools:
            token0_symbol = get_token_symbol(connection, pool['token0_address'])
            token1_symbol = get_token_symbol(connection, pool['token1_address'])
            print(f"{token0_symbol}/{token1_symbol}")

        print(f"\nTotal V3 pairs: {len(v3_pools)}")

    except Error as e:
        print(f"Error listing V3 pairs: {e}")
    finally:
        connection.close()

if __name__ == "__main__":
    list_v3_pairs()