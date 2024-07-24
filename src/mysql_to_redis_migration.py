import mysql.connector
import redis
from decimal import Decimal
import json
from datetime import datetime, date

# MySQL connection
mysql_conn = mysql.connector.connect(
    host="localhost",
    user="arbitrage_user",
    password="Newpassword1!",
    database="arbitrage_system"
)
mysql_cursor = mysql_conn.cursor(dictionary=True)

# Redis connection
redis_conn = redis.Redis(host='localhost', port=6379, db=0)

def json_serial(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode('utf-8')
    raise TypeError(f"Type {type(obj)} not serializable")

def clean_row(row):
    return {k: ('' if v is None else v) for k, v in row.items()}

def migrate_table(table_name, primary_key, index_fields=[]):
    mysql_cursor.execute(f"SELECT * FROM {table_name}")
    for row in mysql_cursor.fetchall():
        # Clean the row, replacing None with empty string
        row = clean_row(row)
        
        # Convert to JSON and back to handle special types
        row_json = json.dumps(row, default=json_serial)
        row = json.loads(row_json)
        
        # Store main data
        main_key = f"{table_name}:{row[primary_key]}"
        redis_conn.hset(main_key, mapping=row)
        
        # Create indexes
        for field in index_fields:
            if row[field]:  # Only create index if the field has a value
                index_key = f"{table_name}:index:{field}"
                redis_conn.sadd(index_key, row[primary_key])

# Migrate uniswap_v3_pools
migrate_table('uniswap_v3_pools', 'pool_address', ['token0_address', 'token1_address'])

# Migrate uniswap_v2_pairs
migrate_table('uniswap_v2_pairs', 'pair_address', ['token0_address', 'token1_address'])
# Close connections
mysql_cursor.close()
mysql_conn.close()

print("Migration completed successfully!")