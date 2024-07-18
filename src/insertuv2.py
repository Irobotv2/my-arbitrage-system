import mysql.connector
from mysql.connector import Error
import requests
from decimal import Decimal

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'arbitrage_user',
    'password': 'Newpassword1!',
    'database': 'arbitrage_system',
}

# API configuration
API_KEY = "bde86d5008a99eaf066b94e4cfcad7fc"
UNISWAP_V2_URL = f"https://gateway-arbitrum.network.thegraph.com/api/{API_KEY}/subgraphs/id/2ZXJn1QPvBpS1UVAsSMvqeGm3XvN29GVo75pXafmiNFb"

def execute_query(connection, query, params=None):
    cursor = connection.cursor()
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        connection.commit()
    except Error as e:
        print(f"Error: '{e}'")

def fetch_v3_pairs_from_db(connection):
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT DISTINCT token0_address, token1_address
        FROM uniswap_v3_pools
    """)
    return cursor.fetchall()

def fetch_v2_pair(token0, token1):
    query = """
    {
      pairs(where: {token0: "%s", token1: "%s"}) {
        id
        token0 {
          id
          symbol
        }
        token1 {
          id
          symbol
        }
        reserve0
        reserve1
        reserveUSD
      }
    }
    """ % (token0, token1)
    response = requests.post(UNISWAP_V2_URL, json={'query': query})
    if response.status_code == 200:
        pairs = response.json()['data']['pairs']
        return pairs[0] if pairs else None
    else:
        raise Exception(f"Failed to fetch V2 pair: {response.text}")

def insert_token_if_not_exists(cursor, token_address, token_symbol):
    cursor.execute("""
        INSERT IGNORE INTO tokens (address, symbol) 
        VALUES (%s, %s)
    """, (token_address, token_symbol))

def insert_or_update_v2_pair(cursor, pair):
    if pair:
        cursor.execute("""
            INSERT INTO uniswap_v2_pairs 
            (pair_address, token0_address, token1_address, reserve0, reserve1, total_liquidity_usd) 
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            token0_address = VALUES(token0_address),
            token1_address = VALUES(token1_address),
            reserve0 = VALUES(reserve0),
            reserve1 = VALUES(reserve1),
            total_liquidity_usd = VALUES(total_liquidity_usd)
        """, (
            pair['id'],
            pair['token0']['id'],
            pair['token1']['id'],
            Decimal(pair['reserve0']),
            Decimal(pair['reserve1']),
            Decimal(pair['reserveUSD'])
        ))
        print(f"Inserted/Updated V2 pair: {pair['id']}")
    else:
        print(f"No V2 pair found for tokens {pair['token0']['id']} and {pair['token1']['id']}")

def populate_v2_pairs():
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    try:
        # Fetch V3 pairs from database
        v3_pairs = fetch_v3_pairs_from_db(connection)

        for pair in v3_pairs:
            # Fetch corresponding V2 pair
            v2_pair = fetch_v2_pair(pair['token0_address'], pair['token1_address'])
            
            if v2_pair:
                # Insert tokens if they don't exist
                insert_token_if_not_exists(cursor, v2_pair['token0']['id'], v2_pair['token0']['symbol'])
                insert_token_if_not_exists(cursor, v2_pair['token1']['id'], v2_pair['token1']['symbol'])

                # Insert or update V2 pair
                insert_or_update_v2_pair(cursor, v2_pair)
            else:
                print(f"No V2 pair found for tokens {pair['token0_address']} and {pair['token1_address']}")

        connection.commit()
        print("Database population completed successfully.")

    except Exception as e:
        print(f"An error occurred: {e}")
        connection.rollback()

    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    populate_v2_pairs()