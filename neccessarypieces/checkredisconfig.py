import redis
import json
import random
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

def fetch_all_keys(pattern="*"):
    # Fetch all keys that match the pattern
    keys = redis_client.keys(pattern)
    logging.info(f"Fetched {len(keys)} keys from Redis.")
    return keys

def randomly_check_keys(keys, sample_size=5):
    # Randomly select a few keys to check
    if len(keys) == 0:
        logging.info("No keys found in Redis.")
        return

    random_keys = random.sample(keys, min(sample_size, len(keys)))
    logging.info(f"Randomly selected keys: {random_keys}")

    # Fetch and display configurations for the selected keys
    for key in random_keys:
        config = redis_client.get(key)
        if config:
            logging.info(f"Configuration for {key.decode('utf-8')}: {json.loads(config)}")
        else:
            logging.info(f"No configuration found for {key.decode('utf-8')}")

def main():
    # Fetch all keys with a specific pattern (e.g., those ending with '_config')
    keys = fetch_all_keys(pattern="*_config")
    randomly_check_keys(keys)

if __name__ == "__main__":
    main()
