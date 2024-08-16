import logging
from decimal import Decimal

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
LIQUIDITY_IMBALANCE_THRESHOLD = 0.05  # 5%

# Mock Redis client
class MockRedis:
    def __init__(self):
        self.data = {}

    def hgetall(self, key):
        return self.data.get(key, {})

    def keys(self, pattern):
        return [k for k in self.data.keys() if k.startswith(pattern.replace('*', ''))]

redis_client = MockRedis()

# Helper function to get token symbol
def get_token_symbol(address):
    return redis_client.hgetall(f"token:{address}").get('symbol', address[:10])

# Function to verify liquidity imbalance
def verify_liquidity_imbalance(pool_data):
    logger.info(f"Verifying liquidity imbalance for pool: {pool_data.get('address', 'Unknown')}")
    try:
        if 'reserve0' in pool_data and 'reserve1' in pool_data:  # V2 pool
            reserve0 = Decimal(pool_data['reserve0'])
            reserve1 = Decimal(pool_data['reserve1'])
            if reserve0 == 0 or reserve1 == 0:
                logger.warning(f"Zero reserve detected in V2 pool: {pool_data.get('address', 'Unknown')}")
                return None
            
            # Calculate the current price ratio
            current_ratio = reserve1 / reserve0
            
            # Assume the expected ratio is 1:1 for simplicity
            # In a real scenario, you'd need to fetch the expected price from an oracle or other source
            expected_ratio = Decimal('1.0')
            
            # Calculate the imbalance as the relative difference from the expected ratio
            imbalance = abs(current_ratio / expected_ratio - 1)
            
            logger.info(f"V2 pool imbalance: {imbalance:.4f} (current ratio: {current_ratio:.4f}, expected ratio: {expected_ratio:.4f})")
        
        elif 'liquidity' in pool_data and 'sqrtPriceX96' in pool_data:  # V3 pool
            liquidity = Decimal(pool_data['liquidity'])
            sqrt_price_x96 = Decimal(pool_data['sqrtPriceX96'])
            if sqrt_price_x96 == 0:
                logger.warning(f"Zero sqrtPriceX96 detected in V3 pool: {pool_data.get('address', 'Unknown')}")
                return None
            
            # Calculate the current price from sqrtPriceX96
            current_price = (sqrt_price_x96 / 2**96) ** 2
            
            # Assume the expected price is 1:1 for simplicity
            # In a real scenario, you'd need to fetch the expected price from an oracle or other source
            expected_price = Decimal('1.0')
            
            # Calculate the imbalance as the relative difference from the expected price
            imbalance = abs(current_price / expected_price - 1)
            
            logger.info(f"V3 pool imbalance: {imbalance:.4f} (current price: {current_price:.4f}, expected price: {expected_price:.4f})")
        
        else:
            logger.warning(f"Invalid pool data format: {pool_data}")
            return None
        
        return imbalance
    except Exception as e:
        logger.error(f"Error in verify_liquidity_imbalance: {e}")
        return None

# Function to scan for liquidity imbalances
def scan_liquidity_imbalances():
    logger.info("Starting liquidity imbalance scan...")
    opportunities = []
    v2_pools = redis_client.keys("uniswap_v2_pair:*")
    v3_pools = redis_client.keys("uniswap_v3_pool:*")
    all_pools = v2_pools + v3_pools
    
    for pool_key in all_pools:
        logger.info(f"Checking pool: {pool_key}")
        pool_data = redis_client.hgetall(pool_key)
        imbalance = verify_liquidity_imbalance(pool_data)
        
        if imbalance is not None and imbalance > LIQUIDITY_IMBALANCE_THRESHOLD:
            logger.info(f"Imbalance opportunity detected: {imbalance:.4f}")
            opportunities.append({
                'type': 'liquidity_imbalance',
                'pool': pool_key,
                'imbalance': imbalance,
                'token0': pool_data['token0'],
                'token1': pool_data['token1']
            })
    
    logger.info(f"Scan complete. Found {len(opportunities)} opportunities.")
    return opportunities

# Mock data setup
def setup_mock_data():
    # Token data (unchanged)
    redis_client.data["token:0x1111"] = {"symbol": "TOKEN_A", "address": "0x1111"}
    redis_client.data["token:0x2222"] = {"symbol": "TOKEN_B", "address": "0x2222"}
    redis_client.data["token:0x3333"] = {"symbol": "TOKEN_C", "address": "0x3333"}

    # V2 pools
    redis_client.data["uniswap_v2_pair:0xaaaa"] = {
        "address": "0xaaaa",
        "token0": "0x1111",
        "token1": "0x2222",
        "reserve0": "1000000000000000000000",  # 1000 TOKEN_A
        "reserve1": "990000000000000000000"    # 990 TOKEN_B (1% imbalance)
    }
    redis_client.data["uniswap_v2_pair:0xbbbb"] = {
        "address": "0xbbbb",
        "token0": "0x1111",
        "token1": "0x2222",
        "reserve0": "1000000000000000000000",  # 1000 TOKEN_A
        "reserve1": "1100000000000000000000"   # 1100 TOKEN_B (10% imbalance)
    }

    # V3 pool
    redis_client.data["uniswap_v3_pool:0xcccc"] = {
        "address": "0xcccc",
        "token0": "0x2222",
        "token1": "0x3333",
        "liquidity": "1000000000000000000",
        "sqrtPriceX96": "82959809221060520845745313930"  # Represents a ~10% price deviation from 1:1
    }
# Main execution
def main():
    logger.info("Setting up mock data...")
    setup_mock_data()

    logger.info("Starting liquidity imbalance test...")
    opportunities = scan_liquidity_imbalances()

    logger.info("\nDetailed Opportunities:")
    for idx, opp in enumerate(opportunities, 1):
        logger.info(f"Opportunity {idx}:")
        logger.info(f"  Type: {opp['type']}")
        logger.info(f"  Pool: {opp['pool']}")
        logger.info(f"  Imbalance: {opp['imbalance']:.4f}")
        logger.info(f"  Token0: {get_token_symbol(opp['token0'])}")
        logger.info(f"  Token1: {get_token_symbol(opp['token1'])}")
        logger.info("")

    logger.info("Test complete.")

if __name__ == "__main__":
    main()