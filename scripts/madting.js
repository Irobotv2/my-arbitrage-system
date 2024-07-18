const hre = require("hardhat");
const { Interface } = require('@ethersproject/abi');
const { ethers } = hre;
const mysql = require('mysql2/promise');

// Database configuration
const DB_CONFIG = {
  host: 'localhost',
  user: 'arbitrage_user',
  password: 'Newpassword1!',
  database: 'arbitrage_system'
};

// Tenderly RPC URL
const RPC_URL = "https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c";

// New contract address
const ARBITRAGE_CONTRACT_ADDRESS = "0x50215e914690e0Ad60fb0096e53F8a69d2d53af3";

async function getLatestArbitrageOpportunity() {
  const connection = await mysql.createConnection(DB_CONFIG);

  const [rows] = await connection.execute(`
    SELECT * FROM arbitrage_opportunities 
    ORDER BY timestamp DESC 
    LIMIT 1
  `);

  await connection.end();

  if (rows[0]) {
    console.log("Retrieved latest arbitrage opportunity:");
    console.log(`  Pair: ${rows[0].pair}`);
    console.log(`  V2 Price: ${rows[0].v2_price}`);
    console.log(`  V3 Price: ${rows[0].v3_price}`);
    console.log(`  Basis Points: ${rows[0].basis_points}`);
    console.log(`  Direction: ${rows[0].direction}`);
  } else {
    console.log("No arbitrage opportunity found.");
  }

  return rows[0];
}

async function isGasPriceAcceptable() {
  const provider = new ethers.JsonRpcProvider(RPC_URL);
  const feeData = await provider.getFeeData();
  const gasPrice = feeData.gasPrice;
  const maxGasPrice = ethers.parseUnits("50", "gwei");
  console.log(`Current gas price: ${ethers.formatUnits(gasPrice, "gwei")} gwei`);
  console.log(`Max acceptable gas price: ${ethers.formatUnits(maxGasPrice, "gwei")} gwei`);
  return gasPrice <= maxGasPrice;
}

function calculatePotentialProfit(opportunity, flashLoanAmount) {
  const v2Price = parseFloat(opportunity.v2_price);
  const v3Price = parseFloat(opportunity.v3_price);
  const direction = opportunity.direction;
  
  let potentialProfit;
  if (direction === 'v2_to_v3') {
    potentialProfit = (v3Price - v2Price) * flashLoanAmount;
  } else {
    potentialProfit = (v2Price - v3Price) * flashLoanAmount;
  }
  
  console.log(`Potential profit: ${potentialProfit} ETH`);
  return Number(potentialProfit.toFixed(18));
}

async function executeArbitrage(opportunity, arbitrageContract) {
    console.log("Executing arbitrage for opportunity:", opportunity);
  
    const flashLoanAmount = ethers.parseEther("1");
    console.log("Flash loan amount:", ethers.formatEther(flashLoanAmount), "ETH");
  
    try {
      const potentialProfit = calculatePotentialProfit(opportunity, parseFloat(ethers.formatEther(flashLoanAmount)));
      console.log("Calculated potential profit:", potentialProfit, "ETH");
  
      const MINIMUM_PROFIT_THRESHOLD_ETH = 0.01; // 0.01 ETH
      
      if (potentialProfit > MINIMUM_PROFIT_THRESHOLD_ETH) {
        console.log("Potential profit exceeds threshold, executing arbitrage...");
  
        // Use the ERC20 ABI instead of trying to get the contract
        const erc20Abi = [
          "function approve(address spender, uint256 amount) external returns (bool)"
        ];
        const erc20Interface = new Interface(erc20Abi);
        const tokenIn = new ethers.Contract(opportunity.v2_pair, erc20Interface, ethers.provider.getSigner());
  
        // Approve the contract to spend our tokens
        await tokenIn.approve(arbitrageContract.address, flashLoanAmount);
  
        const params = {
          tokenIn: opportunity.v2_pair,
          tokenOut: opportunity.v3_pool,
          amount: flashLoanAmount,
          minOutV2: flashLoanAmount * 99n / 100n,
          minOutV3: flashLoanAmount * 99n / 100n,
          v3Fee: 3000,
          useV3: opportunity.direction.startsWith('Buy on V3')
        };
  
        console.log("Initiating arbitrage with params:", params);
  
        try {
          const tx = await arbitrageContract.initiateArbitrage(params, { gasLimit: 10000000 });
          console.log("Transaction sent:", tx.hash);
          console.log("Waiting for transaction confirmation...");
          const receipt = await tx.wait();
          console.log("Transaction confirmed in block:", receipt.blockNumber);
          console.log("Gas used:", receipt.gasUsed.toString());
  
          let totalGasCost = receipt.gasUsed * receipt.effectiveGasPrice;
          console.log("Total gas cost:", ethers.formatEther(totalGasCost), "ETH");
  
          for (const log of receipt.logs) {
            try {
              const parsedLog = arbitrageContract.interface.parseLog(log);
              console.log("Event:", parsedLog.name, parsedLog.args);
            } catch (e) {
              // Ignore logs that don't match the contract's events
            }
          }
        } catch (error) {
          console.error("Error initiating arbitrage:", error.message);
          if (error.transaction) {
            console.error("Failed transaction hash:", error.transactionHash);
          }
          if (error.data) {
            try {
              const decodedError = arbitrageContract.interface.parseError(error.data);
              console.error("Decoded error:", decodedError);
            } catch (e) {
              console.error("Failed to decode error:", e);
            }
          }
        }
      } else {
        console.log("Potential profit below threshold, skipping this opportunity.");
      }
    } catch (error) {
      console.error("Error in profit calculation:", error);
    }
  }

async function main() {
  console.log("Starting arbitrage monitoring...");
  const [deployer] = await ethers.getSigners();
  console.log("Using account:", deployer.address);

  const UniswapV2V3FlashArbitrage = await ethers.getContractFactory("UniswapV2V3FlashArbitrage");
  const arbitrageContract = await UniswapV2V3FlashArbitrage.attach(ARBITRAGE_CONTRACT_ADDRESS);

  async function monitorAndExecuteArbitrage() {
    console.log("Entering arbitrage monitoring loop...");
    while (true) {
      try {
        console.log("Checking for new arbitrage opportunity...");
        const opportunity = await getLatestArbitrageOpportunity();
        if (opportunity) {
          console.log("Opportunity found, checking gas price...");
          if (await isGasPriceAcceptable()) {
            console.log("Gas price is acceptable, executing arbitrage...");
            await executeArbitrage(opportunity, arbitrageContract);
          } else {
            console.log("Gas price is too high, skipping this opportunity.");
          }
        } else {
          console.log("No new arbitrage opportunity found.");
        }
        console.log("Waiting for 5 seconds before next check...");
        await new Promise(resolve => setTimeout(resolve, 5000));
      } catch (error) {
        console.error("Error in arbitrage loop:", error);
        console.log("Waiting for 10 seconds before retrying...");
        await new Promise(resolve => setTimeout(resolve, 10000));
      }
    }
  }

  await monitorAndExecuteArbitrage().catch(console.error);
}

main()
  .then(() => process.exit(0))
  .catch(error => {
    console.error("Unhandled error:", error);
    process.exit(1);
  });