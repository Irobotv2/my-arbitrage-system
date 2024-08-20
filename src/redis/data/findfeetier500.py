import redis

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Define the key for the WETH/USDC pair with 500 fee tier
key_prefix = "Uniswap V3:WETH/USDC:Fee tier 500"

# Query Redis for pool address, slot0 data, and quote
pool_address = redis_client.get(f"{key_prefix}")
slot0_data = redis_client.hgetall(f"{key_prefix}:slot0")
quote_data = redis_client.hgetall(f"{key_prefix}:quote")

# Print the results
print("WETH/USDC Pool (0.05% fee tier):")
print(f"Pool Address: {pool_address.decode() if pool_address else 'Not found'}")

print("\nSlot0 Data:")
for key, value in slot0_data.items():
    print(f"{key.decode()}: {value.decode()}")

print("\nQuote Data:")
for key, value in quote_data.items():
    print(f"{key.decode()}: {value.decode()}")