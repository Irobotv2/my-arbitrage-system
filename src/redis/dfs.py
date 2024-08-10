import redis
from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import geth_poa_middleware
import logging
from datetime import datetime, timedelta
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    filename='arbitrage_report.log', filemode='w')
logger = logging.getLogger()
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)

# Initialize Redis client
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Initialize Web3 (Tenderly provider)
w3 = Web3(HTTPProvider('https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c'))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Contract setup
CONTRACT_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {
                        "internalType": "address",
                        "name": "tokenIn",
                        "type": "address"
                    },
                    {
                        "internalType": "address",
                        "name": "tokenOut",
                        "type": "address"
                    },
                    {
                        "internalType": "address",
                        "name": "pool",
                        "type": "address"
                    },
                    {
                        "internalType": "bool",
                        "name": "isV3",
                        "type": "bool"
                    },
                    {
                        "internalType": "uint24",
                        "name": "fee",
                        "type": "uint24"
                    },
                    {
                        "internalType": "uint256",
                        "name": "price",
                        "type": "uint256"
                    }
                ],
                "internalType": "struct FlashLoanArbitrage.SwapStep[]",
                "name": "path",
                "type": "tuple[]"
            },
            {
                "internalType": "uint256",
                "name": "flashLoanAmount",
                "type": "uint256"
            }
        ],
        "name": "simulateArbitrage",
        "outputs": [
            {
                "internalType": "uint256",
                "name": "estimatedProfit",
                "type": "uint256"
            },
            {
                "internalType": "uint256[]",
                "name": "simulationResults",
                "type": "uint256[]"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

CONTRACT_ADDRESS = Web3.to_checksum_address("0x48334a214155101522519c5f6c2d82e46cb405d4")
contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)

def get_pool_price(pool_address, is_v3):
    # This is a placeholder and should be replaced with real price fetching
    logger.info(f"Fetching price for pool {pool_address} (V3: {is_v3})")
    return Web3.to_wei(1, 'ether')  # 1:1 price as placeholder

def find_arbitrage_opportunities(token_pair, flash_loan_amount, min_profit_threshold=0.005):
    token1, token2 = token_pair
    logger.info(f"Searching for arbitrage opportunities for pair: {token1} - {token2}")
    
    v2_pools = redis_client.keys(f"uniswap_v2_pair:*")
    v3_pools = redis_client.keys(f"uniswap_v3_pool:*")
    logger.info(f"Found {len(v2_pools)} V2 pools and {len(v3_pools)} V3 pools")
    
    opportunities = []
    
    for v2_pool in v2_pools:
        v2_data = redis_client.hgetall(v2_pool)
        if (v2_data['token0'] == token1 and v2_data['token1'] == token2) or \
           (v2_data['token0'] == token2 and v2_data['token1'] == token1):
            v2_price = get_pool_price(v2_data['pair_address'], False)
            
            for v3_pool in v3_pools:
                v3_data = redis_client.hgetall(v3_pool)
                if (v3_data['token0'] == token1 and v3_data['token1'] == token2) or \
                   (v3_data['token0'] == token2 and v3_data['token1'] == token1):
                    v3_price = get_pool_price(v3_data['pool_address'], True)
                    
                    price_diff = abs(v2_price - v3_price) / min(v2_price, v3_price)
                    logger.info(f"Price difference between V2 and V3: {price_diff:.2%}")
                    
                    if price_diff > min_profit_threshold:
                        if v2_price < v3_price:
                            buy_pool = v2_data['pair_address']
                            sell_pool = v3_data['pool_address']
                            buy_is_v3 = False
                            sell_is_v3 = True
                        else:
                            buy_pool = v3_data['pool_address']
                            sell_pool = v2_data['pair_address']
                            buy_is_v3 = True
                            sell_is_v3 = False
                        
                        opportunities.append({
                            'token1': token1,
                            'token2': token2,
                            'buy_pool': buy_pool,
                            'sell_pool': sell_pool,
                            'buy_is_v3': buy_is_v3,
                            'sell_is_v3': sell_is_v3,
                            'price_difference': price_diff,
                            'estimated_profit': price_diff * flash_loan_amount
                        })
                        logger.info(f"Found potential arbitrage opportunity with {price_diff:.2%} price difference")
    
    logger.info(f"Found {len(opportunities)} potential arbitrage opportunities")
    return opportunities

def simulate_arbitrage(opportunity, flash_loan_amount):
    logger.info(f"Simulating arbitrage for opportunity: {opportunity['token1']} - {opportunity['token2']}")
    path = [
        {
            'tokenIn': opportunity['token1'],
            'tokenOut': opportunity['token2'],
            'pool': opportunity['buy_pool'],
            'isV3': opportunity['buy_is_v3'],
            'fee': 3000 if opportunity['buy_is_v3'] else 0,
            'price': Web3.to_wei(1, 'ether')
        },
        {
            'tokenIn': opportunity['token2'],
            'tokenOut': opportunity['token1'],
            'pool': opportunity['sell_pool'],
            'isV3': opportunity['sell_is_v3'],
            'fee': 3000 if opportunity['sell_is_v3'] else 0,
            'price': Web3.to_wei(1, 'ether')
        }
    ]
    
    try:
        estimated_profit, simulation_results = contract.functions.simulateArbitrage(path, flash_loan_amount).call()
        logger.info(f"Simulation complete. Estimated profit: {Web3.from_wei(estimated_profit, 'ether')} ETH")
        return estimated_profit, simulation_results
    except Exception as e:
        logger.error(f"Error in simulate_arbitrage: {e}")
        return 0, []

def main(run_time=60):
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=run_time)
    
    flash_loan_amount = Web3.to_wei(1, 'ether')  # 1 WETH
    logger.info(f"Starting arbitrage search. Will run until {end_time}")
    logger.info(f"Flash loan amount: {Web3.from_wei(flash_loan_amount, 'ether')} ETH")
    
    token_pairs = [
        ('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0x6B175474E89094C44Da98b954EedeAC495271d0F'),  # WETH-DAI
        ('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'),  # WETH-USDC
    ]
    
    best_opportunity = None
    highest_profit = 0
    iterations = 0
    
    while datetime.now() < end_time:
        iterations += 1
        logger.info(f"Starting iteration {iterations}")
        
        for token_pair in token_pairs:
            logger.info(f"Analyzing token pair: {token_pair[0]} - {token_pair[1]}")
            opportunities = find_arbitrage_opportunities(token_pair, flash_loan_amount)
            
            for opportunity in opportunities:
                estimated_profit, simulation_results = simulate_arbitrage(opportunity, flash_loan_amount)
                
                if estimated_profit > highest_profit:
                    highest_profit = estimated_profit
                    best_opportunity = opportunity
                    best_opportunity['simulated_profit'] = estimated_profit
                    best_opportunity['simulation_results'] = simulation_results
                    
                    logger.info(f"New best opportunity found:")
                    logger.info(f"Tokens: {opportunity['token1']} - {opportunity['token2']}")
                    logger.info(f"Buy pool: {opportunity['buy_pool']} (V3: {opportunity['buy_is_v3']})")
                    logger.info(f"Sell pool: {opportunity['sell_pool']} (V3: {opportunity['sell_is_v3']})")
                    logger.info(f"Price difference: {opportunity['price_difference']:.2%}")
                    logger.info(f"Estimated profit: {Web3.from_wei(estimated_profit, 'ether')} ETH")
        
        logger.info(f"Completed iteration {iterations}. Time elapsed: {datetime.now() - start_time}")
        time.sleep(1)  # Add a small delay to prevent overwhelming the system
    
    logger.info("Arbitrage search completed.")
    if best_opportunity:
        logger.info("Best arbitrage opportunity found:")
        logger.info(f"Tokens: {best_opportunity['token1']} - {best_opportunity['token2']}")
        logger.info(f"Buy pool: {best_opportunity['buy_pool']} (V3: {best_opportunity['buy_is_v3']})")
        logger.info(f"Sell pool: {best_opportunity['sell_pool']} (V3: {best_opportunity['sell_is_v3']})")
        logger.info(f"Price difference: {best_opportunity['price_difference']:.2%}")
        logger.info(f"Simulated profit: {Web3.from_wei(best_opportunity['simulated_profit'], 'ether')} ETH")
    else:
        logger.info("No profitable arbitrage opportunities found.")
    
    logger.info(f"Total iterations: {iterations}")
    logger.info(f"Total runtime: {datetime.now() - start_time}")

if __name__ == "__main__":
    main()