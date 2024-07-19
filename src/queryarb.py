import mysql.connector
import time
from decimal import Decimal
from datetime import datetime

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'arbitrage_user',
    'password': 'Newpassword1!',
    'database': 'arbitrage_system'
}

def get_new_opportunities(last_id):
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor(dictionary=True)

    query = """
    SELECT * FROM arbitrage_opportunities 
    WHERE id > %s
    ORDER BY id ASC
    """

    cursor.execute(query, (last_id,))
    rows = cursor.fetchall()
    cursor.close()
    connection.close()
    return rows

def format_opportunity(opportunity):
    return (
        f"------\nID: {opportunity['id']}\n"
        f"Pair: {opportunity['pair']}\n"
        f"V2 Pair: {opportunity['v2_pair']}\n"
        f"V3 Pool: {opportunity['v3_pool']}\n"
        f"V2 Price: {opportunity['v2_price']}\n"
        f"V3 Price: {opportunity['v3_price']}\n"
        f"Basis Points: {opportunity['basis_points']}\n"
        f"Direction: {opportunity['direction']}\n"
        f"Timestamp: {opportunity['timestamp']}\n"
        f"Executed: {opportunity['executed']}\n"
        f"Execution Timestamp: {opportunity['execution_timestamp']}\n"
        "------"
    )

def main():
    last_id = 0
    while True:
        new_opportunities = get_new_opportunities(last_id)
        if new_opportunities:
            for opportunity in new_opportunities:
                print(format_opportunity(opportunity))
                last_id = opportunity['id']
        else:
            print("No new opportunities found.")
        
        time.sleep(5)

if __name__ == "__main__":
    main()
