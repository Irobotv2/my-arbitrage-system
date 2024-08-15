import asyncio
import aiohttp
import logging
from decimal import Decimal
import redis
import json
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# The Graph API setup
GRAPH_API_KEY = 'bde86d5008a99eaf066b94e4cfcad7fc'
GRAPH_API_URL = f'https://gateway.thegraph.com/api/{GRAPH_API_KEY}/subgraphs/id/FEtpnfQ1aqF8um2YktEkfzFD11ZKrfurvBLPeQzv9JB1'

# Redis setup
redis_client = redis.Redis(host='localhost', port=6379, db=0)

async def get_top_liquid_pairs():
    query = """
    {
      pairs(first: 100, orderBy: reserveUSD, orderDirection: desc) {
        id
        token0 {
          id
          symbol
          name
          decimals
        }
        token1 {
          id
          symbol
          name
          decimals
        }
        reserve0
        reserve1
        totalSupply
        reserveUSD
        token0Price
        token1Price
        volumeUSD
        untrackedVolumeUSD
        txCount
        createdAtTimestamp
      }
    }
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GRAPH_API_URL, json={'query': query}) as response:
                if response.status != 200:
                    logging.error(f"Error querying The Graph API: {response.status}")
                    return []
                data = await response.json()
        
        pairs = data.get('data', {}).get('pairs', [])
        return pairs
    except Exception as e:
        logging.error(f"Error fetching top liquid pairs: {str(e)}")
        return []

def is_valid_pair(pair):
    return (pair['token0']['symbol'].lower() != 'unknown' and
            pair['token1']['symbol'].lower() != 'unknown' and
            pair['token0']['name'].lower() != 'unknown' and
            pair['token1']['name'].lower() != 'unknown')


def insert_pair_data(pair):
    pair_key = f"Uniswap V2:{pair['token0']['symbol']}/{pair['token1']['symbol']}"
    
    # Calculate 24h fees (assuming 0.3% fee for Uniswap V2)
    volume_usd = float(pair['volumeUSD']) + float(pair['untrackedVolumeUSD'])
    fees_24h = volume_usd * 0.003
    
    # Correct price interpretation
    token0_price_in_token1 = float(pair['token1Price'])  # This is the price of token0 in terms of token1
    token1_price_in_token0 = float(pair['token0Price'])  # This is the price of token1 in terms of token0
    
    pair_data = {
        "pair_address": pair['id'],
        "token0": json.dumps({
            "address": pair['token0']['id'],
            "symbol": pair['token0']['symbol'],
            "name": pair['token0']['name'],
            "decimals": pair['token0']['decimals']
        }),
        "token1": json.dumps({
            "address": pair['token1']['id'],
            "symbol": pair['token1']['symbol'],
            "name": pair['token1']['name'],
            "decimals": pair['token1']['decimals']
        }),
        "reserve0": pair['reserve0'],
        "reserve1": pair['reserve1'],
        "total_supply_lp_tokens": pair['totalSupply'],
        "reserveUSD": pair['reserveUSD'],
        f"{pair['token0']['symbol']}_price_in_{pair['token1']['symbol']}": str(token0_price_in_token1),
        f"{pair['token1']['symbol']}_price_in_{pair['token0']['symbol']}": str(token1_price_in_token0),
        "volume_24h": str(volume_usd),
        "fees_24h": str(fees_24h),
        "tx_count": pair['txCount'],
        "created_at": pair['createdAtTimestamp'],
        "last_updated": str(int(datetime.now().timestamp()))
    }
    redis_client.hset(pair_key, mapping=pair_data)
    
    # Set expiration for the data (e.g., 5 minutes)
    redis_client.expire(pair_key, 300)

    # Log the information with correct price interpretation
    logging.info(f"\nPair: {pair['token0']['symbol']} / {pair['token1']['symbol']}")
    logging.info(f"Pair Address: {pair['id']}")
    logging.info(f"Token 0: {pair['token0']['name']} ({pair['token0']['symbol']}) - {pair['token0']['id']}")
    logging.info(f"Token 1: {pair['token1']['name']} ({pair['token1']['symbol']}) - {pair['token1']['id']}")
    logging.info(f"Reserve USD: ${Decimal(pair['reserveUSD']):.2f}")
    logging.info(f"1 {pair['token0']['symbol']} = {token0_price_in_token1:.8f} {pair['token1']['symbol']}")
    logging.info(f"1 {pair['token1']['symbol']} = {token1_price_in_token0:.8f} {pair['token0']['symbol']}")
    logging.info(f"Inserted pair data into Redis: {pair_key}")

async def main():
    logging.info("Clearing Redis database...")
    redis_client.flushdb()
    
    logging.info("Fetching top liquid Uniswap V2 pairs...")
    all_pairs = await get_top_liquid_pairs()
    
    if not all_pairs:
        logging.error("Failed to fetch pairs. Exiting.")
        return

    valid_pairs = [pair for pair in all_pairs if is_valid_pair(pair)]
    top_10_valid_pairs = valid_pairs[:10]

    logging.info(f"Successfully fetched {len(top_10_valid_pairs)} valid pairs.")
    
    for pair in top_10_valid_pairs:
        token0 = pair['token0']
        token1 = pair['token1']
        pair_key = f"Uniswap V2:{token0['symbol']}/{token1['symbol']}"
        logging.info(f"\nPair: {token0['symbol']} / {token1['symbol']}")
        logging.info(f"Pair Address: {pair['id']}")
        logging.info(f"Token 0: {token0['name']} ({token0['symbol']}) - {token0['id']}")
        logging.info(f"Token 1: {token1['name']} ({token1['symbol']}) - {token1['id']}")
        logging.info(f"Reserve USD: ${Decimal(pair['reserveUSD']):.2f}")
        logging.info(f"Token 0 Price: {Decimal(pair['token0Price']):.8f}")
        logging.info(f"Token 1 Price: {Decimal(pair['token1Price']):.8f}")
        
        # Insert pair data into Redis
        insert_pair_data(pair)
        logging.info(f"Inserted pair data into Redis: {pair_key}")

if __name__ == "__main__":
    asyncio.run(main())