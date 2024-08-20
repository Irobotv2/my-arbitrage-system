import redis
from web3 import Web3
import time
import logging
provider_url = 'http://localhost:8545'  # HTTP URL
w3 = Web3(Web3.HTTPProvider(provider_url))


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
flashloan_contract = w3.eth.contract(address=FLASHLOAN_BUNDLE_EXECUTOR_ADDRESS, abi=FLASHLOAN_BUNDLE_EXECUTOR_ABI)
v2_pool_contract = w3.eth.contract(address=UNISWAP_V2_WBTC_WETH_POOL, abi=V2_POOL_ABI)
v3_pool_contract = w3.eth.contract(address=UNISWAP_V3_WBTC_WETH_POOL, abi=V3_POOL_ABI)

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Set up logging
logging.basicConfig(level=logging.INFO)

def get_token_decimals(token_address):
    token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
    return token_contract.functions.decimals().call()

def get_wbtc_weth_price_v2():
    # Fetch reserves from the Uniswap V2 pool
    reserves = v2_pool_contract.functions.getReserves().call()
    wbtc_reserve = reserves[0]  # Reserve of WBTC (Token 0)
    weth_reserve = reserves[1]  # Reserve of WETH (Token 1)
    
    # Get the decimals of WBTC and WETH
    wbtc_decimals = get_token_decimals('0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599')  # WBTC
    weth_decimals = get_token_decimals('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2')  # WETH

    # Normalize reserves to account for decimals
    normalized_wbtc_reserve = wbtc_reserve / (10 ** wbtc_decimals)
    normalized_weth_reserve = weth_reserve / (10 ** weth_decimals)

    # Calculate the price of WBTC in terms of WETH
    price_v2 = normalized_weth_reserve / normalized_wbtc_reserve
    return price_v2


def sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals):
    price = (sqrt_price_x96 ** 2) / (2 ** 192)
    decimal_adjustment = 10 ** (token1_decimals - token0_decimals)
    return price * decimal_adjustment

def get_wbtc_weth_price_v3():
    slot0_data = v3_pool_contract.functions.slot0().call()
    sqrt_price_x96 = slot0_data[0]
    token0_decimals = get_token_decimals('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2')  # WETH
    token1_decimals = get_token_decimals('0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599')  # WBTC
    price_v3 = sqrt_price_x96_to_price(sqrt_price_x96, token0_decimals, token1_decimals)
    return price_v3

def monitor_arbitrage_opportunities():
    while True:
        price_v2 = get_wbtc_weth_price_v2()
        price_v3 = get_wbtc_weth_price_v3()

        logging.info(f"Uniswap V2 Price: {price_v2} WETH per WBTC")
        logging.info(f"Uniswap V3 Price: {price_v3} WETH per WBTC")
        
        if price_v3 > price_v2 * 1.01:
            logging.info("Arbitrage opportunity detected! Uniswap V3 > Uniswap V2")
            execute_arbitrage(is_v2_to_v3=True, tokens=[], amounts=[])
        elif price_v2 > price_v3 * 1.01:
            logging.info("Arbitrage opportunity detected! Uniswap V2 > Uniswap V3")
            execute_arbitrage(is_v2_to_v3=False, tokens=[], amounts=[])

        time.sleep(10)  # Check every 10 seconds

def execute_arbitrage(is_v2_to_v3, tokens, amounts):
    targets = []  # Addresses of the contracts to interact with
    payloads = []  # The payloads (data) for the transactions

    if is_v2_to_v3:
        # Add logic to create payloads for swapping on V2 and V3, and repaying the flash loan
        pass
    else:
        # Add logic to create payloads for swapping on V3 and V2, and repaying the flash loan
        pass

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
