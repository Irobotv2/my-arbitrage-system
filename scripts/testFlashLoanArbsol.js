const hre = require("hardhat");
const { expect } = require("chai");
const { ethers } = require("hardhat");

// The ABI you provided
const flashLoanArbitrageABI = [
  {
    "inputs": [],
    "stateMutability": "nonpayable",
    "type": "constructor"
  },
  {
    "anonymous": false,
    "inputs": [
      {
        "indexed": false,
        "internalType": "uint256",
        "name": "profit",
        "type": "uint256"
      }
    ],
    "name": "ArbitrageExecuted",
    "type": "event"
  },
  {
    "anonymous": false,
    "inputs": [
      {
        "indexed": false,
        "internalType": "uint256",
        "name": "flashLoanAmount",
        "type": "uint256"
      },
      {
        "indexed": false,
        "internalType": "uint256",
        "name": "finalAmount",
        "type": "uint256"
      },
      {
        "indexed": false,
        "internalType": "uint256",
        "name": "profit",
        "type": "uint256"
      }
    ],
    "name": "SimulationComplete",
    "type": "event"
  },
  {
    "anonymous": false,
    "inputs": [
      {
        "indexed": false,
        "internalType": "string",
        "name": "message",
        "type": "string"
      }
    ],
    "name": "SimulationError",
    "type": "event"
  },
  {
    "inputs": [
      {
        "internalType": "uint256",
        "name": "flashLoanAmount",
        "type": "uint256"
      },
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
      }
    ],
    "name": "executeArbitrage",
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
  },
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
  },
  {
    "inputs": [
      {
        "internalType": "uint256",
        "name": "amountIn",
        "type": "uint256"
      },
      {
        "internalType": "uint256",
        "name": "price",
        "type": "uint256"
      }
    ],
    "name": "simulateV2Swap",
    "outputs": [
      {
        "internalType": "uint256",
        "name": "amountOut",
        "type": "uint256"
      }
    ],
    "stateMutability": "pure",
    "type": "function"
  },
  {
    "inputs": [
      {
        "internalType": "uint256",
        "name": "amountIn",
        "type": "uint256"
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
    "name": "simulateV3Swap",
    "outputs": [
      {
        "internalType": "uint256",
        "name": "amountOut",
        "type": "uint256"
      }
    ],
    "stateMutability": "pure",
    "type": "function"
  },
  {
    "inputs": [
      {
        "internalType": "int256",
        "name": "amount0Delta",
        "type": "int256"
      },
      {
        "internalType": "int256",
        "name": "amount1Delta",
        "type": "int256"
      },
      {
        "internalType": "bytes",
        "name": "data",
        "type": "bytes"
      }
    ],
    "name": "uniswapV3SwapCallback",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [
      {
        "internalType": "address",
        "name": "token",
        "type": "address"
      },
      {
        "internalType": "uint256",
        "name": "amount",
        "type": "uint256"
      }
    ],
    "name": "withdraw",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "stateMutability": "payable",
    "type": "receive"
  }
];

async function main() {
  let provider;
  try {
    // Set up JSON-RPC provider
    provider = new ethers.JsonRpcProvider("https://mainnet.gateway.tenderly.co/4XuvSWbosReD6ZCdS5naXU");
    
    const network = await provider.getNetwork();
    console.log("Connected to network:", network.name, "Chain ID:", network.chainId);

    const [deployer] = await ethers.getSigners();
    console.log("Using account:", deployer.address);

    const flashLoanArbitrageAddress = "0xb7ae06bb6d128124f76a5c812591ff6c27e5d15b";
    
    // Create the contract instance using the provided ABI
    const flashLoanArbitrage = new ethers.Contract(flashLoanArbitrageAddress, flashLoanArbitrageABI, provider);

    console.log("FlashLoanArbitrage instance created");
    console.log("FlashLoanArbitrage functions:", Object.keys(flashLoanArbitrage.interface.functions));
    console.log("FlashLoanArbitrage address:", flashLoanArbitrageAddress);

    // Test parameters
    const wethAddress = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";
    const daiAddress = "0x6B175474E89094C44Da98b954EedeAC495271d0F";
    const usdcAddress = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48";
    const borrowAmount = ethers.parseUnits("1", 18); // 1 WETH

    // Validate token addresses and contract functions
    async function validateSetup() {
      console.log("Validating setup...");
      
      // Validate tokens
      async function validateToken(address, name) {
        const token = new ethers.Contract(address, ["function symbol() view returns (string)"], provider);
        const symbol = await token.symbol();
        console.log(`Validated ${name}: ${symbol}`);
        return symbol;
      }

      await validateToken(wethAddress, "WETH");
      await validateToken(daiAddress, "DAI");
      await validateToken(usdcAddress, "USDC");

      // Check contract functions
      const requiredFunctions = ['simulateArbitrage', 'executeArbitrage', 'withdraw'];
      for (const func of requiredFunctions) {
        if (!flashLoanArbitrage.interface.functions[func]) {
          throw new Error(`Contract is missing required function: ${func}`);
        }
      }
      console.log("Contract has all required functions");
    }

    // Function to get real-time price from Uniswap V3 pool
    async function getUniswapV3Price(poolAddress, token0, token1) {
      const IUniswapV3Pool = new ethers.Contract(
        poolAddress,
        ['function slot0() external view returns (uint160 sqrtPriceX96, int24 tick, uint16 observationIndex, uint16 observationCardinality, uint16 observationCardinalityNext, uint8 feeProtocol, bool unlocked)'],
        provider
      );

      const [sqrtPriceX96] = await IUniswapV3Pool.slot0();
      const price = (sqrtPriceX96 * sqrtPriceX96 * (10n**18n) / (2n**192n)).toString();
      return ethers.BigNumber.from(price);
    }

    // Test executeArbitrage function
    async function testExecuteArbitrage() {
      console.log("Testing executeArbitrage function...");
      const flashLoanAmount = ethers.parseUnits("1", 18); // 1 WETH

      const path = [
        {
          tokenIn: wethAddress,
          tokenOut: daiAddress,
          pool: "0xC2e9F25Be6257c210d7Adf0D4Cd6E3E881ba25f8",
          isV3: true,
          fee: 3000,
          price: 0
        },
        {
          tokenIn: daiAddress,
          tokenOut: usdcAddress,
          pool: "0x5777d92f208679DB4b9778590Fa3CAB3aC9e2168",
          isV3: true,
          fee: 100,
          price: 0
        },
        {
          tokenIn: usdcAddress,
          tokenOut: wethAddress,
          pool: "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",
          isV3: true,
          fee: 500,
          price: 0
        }
      ];

      // Get real-time prices
      for (let step of path) {
        step.price = await getUniswapV3Price(step.pool, step.tokenIn, step.tokenOut);
        console.log(`Real-time price for ${step.tokenIn} to ${step.tokenOut}: ${ethers.utils.formatUnits(step.price, 18)}`);
      }

      try {
        console.log("Simulating arbitrage...");
        const [estimatedProfit, simulationResults] = await flashLoanArbitrage.simulateArbitrage(path, flashLoanAmount);
        console.log("Estimated profit:", ethers.utils.formatUnits(estimatedProfit, 18), "ETH");

        const minProfitThreshold = ethers.parseUnits("0.01", 18);

        if (estimatedProfit.gt(minProfitThreshold)) {
          console.log("Estimated profit above threshold. Executing arbitrage...");
          const tx = await flashLoanArbitrage.executeArbitrage(flashLoanAmount, path, {
            gasLimit: 5000000
          });
          console.log("Arbitrage transaction sent:", tx.hash);
          
          const receipt = await tx.wait();
          console.log("Arbitrage transaction confirmed in block:", receipt.blockNumber);
          
          // Log events
          for (const log of receipt.logs) {
            try {
              const parsedLog = flashLoanArbitrage.interface.parseLog(log);
              console.log("Event:", parsedLog.name);
              console.log("Event args:", parsedLog.args);
            } catch (error) {
              console.log("Could not decode log:", log);
            }
          }
          
          console.log("Arbitrage executed successfully");
          return true;
        } else {
          console.log("Estimated profit too low, skipping arbitrage");
          return false;
        }
      } catch (error) {
        console.error("Error executing arbitrage:", error);
        if (error.transaction) {
          const tx = error.transaction;
          console.log("Failed transaction details:");
          console.log("From:", tx.from);
          console.log("To:", tx.to);
          console.log("Value:", ethers.utils.formatEther(tx.value), "ETH");
          console.log("Gas price:", ethers.utils.formatUnits(tx.gasPrice, "gwei"), "Gwei");
          console.log("Gas limit:", tx.gasLimit.toString());
        }
        if (error.receipt) {
          const receipt = error.receipt;
          console.log("Transaction receipt:");
          console.log("Status:", receipt.status);
          console.log("Gas used:", receipt.gasUsed.toString());
          console.log("Block number:", receipt.blockNumber);
          // Try to decode logs
          for (const log of receipt.logs) {
            try {
              const parsedLog = flashLoanArbitrage.interface.parseLog(log);
              console.log("Event:", parsedLog.name);
              console.log("Event args:", parsedLog.args);
            } catch (decodeError) {
              console.log("Could not decode log:", log);
            }
          }
        }
        return false;
      }
    }

    // Test withdraw function
    async function testWithdraw() {
      console.log("Testing withdraw function...");
      const withdrawAmount = ethers.parseUnits("0.1", 18); // 0.1 ETH
      try {
        // Check balance before withdrawal
        const balanceBefore = await provider.getBalance(flashLoanArbitrageAddress);
        console.log("Contract balance before withdrawal:", ethers.utils.formatEther(balanceBefore), "ETH");

        if (balanceBefore.lt(withdrawAmount)) {
          console.log("Insufficient balance for withdrawal");
          return false;
        }

        const tx = await flashLoanArbitrage.withdraw(ethers.ZeroAddress, withdrawAmount);
        console.log("Withdraw transaction sent:", tx.hash);
        const receipt = await tx.wait();
        console.log("Withdraw transaction confirmed in block:", receipt.blockNumber);

        // Check balance after withdrawal
        const balanceAfter = await provider.getBalance(flashLoanArbitrageAddress);
        console.log("Contract balance after withdrawal:", ethers.utils.formatEther(balanceAfter), "ETH");

        console.log("Withdraw executed successfully");
        return true;
      } catch (error) {
        console.error("Error executing withdraw:", error);
        if (error.reason) {
          console.log("Revert reason:", error.reason);
        }
        // Try to get more details about the error
        if (error.transaction) {
          const tx = error.transaction;
          console.log("Failed transaction details:");
          console.log("From:", tx.from);
          console.log("To:", tx.to);
          console.log("Value:", ethers.utils.formatEther(tx.value), "ETH");
          console.log("Gas price:", ethers.utils.formatUnits(tx.gasPrice, "gwei"), "Gwei");
          console.log("Gas limit:", tx.gasLimit.toString());
        }
        return false;
      }
    }

    // Run tests
    await validateSetup();
    const arbitrageResult = await testExecuteArbitrage();
    const withdrawResult = await testWithdraw();

    if (arbitrageResult && withdrawResult) {
      console.log("All tests passed successfully!");
    } else {
      console.log("Some tests failed. Please check the logs for details.");
    }

  } catch (error) {
    console.error("An error occurred:", error.message);
    if (error.stack) {
      console.error("Stack trace:", error.stack);
    }
    process.exit(1);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });