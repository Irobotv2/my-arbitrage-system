import asyncio
import json
from web3 import Web3
from datetime import datetime, timedelta
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Connect to your local Ethereum node using HTTP
web3 = Web3(Web3.HTTPProvider('http://localhost:8545'))

logging.info(f"Connected to local Ethereum node: {web3.is_connected()}")

# Uniswap V3 Router and Factory addresses
uniswap_v3_router = web3.to_checksum_address('0xE592427A0AEce92De3Edee1F18E0157C05861564')
uniswap_v3_factory = web3.to_checksum_address('0x1F98431c8aD98523631AE4a59f267346ea31F984')

# ABIs remain the same
uniswap_v3_router_abi = json.loads('''
[
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                    {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "internalType": "struct ISwapRouter.ExactInputSingleParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "exactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "bytes", "name": "path", "type": "bytes"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"}
                ],
                "internalType": "struct ISwapRouter.ExactInputParams",
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "exactInput",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    }
]
''')

uniswap_v3_factory_abi = json.loads('''
[
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"}
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]
''')

uniswap_v3_pool_abi = json.loads('''
[
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    }
]
''')

uniswap_router_contract = web3.eth.contract(address=uniswap_v3_router, abi=uniswap_v3_router_abi)
uniswap_factory_contract = web3.eth.contract(address=uniswap_v3_factory, abi=uniswap_v3_factory_abi)

# Global variables for data collection
large_operations = []
total_transactions = 0
start_time = None
end_time = None

def get_pool_address(token0, token1, fee):
    pool_address = uniswap_factory_contract.functions.getPool(token0, token1, fee).call()
    logging.debug(f"Pool address for {token0}/{token1} with fee {fee}: {pool_address}")
    return pool_address

def get_pool_liquidity(pool_address):
    pool_contract = web3.eth.contract(address=pool_address, abi=uniswap_v3_pool_abi)
    liquidity = pool_contract.functions.liquidity().call()
    logging.debug(f"Liquidity for pool {pool_address}: {liquidity}")
    return liquidity

def extract_volume_and_pool(func_name, func_params):
    if func_name == 'exactInputSingle':
        token_in = func_params['params']['tokenIn']
        token_out = func_params['params']['tokenOut']
        fee = func_params['params']['fee']
        amount = func_params['params']['amountIn']
        pool_address = get_pool_address(token_in, token_out, fee)
        logging.debug(f"Extracted volume {amount} for pool {pool_address}")
        return amount, pool_address
    elif func_name == 'exactInput':
        path = func_params['params']['path']
        token_in = '0x' + path[:40]
        fee = int(path[40:46], 16)
        token_out = '0x' + path[46:86]
        amount = func_params['params']['amountIn']
        pool_address = get_pool_address(token_in, token_out, fee)
        logging.debug(f"Extracted volume {amount} for pool {pool_address} (multi-hop)")
        return amount, pool_address
    logging.warning(f"Unknown function: {func_name}")
    return 0, None

def handle_event(tx_hash):
    global total_transactions, large_operations

    try:
        tx = web3.eth.get_transaction(tx_hash)
        if tx['to'] and tx['to'].lower() == uniswap_v3_router.lower():
            decoded = uniswap_router_contract.decode_function_input(tx['input'])
            func_name = decoded[0]
            func_params = decoded[1]

            volume, pool_address = extract_volume_and_pool(func_name, func_params)
            
            if pool_address:
                total_liquidity = get_pool_liquidity(pool_address)
                if total_liquidity > 0:
                    liquidity_percentage = (int(volume) / int(total_liquidity)) * 100
                    
                    if liquidity_percentage >= 5:
                        large_operations.append({
                            "function": func_name,
                            "volume": Web3.from_wei(volume, 'ether'),
                            "tx_hash": tx_hash.hex(),
                            "pool_address": pool_address,
                            "liquidity_percentage": liquidity_percentage
                        })
                        logging.info(f"Large liquidity operation found: {func_name}")
                        logging.info(f"Volume: {Web3.from_wei(volume, 'ether')} ETH")
                        logging.info(f"Pool Address: {pool_address}")
                        logging.info(f"Liquidity Percentage: {liquidity_percentage:.2f}%")
                        logging.info(f"Transaction hash: {tx_hash.hex()}")
                    else:
                        logging.debug(f"Transaction below threshold: {liquidity_percentage:.2f}% < 5%")
                else:
                    logging.warning(f"Zero liquidity for pool {pool_address}")
            else:
                logging.debug(f"No pool address found for transaction {tx_hash.hex()}")
        
        total_transactions += 1
        if total_transactions % 100 == 0:
            logging.info(f"Processed {total_transactions} transactions")
    except Exception as e:
        logging.error(f"Error processing transaction {tx_hash.hex()}: {e}")

async def log_loop(duration):
    global start_time, end_time
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=duration)
    
    last_block = web3.eth.get_block_number()
    logging.info(f"Starting scan from block {last_block}")
    
    while datetime.now() < end_time:
        current_block = web3.eth.get_block_number()
        if current_block > last_block:
            logging.info(f"Scanning blocks {last_block + 1} to {current_block}")
            for block_number in range(last_block + 1, current_block + 1):
                block = web3.eth.get_block(block_number, full_transactions=True)
                logging.info(f"Processing block {block_number} with {len(block.transactions)} transactions")
                for tx in block.transactions:
                    handle_event(tx['hash'])
            last_block = current_block
        else:
            logging.debug("Waiting for new block...")
        await asyncio.sleep(1)  # Check for new blocks every second

def generate_report():
    global start_time, end_time, total_transactions, large_operations
    
    report = f"""
    Uniswap V3 Mempool Monitoring Report
    ------------------------------------
    Start Time: {start_time}
    End Time: {end_time}
    Duration: {end_time - start_time}
    
    Total Transactions Scanned: {total_transactions}
    Large Liquidity Operations Found: {len(large_operations)}
    
    Details of Large Liquidity Operations:
    """
    
    for op in large_operations:
        report += f"""
    Function: {op['function']}
    Volume: {op['volume']} ETH
    Pool Address: {op['pool_address']}
    Liquidity Percentage: {op['liquidity_percentage']:.2f}%
    Transaction Hash: {op['tx_hash']}
    
    """
    
    report += f"""
    Summary:
    - Average number of transactions per hour: {total_transactions / ((end_time - start_time).total_seconds() / 3600):.2f}
    - Percentage of large liquidity operations: {(len(large_operations) / total_transactions * 100) if total_transactions > 0 else 0:.2f}%
    
    This report can be used to identify patterns in large liquidity movements,
    which may indicate potential arbitrage opportunities or significant market activities.
    """
    
    return report

async def main():
    duration = 1  # Run for 1 hour
    await log_loop(duration)
    report = generate_report()
    print(report)
    
    with open('uniswap_mempool_report.txt', 'w') as f:
        f.write(report)

if __name__ == '__main__':
    asyncio.run(main())