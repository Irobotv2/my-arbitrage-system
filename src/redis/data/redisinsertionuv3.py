import asyncio
import aiohttp
import logging
from decimal import Decimal
import redis
import json
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# The Graph API setup for Uniswap V3
GRAPH_API_KEY = 'bde86d5008a99eaf066b94e4cfcad7fc'
GRAPH_API_URL = f'https://gateway.thegraph.com/api/{GRAPH_API_KEY}/subgraphs/id/4cKy6QQMc5tpfdx8yxfYeb9TLZmgLQe44ddW1G7NwkA6'

# Redis setup
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

async def check_api_connection():
    query = """
    {
      _meta {
        block {
          number
        }
        deployment
        hasIndexingErrors
      }
    }
    """
    try:
        timeout = aiohttp.ClientTimeout(total=60)  # 60 seconds timeout
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(GRAPH_API_URL, json={'query': query}) as response:
                if response.status != 200:
                    logging.error(f"API check failed. Status: {response.status}")
                    logging.error(f"Response content: {await response.text()}")
                    return False
                data = await response.json()
                if '_meta' in data.get('data', {}):
                    logging.info("API connection successful")
                    return True
                else:
                    logging.error("API response doesn't contain expected data")
                    return False
    except Exception as e:
        logging.error(f"Error checking API connection: {str(e)}")
        return False
async def get_random_pools():
    query = """
    {
      pool100: liquidityPools(
        first: 5,
        where: {fees_: {feePercentage: 0.0001}}
      ) {
        ...poolFields
      }
      pool500: liquidityPools(
        first: 5,
        where: {fees_: {feePercentage: 0.0005}}
      ) {
        ...poolFields
      }
      pool3000: liquidityPools(
        first: 5,
        where: {fees_: {feePercentage: 0.003}}
      ) {
        ...poolFields
      }
      pool10000: liquidityPools(
        first: 5,
        where: {fees_: {feePercentage: 0.01}}
      ) {
        ...poolFields
      }
    }

    fragment poolFields on LiquidityPool {
      id
      inputTokens {
        id
        symbol
        name
        decimals
      }
      fees {
        feePercentage
      }
      totalValueLockedUSD
      inputTokenBalances
      cumulativeVolumeUSD
      cumulativeTotalRevenueUSD
      createdTimestamp
    }
    """
    
    # ... rest of the function remains the same
    
    for attempt in range(MAX_RETRIES):
        try:
            timeout = aiohttp.ClientTimeout(total=120)  # Increased timeout to 120 seconds
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(GRAPH_API_URL, json={'query': query}) as response:
                    if response.status != 200:
                        logging.error(f"Error querying The Graph API: Status {response.status}")
                        logging.error(f"Response content: {await response.text()}")
                        if attempt < MAX_RETRIES - 1:
                            backoff_time = (2 ** attempt) * RETRY_DELAY
                            logging.info(f"Retrying in {backoff_time} seconds...")
                            await asyncio.sleep(backoff_time)
                            continue
                        return []
                    data = await response.json()
            
            pools = []
            for fee_tier in ['pool100', 'pool500', 'pool3000', 'pool10000']:
                pools.extend(data.get('data', {}).get(fee_tier, []))
            
            if not pools:
                logging.warning("No pools data found in the API response")
            return pools
        except asyncio.TimeoutError:
            logging.error(f"Request timed out on attempt {attempt + 1}")
        except aiohttp.ClientError as e:
            logging.error(f"AIOHTTP ClientError on attempt {attempt + 1}: {str(e)}")
        except Exception as e:
            logging.error(f"Unexpected error on attempt {attempt + 1}: {str(e)}")
        
        if attempt < MAX_RETRIES - 1:
            backoff_time = (2 ** attempt) * RETRY_DELAY
            logging.info(f"Retrying in {backoff_time} seconds...")
            await asyncio.sleep(backoff_time)
    
    logging.error(f"Failed to fetch pools after {MAX_RETRIES} attempts")
    return []

def is_valid_pool(pool):
    return (len(pool['inputTokens']) == 2 and
            all(token['symbol'].lower() != 'unknown' for token in pool['inputTokens']) and
            pool['fees'] and len(pool['fees']) > 0)

def insert_pool_data(pool):
    token0, token1 = pool['inputTokens']
    fee_tier = int(float(pool['fees'][0]['feePercentage']) * 10000)  # Convert to basis points
    pool_key = f"Uniswap V3:{token0['symbol']}/{token1['symbol']}:{fee_tier}"
    
    pool_data = {
        "pool_address": pool['id'],
        "token0": json.dumps({
            "address": token0['id'],
            "symbol": token0['symbol'],
            "name": token0['name'],
            "decimals": token0['decimals']
        }),
        "token1": json.dumps({
            "address": token1['id'],
            "symbol": token1['symbol'],
            "name": token1['name'],
            "decimals": token1['decimals']
        }),
        "fee_tier": str(fee_tier),
        "reserve0": pool['inputTokenBalances'][0],
        "reserve1": pool['inputTokenBalances'][1],
        "reserveUSD": pool['totalValueLockedUSD'],
        "volume_24h": pool['cumulativeVolumeUSD'],
        "fees_24h": pool['cumulativeTotalRevenueUSD'],
        "created_at": pool['createdTimestamp'],
        "last_updated": str(int(datetime.now().timestamp()))
    }
    
    # Calculate token prices (this is an approximation)
    reserve0 = float(pool['inputTokenBalances'][0])
    reserve1 = float(pool['inputTokenBalances'][1])
    if reserve0 > 0 and reserve1 > 0:
        pool_data[f"{token0['symbol']}_price_in_{token1['symbol']}"] = str(reserve1 / reserve0)
        pool_data[f"{token1['symbol']}_price_in_{token0['symbol']}"] = str(reserve0 / reserve1)
    
    redis_client.hset(pool_key, mapping=pool_data)
    redis_client.expire(pool_key, 300)  # Set expiration for 5 minutes

    # Log the information
    logging.info(f"\nPool: {token0['symbol']} / {token1['symbol']} (Fee Tier: {fee_tier} bps)")
    logging.info(f"Pool Address: {pool['id']}")
    logging.info(f"TVL USD: ${Decimal(pool['totalValueLockedUSD']):.2f}")
    logging.info(f"Fee Tier: {fee_tier} bps")
    logging.info(f"Inserted pool data into Redis: {pool_key}")

async def main():
    logging.info("Starting the script...")
    logging.info("Checking API connection...")
    if not await check_api_connection():
        logging.error("Failed to connect to the API. Exiting.")
        return

    logging.info("Clearing Redis database...")
    redis_client.flushdb()
    
    logging.info("Fetching random Uniswap V3 pools across all fee tiers...")
    all_pools = await get_random_pools()
    
    if not all_pools:
        logging.error("Failed to fetch pools. Exiting.")
        return

    logging.info(f"Fetched {len(all_pools)} pools. Filtering valid pools...")
    valid_pools = [pool for pool in all_pools if is_valid_pool(pool)]

    logging.info(f"Successfully fetched {len(valid_pools)} valid pools.")
    
    for i, pool in enumerate(valid_pools, 1):
        logging.info(f"Inserting pool {i} of {len(valid_pools)}...")
        insert_pool_data(pool)
    
    logging.info("Script completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())