import redis
import time

# Connect to Redis - use database 15 for testing (assuming your production data is in database 0)
r = redis.Redis(host='localhost', port=6379, db=15)

# Helper function to clear only the test database
def clear_test_db():
    r.flushdb()

# Setup function to run before all tests
def setup():
    clear_test_db()

# 1. Test exchange rate storage and retrieval
def test_exchange_rates():
    r.set('exchange:v2:WETH-DAI', '2000.50')
    r.set('exchange:v3:WETH-DAI', '2001.25')
    assert r.get('exchange:v2:WETH-DAI') == b'2000.50'
    assert r.get('exchange:v3:WETH-DAI') == b'2001.25'
    print("Exchange rate test passed")

# 2. Test liquidity information storage and retrieval
def test_liquidity():
    r.set('liquidity:v2:WETH-DAI', '1000000')
    r.set('liquidity:v3:WETH-DAI', '2000000')
    assert r.get('liquidity:v2:WETH-DAI') == b'1000000'
    assert r.get('liquidity:v3:WETH-DAI') == b'2000000'
    print("Liquidity test passed")

# 3. Test arbitrage opportunities sorted set
def test_arbitrage_opportunities():
    r.zadd('arb:opportunities', {'WETH-DAI:V2-V3': 0.5})
    r.zadd('arb:opportunities', {'DAI-USDC:V3-V2': 0.3})
    r.zadd('arb:opportunities', {'WETH-USDT:V2-V3': 0.7})
    opportunities = r.zrange('arb:opportunities', 0, -1, withscores=True, desc=True)
    assert opportunities == [(b'WETH-USDT:V2-V3', 0.7), (b'WETH-DAI:V2-V3', 0.5), (b'DAI-USDC:V3-V2', 0.3)]
    print("Arbitrage opportunities test passed")

# 4. Test gas price storage and retrieval
def test_gas_price():
    r.set('gas:price', '50')
    assert r.get('gas:price') == b'50'
    print("Gas price test passed")

# 5. Test historical exchange rate logging
def test_historical_rates():
    date = time.strftime("%Y-%m-%d")
    r.rpush(f'history:exchanges:WETH-DAI:{date}', f"{time.time()}:2000.75")
    r.rpush(f'history:exchanges:WETH-DAI:{date}', f"{time.time()}:2001.00")
    history = r.lrange(f'history:exchanges:WETH-DAI:{date}', 0, -1)
    assert len(history) == 2
    print("Historical rates test passed")

# 6. Test system configuration storage and retrieval
def test_configuration():
    r.set('config:min_profit_threshold', '0.2')
    assert r.get('config:min_profit_threshold') == b'0.2'
    print("Configuration test passed")

# 7. Test arbitrage transaction logging
def test_transaction_logging():
    date = time.strftime("%Y-%m-%d")
    r.rpush(f'logs:arbitrage:{date}', 'Executed WETH-DAI arbitrage, profit: 0.3%')
    logs = r.lrange(f'logs:arbitrage:{date}', 0, -1)
    assert logs == [b'Executed WETH-DAI arbitrage, profit: 0.3%']
    print("Transaction logging test passed")

# Run all tests
def run_all_tests():
    setup()
    test_exchange_rates()
    test_liquidity()
    test_arbitrage_opportunities()
    test_gas_price()
    test_historical_rates()
    test_configuration()
    test_transaction_logging()
    print("All tests passed successfully!")

# Execute all tests
if __name__ == "__main__":
    run_all_tests()

# After tests, clear the test database
    clear_test_db()
    print("Test database cleared")