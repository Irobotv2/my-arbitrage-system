import redis
from web3 import Web3
import time
import logging

# Setup Web3 connection
provider_url = 'http://localhost:8545'  # HTTP URL
w3 = Web3(Web3.HTTPProvider(provider_url))

# Define your wallet address and private key
wallet_address = "0x19F5034FAB7e2CcA2Ad46EC28acF20cbd098D3fF"
private_key = "6d0ad7f50dccb88715e3592f39ea5be4c715531223b2daeb2de621dc8f6c230f"  # Replace with your actual private key

# Define contract addresses
UNISWAP_V2_WBTC_WETH_POOL = "0xBb2b8038a1640196FbE3e38816F3e67Cba72D940"
UNISWAP_V3_WBTC_WETH_POOL = "0xCBCdF9626bC03E24f779434178A73a0B4bad62eD"
UNISWAP_V2_ROUTER_ADDRESS = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V3_ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS = "0x26B7B5AB244114ab88578D5C4cD5b096097bf543"

v3_pools = {
    '0.01%': '0xe6ff8b9A37B0fab776134636D9981Aa778c4e718',
    '0.05%': '0x4585FE77225b41b697C938B018E2Ac67Ac5a20c0',
    '0.30%': '0xCBCdF9626bC03E24f779434178A73a0B4bad62eD',  # Existing 0.30% pool
    '1.00%': '0x6Ab3bba2F41e7eAA262fa5A1A9b3932fA161526F'
}

V2_ROUTER_ABI = [
    {
        "name": "swapExactTokensForTokens",
        "type": "function",
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"}
        ],
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
V3_ROUTER_ABI = [
    {
        "name": "exactInputSingle",
        "type": "function",
        "inputs": [
            {
                "name": "params",
                "type": "tuple",
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "recipient", "type": "address"},
                    {"name": "deadline", "type": "uint256"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "amountOutMinimum", "type": "uint256"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"}
                ]
            }
        ],
        "outputs": [{"name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    }
]

# Uniswap V2 WBTC/WETH Pool address and ABI
UNISWAP_V2_WBTC_WETH_POOL = "0xBb2b8038a1640196FbE3e38816F3e67Cba72D940"
V2_POOL_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# Uniswap V3 WBTC/WETH Pool address and ABI
UNISWAP_V3_WBTC_WETH_POOL = "0xCBCdF9626bC03E24f779434178A73a0B4bad62eD"
V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# Add ERC20 ABI for decimals function
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]

# FlashLoanBundleExecutor contract address and ABI
FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS = "0x26B7B5AB244114ab88578D5C4cD5b096097bf543"
FLASHLOAN_BUNDLE_EXECUTOR_ABI = [
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "_executor",
                "type": "address"
            }
        ],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "inputs": [],
        "name": "executor",
        "outputs": [
            {
                "internalType": "address",
                "name": "",
                "type": "address"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "contract IERC20[]",
                "name": "tokens",
                "type": "address[]"
            },
            {
                "internalType": "uint256[]",
                "name": "amounts",
                "type": "uint256[]"
            },
            {
                "internalType": "address[]",
                "name": "targets",
                "type": "address[]"
            },
            {
                "internalType": "bytes[]",
                "name": "payloads",
                "type": "bytes[]"
            }
        ],
        "name": "initiateFlashLoanAndBundle",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [
            {
                "internalType": "address",
                "name": "",
                "type": "address"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "contract IERC20[]",
                "name": "tokens",
                "type": "address[]"
            },
            {
                "internalType": "uint256[]",
                "name": "amounts",
                "type": "uint256[]"
            },
            {
                "internalType": "uint256[]",
                "name": "feeAmounts",
                "type": "uint256[]"
            },
            {
                "internalType": "bytes",
                "name": "userData",
                "type": "bytes"
            }
        ],
        "name": "receiveFlashLoan",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
# Create contract instances
v2_pool_contract = w3.eth.contract(address=UNISWAP_V2_WBTC_WETH_POOL, abi=V2_POOL_ABI)
v3_pool_contract = w3.eth.contract(address=UNISWAP_V3_WBTC_WETH_POOL, abi=V3_POOL_ABI)
v2_router_contract = w3.eth.contract(address=UNISWAP_V2_ROUTER_ADDRESS, abi=V2_ROUTER_ABI)
v3_router_contract = w3.eth.contract(address=UNISWAP_V3_ROUTER_ADDRESS, abi=V3_ROUTER_ABI)
flashloan_contract = w3.eth.contract(address=FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, abi=FLASHLOAN_BUNDLE_EXECUTOR_ABI)

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Set up logging
logging.basicConfig(level=logging.INFO)

def get_token_decimals(token_address):
    token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
    return token_contract.functions.decimals().call()

def get_wbtc_weth_price_v2():
    reserves = v2_pool_contract.functions.getReserves().call()
    wbtc_reserve = reserves[0]
    weth_reserve = reserves[1]
    
    wbtc_decimals = get_token_decimals('0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599')
    weth_decimals = get_token_decimals('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2')

    normalized_wbtc_reserve = wbtc_reserve / (10 ** wbtc_decimals)
    normalized_weth_reserve = weth_reserve / (10 ** weth_decimals)

    price_v2 = normalized_weth_reserve / normalized_wbtc_reserve
    return price_v2

def sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals):
    price = (sqrt_price_x96 ** 2) / (2 ** 192)
    decimal_adjustment = 10 ** (token1_decimals - token0_decimals)
    return price * decimal_adjustment

def get_wbtc_weth_price_v3(pool_address):
    v3_pool_contract = w3.eth.contract(address=pool_address, abi=V3_POOL_ABI)
    slot0_data = v3_pool_contract.functions.slot0().call()
    sqrt_price_x96 = slot0_data[0]
    token0_decimals = get_token_decimals('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2')
    token1_decimals = get_token_decimals('0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599')
    price_v3 = sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals)
    return price_v3

def monitor_arbitrage_opportunities():
    while True:
        price_v2 = get_wbtc_weth_price_v2()

        for fee_tier, pool_address in v3_pools.items():
            price_v3 = get_wbtc_weth_price_v3(pool_address)

            logging.info(f"Uniswap V2 Price: {price_v2} WETH per WBTC")
            logging.info(f"Uniswap V3 ({fee_tier}) Price: {price_v3} WETH per WBTC")

            if price_v3 > price_v2 * 1.01:
                logging.info(f"Arbitrage opportunity detected! Uniswap V3 ({fee_tier}) > Uniswap V2")
                execute_arbitrage(pool_address, is_v2_to_v3=True, amount=w3.toWei(1, 'ether'))
            elif price_v2 > price_v3 * 1.01:
                logging.info(f"Arbitrage opportunity detected! Uniswap V2 > Uniswap V3 ({fee_tier})")
                execute_arbitrage(pool_address, is_v2_to_v3=False, amount=w3.toWei(1, 'ether'))

        time.sleep(10)


def execute_arbitrage(v3_pool_address, is_v2_to_v3, amount):
    if is_v2_to_v3:
        targets = [UNISWAP_V2_ROUTER_ADDRESS, UNISWAP_V3_ROUTER_ADDRESS]

        v2_swap_payload = v2_router_contract.functions.swapExactTokensForTokens(
            amount, 
            0, 
            ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"], 
            wallet_address, 
            int(time.time()) + 60 * 10
        ).buildTransaction({'from': wallet_address})['data']
        
        v3_swap_payload = v3_router_contract.functions.exactInputSingle({
            'tokenIn': "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  
            'tokenOut': "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  
            'fee': 3000,  # This should match the pool fee
            'recipient': wallet_address,
            'deadline': int(time.time()) + 60 * 10,
            'amountIn': amount,
            'amountOutMinimum': 0,
            'sqrtPriceLimitX96': 0,
        }).buildTransaction({'from': wallet_address})['data']

        payloads = [v2_swap_payload, v3_swap_payload]

    else:
        targets = [UNISWAP_V3_ROUTER_ADDRESS, UNISWAP_V2_ROUTER_ADDRESS]
        
        v3_swap_payload = v3_router_contract.functions.exactInputSingle({
            'tokenIn': "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  
            'tokenOut': "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  
            'fee': 3000,  
            'recipient': wallet_address,
            'deadline': int(time.time()) + 60 * 10,
            'amountIn': amount,
            'amountOutMinimum': 0,
            'sqrtPriceLimitX96': 0,
        }).buildTransaction({'from': wallet_address})['data']
        
        v2_swap_payload = v2_router_contract.functions.swapExactTokensForTokens(
            amount, 
            0, 
            ["0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"],  
            wallet_address, 
            int(time.time()) + 60 * 10
        ).buildTransaction({'from': wallet_address})['data']

        payloads = [v3_swap_payload, v2_swap_payload]

    tokens = ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"]
    amounts = [amount, 0]  

    tx = flashloan_contract.functions.initiateFlashLoanAndBundle(tokens, amounts, targets, payloads).buildTransaction({
        'from': wallet_address,
        'nonce': w3.eth.getTransactionCount(wallet_address),
        'gas': 3000000,
        'gasPrice': w3.toWei('20', 'gwei'),
    })

    signed_tx = w3.eth.account.signTransaction(tx, private_key=private_key)
    tx_hash = w3.eth.sendRawTransaction(signed_tx.rawTransaction)
    logging.info(f"Arbitrage transaction sent: {tx_hash.hex()}")

    receipt = w3.eth.waitForTransactionReceipt(tx_hash)
    logging.info(f"Arbitrage transaction mined: {receipt.transactionHash.hex()}")


if __name__ == "__main__":
    monitor_arbitrage_opportunities()
