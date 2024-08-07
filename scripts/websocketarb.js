const ethers = require('ethers');
const { MultiCall } = require('@indexed-finance/multicall');
const FlashLoanArbitrageABI = require('./FlashLoanArbitrageABI.json');

// Tenderly WebSocket provider for listening to events
const tenderlyWsProvider = new ethers.WebSocketProvider('wss://mainnet.gateway.tenderly.co/4XuvSWbosReD6ZCdS5naXU');

// Virtual testnet provider for sending transactions
const virtualTestnetProvider = new ethers.JsonRpcProvider('https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c');

// Create a signer using the virtual testnet provider
const signer = new ethers.Wallet('6d0ad7f50dccb88715e3592f39ea5be4c715531223b2daeb2de621dc8f6c230f', virtualTestnetProvider);

// Create contract instance
const flashLoanArbitrageAddress = "0xb7ae06bb6d128124f76a5c812591ff6c27e5d15b";
const flashLoanArbitrage = new ethers.Contract(flashLoanArbitrageAddress, FlashLoanArbitrageABI, signer);

// Cache static data
const TOKEN_ADDRESSES = {
  DAI: "0x6B175474E89094C44Da98b954EedeAC495271d0F",
  FRAX: "0x853d955aCEf822Db058eb8505911ED77F175b99e",
};

const POOL_ADDRESSES = {
  V3_DAI_FRAX: "0x97e7d56a0408570ba1a7852de36350f7713906ec",
  V2_DAI_FRAX: "0x862d12ebd188aab3f7646efa9c520cd436d6ef6e",
};

// Multicall setup
const multicall = new MultiCall(virtualTestnetProvider);

// Memoization for expensive computations
const memoize = (fn) => {
  const cache = new Map();
  return (...args) => {
    const key = JSON.stringify(args);
    if (cache.has(key)) return cache.get(key);
    const result = fn.apply(this, args);
    cache.set(key, result);
    return result;
  };
};

const getLatestPrices = memoize(async () => {
  const [v3Price, v2Price] = await multicall.all([
    [POOL_ADDRESSES.V3_DAI_FRAX, 'slot0()'],
    [POOL_ADDRESSES.V2_DAI_FRAX, 'getReserves()'],
  ]);

  return {
    v3Price: v3Price[0] / 2n**96n,
    v2Price: v2Price[0] / v2Price[1],
  };
});

const simulateAndExecute = async () => {
  try {
    const { v3Price, v2Price } = await getLatestPrices();

    const path = [
      {
        tokenIn: TOKEN_ADDRESSES.DAI,
        tokenOut: TOKEN_ADDRESSES.FRAX,
        pool: POOL_ADDRESSES.V3_DAI_FRAX,
        isV3: true,
        fee: 500,
        price: ethers.parseUnits(v3Price.toString(), 18)
      },
      {
        tokenIn: TOKEN_ADDRESSES.FRAX,
        tokenOut: TOKEN_ADDRESSES.DAI,
        pool: POOL_ADDRESSES.V2_DAI_FRAX,
        isV3: false,
        fee: 0,
        price: ethers.parseUnits(v2Price.toString(), 18)
      }
    ];

    const flashLoanAmount = ethers.parseUnits("10000", 18);

    // Simulate arbitrage
    const [estimatedProfit, simulationResults] = await flashLoanArbitrage.simulateArbitrage(path, flashLoanAmount);

    console.log("Estimated profit:", ethers.formatUnits(estimatedProfit, 18));

    if (estimatedProfit > 0n) {
      // Execute arbitrage with optimal gas price
      const feeData = await virtualTestnetProvider.getFeeData();
      const tx = await flashLoanArbitrage.executeArbitrage(flashLoanAmount, path, {
        maxFeePerGas: feeData.maxFeePerGas * 120n / 100n, // 20% higher than current max fee
        maxPriorityFeePerGas: feeData.maxPriorityFeePerGas * 120n / 100n,
        gasLimit: 500000n,
      });

      console.log("Arbitrage transaction sent:", tx.hash);

      // Wait for transaction confirmation
      const receipt = await tx.wait(1);
      console.log("Arbitrage transaction confirmed in block:", receipt.blockNumber);
    } else {
      console.log("Estimated profit is not positive. Skipping execution.");
    }
  } catch (error) {
    console.error("Error:", error);
  }
};

// Use Tenderly WebSocket provider to listen for new blocks
tenderlyWsProvider.on('block', async (blockNumber) => {
  console.log(`New block: ${blockNumber}`);
  await simulateAndExecute();
});

// Handle disconnects for Tenderly WebSocket
tenderlyWsProvider.on('error', (error) => {
  console.error('WebSocket Error:', error);
  process.exit(1);
});

tenderlyWsProvider.on('close', (code) => {
  console.log(`WebSocket connection closed with code ${code}. Attempting to reconnect...`);
  tenderlyWsProvider.connect();
});

// Fund the account
const fundAccount = async () => {
  try {
    await virtualTestnetProvider.send("tenderly_setBalance", [
      signer.address,
      "0xDE0B6B3A7640000", // 1 ETH in wei
    ]);
    console.log("Account funded successfully");
  } catch (error) {
    console.error("Error funding account:", error);
  }
};

// Call fundAccount before starting the main loop
fundAccount().then(() => {
  console.log("Starting arbitrage monitoring...");
});