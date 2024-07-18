import mysql.connector
from mysql.connector import Error
import requests
import time
from decimal import Decimal  #
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
UNISWAP_V3_URL = f"https://gateway-arbitrum.network.thegraph.com/api/{API_KEY}/subgraphs/id/5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV"
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

def fetch_top_pairs_v2():
    query = """
    {
      pairs(first: 100, orderBy: reserveUSD, orderDirection: desc) {
        id
        token0 {
          id
          symbol
        }
        token1 {
          id
          symbol
        }
        reserveUSD
      }
    }
    """
    response = requests.post(UNISWAP_V2_URL, json={'query': query})
    if response.status_code == 200:
        return response.json()['data']['pairs']
    else:
        raise Exception(f"Failed to fetch V2 pairs: {response.text}")

def fetch_top_pairs_v3():
    query = """
    {
      pools(first: 100, orderBy: totalValueLockedUSD, orderDirection: desc) {
        id
        token0 {
          id
          symbol
        }
        token1 {
          id
          symbol
        }
        totalValueLockedUSD
        liquidity
      }
    }
    """
    response = requests.post(UNISWAP_V3_URL, json={'query': query})
    if response.status_code == 200:
        return response.json()['data']['pools']
    else:
        raise Exception(f"Failed to fetch V3 pools: {response.text}")

def insert_token_if_not_exists(cursor, token_address, token_symbol):
    cursor.execute("""
        INSERT IGNORE INTO tokens (address, symbol) 
        VALUES (%s, %s)
    """, (token_address, token_symbol))

def check_and_update_database():
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    try:
        # Fetch current data from database
        cursor.execute("SELECT pool_address, liquidity FROM uniswap_v3_pools")
        db_v3_pools = {row[0]: int(row[1]) for row in cursor.fetchall()}

        # Fetch current top pairs from API
        api_v3_pools = fetch_top_pairs_v3()

        # Check and update V3 pools
        for pool in api_v3_pools:
            # Insert tokens if they don't exist
            insert_token_if_not_exists(cursor, pool['token0']['id'], pool['token0']['symbol'])
            insert_token_if_not_exists(cursor, pool['token1']['id'], pool['token1']['symbol'])

            if pool['id'] not in db_v3_pools:
                print(f"Adding new V3 pool: {pool['id']}")
                try:
                    cursor.execute("""
                        INSERT INTO uniswap_v3_pools 
                        (pool_address, token0_address, token1_address, liquidity) 
                        VALUES (%s, %s, %s, %s)
                    """, (pool['id'], pool['token0']['id'], pool['token1']['id'], int(pool['liquidity'])))
                except mysql.connector.IntegrityError as e:
                    if e.errno == 1062:  # Duplicate entry error
                        print(f"Pool {pool['id']} already exists. Updating instead.")
                        cursor.execute("""
                            UPDATE uniswap_v3_pools 
                            SET token0_address = %s, token1_address = %s, liquidity = %s
                            WHERE pool_address = %s
                        """, (pool['token0']['id'], pool['token1']['id'], int(pool['liquidity']), pool['id']))
                    else:
                        raise
            else:
                print(f"Updating V3 pool: {pool['id']}")
                cursor.execute("""
                    UPDATE uniswap_v3_pools 
                    SET liquidity = %s
                    WHERE pool_address = %s
                """, (int(pool['liquidity']), pool['id']))

        connection.commit()
        print("Database check and update completed successfully.")

    except Exception as e:
        print(f"An error occurred: {e}")
        connection.rollback()

    finally:
        cursor.close()
        connection.close()

if __name__ == "__main__":
    check_and_update_database()