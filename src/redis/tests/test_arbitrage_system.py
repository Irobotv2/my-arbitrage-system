import unittest
from decimal import Decimal
from web3 import Web3
import time
import redis
#run with python -m unittest test_arbitrage_system.py

class ArbitrageSystemTests(unittest.TestCase):

    def setUp(self):
        # Initialize your Redis connection and other necessary setup
        self.r = redis.Redis(host='localhost', port=6379, db=0)
        self.w3 = Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/0640f56f05a942d7a25cfeff50de344d'))

    def test_data_accuracy(self):
        # Test a sample V2 pair
        v2_pair_key = "uniswap_v2_pairs:0x4a7d4BE868e0b811ea804fAF0D3A325c3A29a9ad"
        v2_pair_data = self.r.hgetall(v2_pair_key)
        self.assertIsNotNone(v2_pair_data, "V2 pair data not found in Redis")
        
        # Fetch on-chain data and compare
        pair_contract = self.w3.eth.contract(address=v2_pair_data[b'pool_address'].decode(), abi=UNISWAP_V2_PAIR_ABI)
        on_chain_reserves = pair_contract.functions.getReserves().call()
        self.assertEqual(Decimal(v2_pair_data[b'reserve0'].decode()), Decimal(on_chain_reserves[0]), "V2 reserve0 mismatch")
        self.assertEqual(Decimal(v2_pair_data[b'reserve1'].decode()), Decimal(on_chain_reserves[1]), "V2 reserve1 mismatch")

    def test_address_correctness(self):
        # Test a sample V3 pool
        v3_pool_key = "uniswap_v3_pools:0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8"
        v3_pool_data = self.r.hgetall(v3_pool_key)
        self.assertIsNotNone(v3_pool_data, "V3 pool data not found in Redis")
        
        # Validate addresses
        self.assertTrue(self.w3.is_address(v3_pool_data[b'token0_address'].decode()), "Invalid token0 address")
        self.assertTrue(self.w3.is_address(v3_pool_data[b'token1_address'].decode()), "Invalid token1 address")
        self.assertTrue(self.w3.is_address(v3_pool_data[b'pool_address'].decode()), "Invalid pool address")

    def test_data_freshness(self):
        v2_pair_key = "uniswap_v2_pairs:0x4a7d4BE868e0b811ea804fAF0D3A325c3A29a9ad"
        v2_pair_data = self.r.hgetall(v2_pair_key)
        last_updated = int(v2_pair_data.get(b'last_updated', 0))
        current_time = int(time.time())
        self.assertLess(current_time - last_updated, 300, "Data is more than 5 minutes old")

    def test_data_completeness(self):
        v3_pool_key = "uniswap_v3_pools:0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8"
        v3_pool_data = self.r.hgetall(v3_pool_key)
        required_fields = [b'token0_address', b'token1_address', b'pool_address', b'sqrt_price', b'fee_tier']
        for field in required_fields:
            self.assertIn(field, v3_pool_data, f"Missing required field: {field.decode()}")

    def test_price_calculation(self):
        v3_pool_key = "uniswap_v3_pools:0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8"
        v3_pool_data = self.r.hgetall(v3_pool_key)
        sqrt_price = Decimal(v3_pool_data[b'sqrt_price'].decode())
        calculated_price = (sqrt_price / Decimal(2**96)) ** 2
        self.assertGreater(calculated_price, 0, "Invalid calculated price")

    def test_fee_calculation(self):
        v2_pair_key = "uniswap_v2_pairs:0x4a7d4BE868e0b811ea804fAF0D3A325c3A29a9ad"
        v2_pair_data = self.r.hgetall(v2_pair_key)
        fee = Decimal(v2_pair_data[b'fee'].decode())
        self.assertEqual(fee, Decimal('0.003'), "Incorrect fee for V2 pair")

    def test_redis_availability(self):
        try:
            self.r.ping()
        except redis.ConnectionError:
            self.fail("Redis connection failed")

    def test_data_structure_consistency(self):
        v2_keys = list(self.r.scan_iter("uniswap_v2_pairs:*"))
        v3_keys = list(self.r.scan_iter("uniswap_v3_pools:*"))
        self.assertTrue(all(key.startswith(b'uniswap_v2_pairs:') for key in v2_keys), "Inconsistent V2 pair key format")
        self.assertTrue(all(key.startswith(b'uniswap_v3_pools:') for key in v3_keys), "Inconsistent V3 pool key format")

    def test_decimal_precision(self):
        v3_pool_key = "uniswap_v3_pools:0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8"
        v3_pool_data = self.r.hgetall(v3_pool_key)
        sqrt_price = Decimal(v3_pool_data[b'sqrt_price'].decode())
        price = (sqrt_price / Decimal(2**96)) ** 2
        self.assertIsInstance(price, Decimal, "Price should be a Decimal")
        self.assertGreater(price.as_tuple().exponent, -18, "Price has more than 18 decimal places")

if __name__ == '__main__':
    unittest.main()