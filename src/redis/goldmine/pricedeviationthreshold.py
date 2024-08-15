import asyncio
import redis
import logging
from datetime import datetime, timedelta
from decimal import Decimal
import time
from redis.exceptions import RedisError

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add a stream handler to output logs to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)

# Initialize Redis client
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Constants
PRICE_DEVIATION_THRESHOLD = 0.005  # 0.5%
SCAN_INTERVAL = 30  # seconds
RUN_TIME = 600  # 10 minutes
MIN_POOLS_PER_TOKEN = 2  # Minimum number of pools required for a token to be considered

# Store triggers
triggers = []

def redis_operation_with_retry(operation, max_retries=3, delay=1):
    for _ in range(max_retries):
        try:
            return operation()
        except RedisError as e:
            logger.warning(f"Redis operation failed: {str(e)}. Retrying in {delay} seconds...")
            time.sleep(delay)
    logger.error(f"Redis operation failed after {max_retries} retries")
    return None
def get_pool_price(pool_data, is_v3):
    try:
        if is_v3:
            if 'sqrtPriceX96' in pool_data:
                sqrt_price_x96 = Decimal(pool_data['sqrtPriceX96'])
                price = (sqrt_price_x96 ** 2) / (2 ** 192)
            else:
                logger.warning(f"Missing sqrtPriceX96 in V3 pool data")
                return None
        else:  # V2 pool
            if 'reserve0' in pool_data and 'reserve1' in pool_data:
                reserve0 = Decimal(pool_data['reserve0'])
                reserve1 = Decimal(pool_data['reserve1'])
                if reserve0 == 0:
                    return None
                price = reserve1 / reserve0
            else:
                logger.warning(f"Missing reserves in V2 pool data")
                return None
        return price
    except (KeyError, ValueError, ZeroDivisionError) as e:
        logger.warning(f"Error calculating price: {str(e)}")
        return None
async def scan_price_deviations():
    logger.info("Scanning for price deviations...")
    all_tokens = redis_operation_with_retry(lambda: redis_client.keys("token:*"))
    if all_tokens is None:
        return

    tokens_with_sufficient_pools = 0
    tokens_processed = 0

    for token_key in all_tokens:
        tokens_processed += 1
        token_data = redis_operation_with_retry(lambda: redis_client.hgetall(token_key))
        if token_data is None:
            continue
        token_address = token_key.split(':')[1]  # Extract address from key
        token_symbol = token_data.get('symbol', 'Unknown')

        # Get all pools
        all_pools = redis_operation_with_retry(lambda: redis_client.keys(f"uniswap_v*_*:{token_address}*") + 
                                                       redis_client.keys(f"uniswap_v*_*:*{token_address}"))
        if all_pools is None:
            continue
        
        logger.info(f"Token {token_symbol} ({token_address}): Found {len(all_pools)} pools")
        
        if len(all_pools) < MIN_POOLS_PER_TOKEN:
            logger.info(f"Skipping {token_symbol} due to insufficient pools (found {len(all_pools)}, need at least {MIN_POOLS_PER_TOKEN})")
            continue

        tokens_with_sufficient_pools += 1
        
        prices = []
        for pool_key in all_pools:
            pool_data = redis_operation_with_retry(lambda: redis_client.hgetall(pool_key))
            if pool_data is None:
                continue
            is_v3 = 'v3_pool' in pool_key
            price = get_pool_price(pool_data, is_v3)
            if price is not None:
                prices.append((price, pool_key))
                logger.info(f"{'V3' if is_v3 else 'V2'} Pool {pool_key}: Price = {price}")
        
        if len(prices) >= MIN_POOLS_PER_TOKEN:
            max_price, max_pool = max(prices, key=lambda x: x[0])
            min_price, min_pool = min(prices, key=lambda x: x[0])
            deviation = (max_price - min_price) / min_price
            logger.info(f"Token {token_symbol}: Max Price = {max_price} ({max_pool}), Min Price = {min_price} ({min_pool}), Deviation = {deviation:.4%}")
            if deviation > PRICE_DEVIATION_THRESHOLD:
                logger.info(f"Price deviation detected for {token_symbol}")
                triggers.append({
                    'type': 'price_deviation',
                    'token': token_symbol,
                    'deviation': f"{deviation:.2%}",
                    'max_price_pool': max_pool,
                    'min_price_pool': min_pool,
                    'max_price': str(max_price),
                    'min_price': str(min_price),
                    'timestamp': datetime.now().isoformat()
                })
            else:
                logger.info(f"No significant price deviation detected for {token_symbol}")
        else:
            logger.warning(f"Insufficient valid prices found for token: {token_symbol}")

    logger.info(f"Processed {tokens_processed} tokens, {tokens_with_sufficient_pools} had sufficient pools for analysis")
async def main():
    start_time = datetime.now()
    end_time = start_time + timedelta(seconds=RUN_TIME)
    
    logger.info(f"Starting price deviation scan at {start_time}. Will run until {end_time}")
    
    while datetime.now() < end_time:
        logger.info(f"Starting scan iteration at {datetime.now()}")
        await scan_price_deviations()
        logger.info(f"Completed scan iteration. Triggers found so far: {len(triggers)}")
        await asyncio.sleep(SCAN_INTERVAL)
    
    # Generate report
    logger.info("Scan completed. Generating report...")
    report = ["Price Deviation Scan Report", "============================", ""]
    report.append(f"Scan duration: {RUN_TIME} seconds")
    report.append(f"Total triggers detected: {len(triggers)}")
    report.append("")
    report.append("Detected Price Deviations:")
    for trigger in triggers:
        report.append(f"  Token: {trigger['token']}")
        report.append(f"    Deviation: {trigger['deviation']}")
        report.append(f"    Max Price: {trigger['max_price']} ({trigger['max_price_pool']})")
        report.append(f"    Min Price: {trigger['min_price']} ({trigger['min_price_pool']})")
        report.append(f"    Time: {trigger['timestamp']}")
        report.append("")
    
    # Save report to file
    with open('price_deviation_report.txt', 'w') as f:
        f.write("\n".join(report))
    
    logger.info("Report saved to price_deviation_report.txt")
    
    # Display all triggers
    logger.info("Displaying all triggers:")
    for trigger in triggers:
        logger.info(f"Trigger: {trigger}")

if __name__ == "__main__":
    asyncio.run(main())