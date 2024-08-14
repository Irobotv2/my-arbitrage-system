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
LIQUIDITY_IMBALANCE_THRESHOLD = 0.05  # 5%
SCAN_INTERVAL = 30  # seconds
RUN_TIME = 600  # 10 minutes

# Store triggers
triggers = []

def redis_operation_with_retry(operation, max_retries=3, delay=1):
    retries = 0
    while retries < max_retries:
        try:
            return operation()
        except RedisError as e:
            logger.warning(f"Redis operation failed: {str(e)}. Retrying in {delay} seconds...")
            retries += 1
            time.sleep(delay)
    
    logger.error(f"Redis operation failed after {max_retries} retries")
    return None

def validate_pool_data(pool_data, pool_type):
    if pool_type == 'v3':
        required_fields = ['liquidity', 'sqrtPriceX96']
    else:  # v2
        required_fields = ['reserve0', 'reserve1']
    
    for field in required_fields:
        if field not in pool_data:
            return False, f"Missing {field}"
        if not pool_data[field] or not pool_data[field].strip():
            return False, f"Empty {field}"
        try:
            Decimal(pool_data[field])
        except:
            return False, f"Invalid {field}"
    
    return True, "Valid"

def handle_v3_pool_data(pool_key, pool_data):
    if 'liquidity' not in pool_data or 'sqrtPriceX96' not in pool_data:
        missing_fields = []
        if 'liquidity' not in pool_data:
            missing_fields.append('liquidity')
        if 'sqrtPriceX96' not in pool_data:
            missing_fields.append('sqrtPriceX96')
        logger.warning(f"Missing data for V3 pool: {pool_key}. Missing fields: {', '.join(missing_fields)}")
        return None
    
    try:
        liquidity = Decimal(pool_data['liquidity'])
        sqrt_price_x96 = Decimal(pool_data['sqrtPriceX96'])
        return liquidity, sqrt_price_x96
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid data for V3 pool: {pool_key}. Error: {str(e)}")
        return None

def handle_v2_pool_data(pool_key, pool_data):
    if 'reserve0' not in pool_data or 'reserve1' not in pool_data:
        missing_fields = []
        if 'reserve0' not in pool_data:
            missing_fields.append('reserve0')
        if 'reserve1' not in pool_data:
            missing_fields.append('reserve1')
        logger.warning(f"Missing data for V2 pool: {pool_key}. Missing fields: {', '.join(missing_fields)}")
        return None
    
    try:
        reserve0 = Decimal(pool_data['reserve0'])
        reserve1 = Decimal(pool_data['reserve1'])
        return reserve0, reserve1
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid data for V2 pool: {pool_key}. Error: {str(e)}")
        return None

def log_price_deviation(token_symbol, deviation, threshold):
    logger.info(f"Token {token_symbol}: Deviation = {deviation:.2%}, Threshold = {threshold:.2%}")
    if deviation > threshold:
        logger.info(f"Price deviation detected for {token_symbol}")
    else:
        logger.info(f"No price deviation detected for {token_symbol}")

def log_liquidity_imbalance(pool_key, imbalance, threshold):
    logger.info(f"Pool {pool_key}: Imbalance = {imbalance:.2%}, Threshold = {threshold:.2%}")
    if imbalance > threshold:
        logger.info(f"Liquidity imbalance detected in pool {pool_key}")
    else:
        logger.info(f"No liquidity imbalance detected in pool {pool_key}")

async def check_v3_pool_data(pool_keys, num_pools=5):
    logger.info(f"Checking data for {num_pools} V3 pools:")
    for pool_key in pool_keys[:num_pools]:
        pool_data = redis_operation_with_retry(lambda: redis_client.hgetall(pool_key))
        if pool_data is None:
            continue
        logger.info(f"Pool: {pool_key}")
        logger.info(f"Data: {pool_data}")
        logger.info("---")

async def scan_price_deviations():
    logger.info("Scanning for price deviations...")
    all_tokens = redis_operation_with_retry(lambda: redis_client.keys("token:*"))
    if all_tokens is None:
        return
    logger.info(f"Found {len(all_tokens)} tokens")
    for token_key in all_tokens:
        token_data = redis_operation_with_retry(lambda: redis_client.hgetall(token_key))
        if token_data is None:
            continue
        token_address = token_data.get('address')
        token_symbol = token_data.get('symbol', 'Unknown')
        if not token_address:
            logger.warning(f"No address found for token: {token_key}")
            continue
        v2_pools = redis_operation_with_retry(lambda: redis_client.keys(f"uniswap_v2_pair:*:{token_address}:*"))
        v3_pools = redis_operation_with_retry(lambda: redis_client.keys(f"uniswap_v3_pool:*:{token_address}:*"))
        if v2_pools is None or v3_pools is None:
            continue
        all_pools = v2_pools + v3_pools
        
        logger.info(f"Token {token_symbol} ({token_address}): Found {len(all_pools)} pools")
        
        if len(all_pools) < 2:
            logger.info(f"Skipping {token_symbol} due to insufficient pools")
            continue  # Need at least 2 pools to compare prices
        
        prices = []
        for pool_key in all_pools:
            pool_data = redis_operation_with_retry(lambda: redis_client.hgetall(pool_key))
            if pool_data is None:
                continue
            if 'v3_pool' in pool_key:
                is_valid, message = validate_pool_data(pool_data, 'v3')
                if not is_valid:
                    logger.warning(f"Invalid V3 pool data: {message}")
                    continue
                result = handle_v3_pool_data(pool_key, pool_data)
                if result is None:
                    continue
                liquidity, sqrt_price_x96 = result
                price = (sqrt_price_x96 ** 2) / (2 ** 192)
                prices.append(Decimal(price))
                logger.info(f"V3 Pool {pool_key}: Price = {price}")
            else:  # V2 pool
                is_valid, message = validate_pool_data(pool_data, 'v2')
                if not is_valid:
                    logger.warning(f"Invalid V2 pool data: {message}")
                    continue
                if 'price' in pool_data:
                    try:
                        price = Decimal(pool_data['price'])
                        prices.append(price)
                        logger.info(f"V2 Pool {pool_key}: Price = {price}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid price data for V2 pool: {pool_key}. Error: {str(e)}")
                else:
                    logger.warning(f"No price data found for V2 pool: {pool_key}")
        
        if prices:
            max_price = max(prices)
            min_price = min(prices)
            deviation = (max_price - min_price) / min_price
            log_price_deviation(token_symbol, deviation, PRICE_DEVIATION_THRESHOLD)
            if deviation > PRICE_DEVIATION_THRESHOLD:
                triggers.append({
                    'type': 'price_deviation',
                    'token': token_symbol,
                    'deviation': f"{deviation:.2%}",
                    'timestamp': datetime.now().isoformat()
                })
        else:
            logger.warning(f"No valid prices found for token: {token_symbol}")
async def scan_liquidity_imbalances():
    logger.info("Scanning for liquidity imbalances...")
    v2_pools = redis_operation_with_retry(lambda: redis_client.keys("uniswap_v2_pair:*"))
    v3_pools = redis_operation_with_retry(lambda: redis_client.keys("uniswap_v3_pool:*"))
    if v2_pools is None or v3_pools is None:
        logger.warning("Failed to retrieve pool keys from Redis")
        return
    all_pools = v2_pools + v3_pools
    logger.info(f"Found {len(all_pools)} pools")
    for pool_key in all_pools:
        pool_data = redis_operation_with_retry(lambda: redis_client.hgetall(pool_key))
        if pool_data is None:
            logger.warning(f"Failed to retrieve data for pool: {pool_key}")
            continue
        if 'v3_pool' in pool_key:
            is_valid, message = validate_pool_data(pool_data, 'v3')
            if not is_valid:
                logger.warning(f"Invalid V3 pool data: {message}")
                continue
            result = handle_v3_pool_data(pool_key, pool_data)
            if result is None:
                continue
            liquidity, sqrt_price_x96 = result
            try:
                virtual_reserve0 = liquidity * (2**96) / sqrt_price_x96
                virtual_reserve1 = liquidity * sqrt_price_x96 / (2**96)
                if virtual_reserve1 == 0 or virtual_reserve0 == 0:
                    logger.warning(f"Zero virtual reserve found for V3 pool: {pool_key}")
                    continue
                imbalance = abs(virtual_reserve0 / virtual_reserve1 - 1)
                log_liquidity_imbalance(pool_key, imbalance, LIQUIDITY_IMBALANCE_THRESHOLD)
                if imbalance > LIQUIDITY_IMBALANCE_THRESHOLD:
                    triggers.append({
                        'type': 'liquidity_imbalance',
                        'pool': pool_key,
                        'imbalance': f"{imbalance:.2%}",
                        'timestamp': datetime.now().isoformat()
                    })
            except (ValueError, TypeError, ZeroDivisionError, decimal.InvalidOperation) as e:
                logger.warning(f"Error calculating imbalance for V3 pool: {pool_key}. Error: {str(e)}")
        else:  # V2 pool
            is_valid, message = validate_pool_data(pool_data, 'v2')
            if not is_valid:
                logger.warning(f"Invalid V2 pool data: {message}")
                continue
            result = handle_v2_pool_data(pool_key, pool_data)
            if result is None:
                continue
            reserve0, reserve1 = result
            try:
                if reserve0 == 0 or reserve1 == 0:
                    logger.warning(f"Zero reserve found for V2 pool: {pool_key}")
                    continue
                imbalance = abs(reserve0 / reserve1 - 1)
                log_liquidity_imbalance(pool_key, imbalance, LIQUIDITY_IMBALANCE_THRESHOLD)
                if imbalance > LIQUIDITY_IMBALANCE_THRESHOLD:
                    triggers.append({
                        'type': 'liquidity_imbalance',
                        'pool': pool_key,
                        'imbalance': f"{imbalance:.2%}",
                        'timestamp': datetime.now().isoformat()
                    })
            except (ValueError, TypeError, ZeroDivisionError, decimal.InvalidOperation) as e:
                logger.warning(f"Error calculating imbalance for V2 pool: {pool_key}. Error: {str(e)}")
    
    logger.info(f"Completed liquidity imbalance scan. Found {len(triggers)} potential imbalances.")
async def check_data_integrity():
    logger.info("Starting data integrity check...")
    report = []

    # Check tokens
    tokens = redis_operation_with_retry(lambda: redis_client.keys("token:*"))
    if tokens is None:
        report.append("ERROR: Unable to retrieve token keys from Redis")
    else:
        report.append(f"Found {len(tokens)} tokens")
        for token_key in tokens:
            token_data = redis_operation_with_retry(lambda: redis_client.hgetall(token_key))
            if token_data is None:
                report.append(f"ERROR: Unable to retrieve data for token {token_key}")
            else:
                if 'address' not in token_data:
                    report.append(f"ERROR: Missing address for token {token_key}")
                if 'symbol' not in token_data:
                    report.append(f"WARNING: Missing symbol for token {token_key}")

    # Check V2 pools
    v2_pools = redis_operation_with_retry(lambda: redis_client.keys("uniswap_v2_pair:*"))
    if v2_pools is None:
        report.append("ERROR: Unable to retrieve V2 pool keys from Redis")
    else:
        report.append(f"Found {len(v2_pools)} V2 pools")
        for pool_key in v2_pools:
            pool_data = redis_operation_with_retry(lambda: redis_client.hgetall(pool_key))
            if pool_data is None:
                report.append(f"ERROR: Unable to retrieve data for V2 pool {pool_key}")
            else:
                missing_fields = []
                for field in ['reserve0', 'reserve1', 'price']:
                    if field not in pool_data:
                        missing_fields.append(field)
                if missing_fields:
                    report.append(f"ERROR: Missing fields for V2 pool {pool_key}: {', '.join(missing_fields)}")

    # Check V3 pools
    v3_pools = redis_operation_with_retry(lambda: redis_client.keys("uniswap_v3_pool:*"))
    if v3_pools is None:
        report.append("ERROR: Unable to retrieve V3 pool keys from Redis")
    else:
        report.append(f"Found {len(v3_pools)} V3 pools")
        for pool_key in v3_pools:
            pool_data = redis_operation_with_retry(lambda: redis_client.hgetall(pool_key))
            if pool_data is None:
                report.append(f"ERROR: Unable to retrieve data for V3 pool {pool_key}")
            else:
                missing_fields = []
                for field in ['liquidity', 'sqrtPriceX96']:
                    if field not in pool_data:
                        missing_fields.append(field)
                if missing_fields:
                    report.append(f"ERROR: Missing fields for V3 pool {pool_key}: {', '.join(missing_fields)}")

    # Summary
    total_errors = sum(1 for line in report if line.startswith("ERROR"))
    total_warnings = sum(1 for line in report if line.startswith("WARNING"))
    report.append(f"\nData Integrity Check Summary:")
    report.append(f"Total Errors: {total_errors}")
    report.append(f"Total Warnings: {total_warnings}")

    # Log and return the report
    for line in report:
        logger.info(line)
    return report

async def main():
    start_time = datetime.now()
    end_time = start_time + timedelta(seconds=RUN_TIME)
    
    logger.info(f"Starting trigger scan at {start_time}. Will run until {end_time}")
    
    # Run data integrity check
    logger.info("Running data integrity check...")
    integrity_report = await check_data_integrity()
    
    # Save integrity report to file
    with open('data_integrity_report.txt', 'w') as f:
        f.write("\n".join(integrity_report))
    logger.info("Data integrity report saved to data_integrity_report.txt")
    
    # Check V3 pool data at the beginning
    v3_pools = redis_operation_with_retry(lambda: redis_client.keys("uniswap_v3_pool:*"))
    if v3_pools is not None:
        await check_v3_pool_data(v3_pools)
    
    while datetime.now() < end_time:
        logger.info(f"Starting scan iteration at {datetime.now()}")
        await asyncio.gather(
            scan_price_deviations(),
            scan_liquidity_imbalances()
        )
        logger.info(f"Completed scan iteration. Triggers found so far: {len(triggers)}")
        await asyncio.sleep(SCAN_INTERVAL)
    
    # Generate report
    logger.info("Scan completed. Generating report...")
    report = ["Trigger Scan Report", "===================", ""]
    report.append(f"Scan duration: {RUN_TIME} seconds")
    report.append(f"Total triggers detected: {len(triggers)}")
    report.append("")
    
    price_deviations = [t for t in triggers if t['type'] == 'price_deviation']
    liquidity_imbalances = [t for t in triggers if t['type'] == 'liquidity_imbalance']
    
    report.append(f"Price Deviations: {len(price_deviations)}")
    for trigger in price_deviations:
        report.append(f"  Token: {trigger['token']}, Deviation: {trigger['deviation']}, Time: {trigger['timestamp']}")
    
    report.append("")
    report.append(f"Liquidity Imbalances: {len(liquidity_imbalances)}")
    for trigger in liquidity_imbalances:
        report.append(f"  Pool: {trigger['pool']}, Imbalance: {trigger['imbalance']}, Time: {trigger['timestamp']}")
    
    # Save report to file
    with open('trigger_scan_report.txt', 'w') as f:
        f.write("\n".join(report))
    
    logger.info("Report saved to trigger_scan_report.txt")
    
    # Display all triggers
    logger.info("Displaying all triggers:")
    for trigger in triggers:
        logger.info(f"Trigger: {trigger}")

if __name__ == "__main__":
    asyncio.run(main())