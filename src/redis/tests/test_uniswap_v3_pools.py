import unittest
import redis
from decimal import Decimal

# Redis configuration
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0

class TestUniswapV3Pools(unittest.TestCase):
    def setUp(self):
        self.r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

    def test_pool_data_structure(self):
        # Get the first valid pool
        for pool_key in self.r.scan_iter("uniswap_v3_pools:*"):
            pool_data = self.r.hgetall(pool_key)
            if pool_data:
                pool = {k.decode(): v.decode() for k, v in pool_data.items()}
                break
        else:
            self.fail("No valid pool data found")

        # Check if all required fields are present and non-empty
        required_fields = [
            'token0_address', 'token1_address', 'token0_symbol', 'token1_symbol',
            'sqrt_price', 'fee_tier', 'pool_address', 'liquidity',
            'token0_price', 'token1_price'
        ]
        for field in required_fields:
            self.assertIn(field, pool, f"Field '{field}' is missing")
            self.assertTrue(pool[field], f"Field '{field}' is empty")

        # Check data types and formats
        self.assertTrue(pool['token0_address'].startswith('0x'), "Token0 address should start with '0x'")
        self.assertTrue(pool['token1_address'].startswith('0x'), "Token1 address should start with '0x'")
        self.assertTrue(pool['pool_address'].startswith('0x'), "Pool address should start with '0x'")
        
        self.assertIsInstance(Decimal(pool['sqrt_price']), Decimal, "sqrt_price should be a valid Decimal")
        self.assertIsInstance(int(pool['fee_tier']), int, "fee_tier should be a valid integer")
        self.assertIsInstance(Decimal(pool['liquidity']), Decimal, "liquidity should be a valid Decimal")
        self.assertIsInstance(Decimal(pool['token0_price']), Decimal, "token0_price should be a valid Decimal")
        self.assertIsInstance(Decimal(pool['token1_price']), Decimal, "token1_price should be a valid Decimal")

    def test_pool_count(self):
        pool_count = sum(1 for _ in self.r.scan_iter("uniswap_v3_pools:*"))
        print(f"Found {pool_count} pools")
        self.assertGreaterEqual(pool_count, 200, "There should be at least 200 Uniswap V3 pools")
        self.assertLess(pool_count, 400, "There should be fewer than 400 Uniswap V3 pools")

if __name__ == '__main__':
    unittest.main()