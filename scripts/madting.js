const hre = require("hardhat");
const { ethers } = require("ethers");
const mysql = require('mysql2/promise');
const fs = require('fs');
const path = require('path');

// Database configuration
const DB_CONFIG = {
  host: 'localhost',
  user: 'arbitrage_user',
  password: 'Newpassword1!',
  database: 'arbitrage_system'
};

// Tenderly RPC URL
const RPC_URL = "https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c";

// DynamicFlashLoanArbitrage contract address
const ARBITRAGE_CONTRACT_ADDRESS = "0x781ef60721785a8307f40a2e6863f338a8844698";

// Error logging function
function logError(error) {
  const errorLog = path.join(__dirname, 'error.log');
  const errorMessage = `[${new Date().toISOString()}] ${error.stack || error.message || error}\n`;
  fs.appendFileSync(errorLog, errorMessage);
}

async function getLatestArbitrageOpportunities(limit = 10) {
  const connection = await mysql.createConnection(DB_CONFIG);

  try {
    const [rows] = await connection.query(`
      SELECT * FROM arbitrage_opportunities 
      WHERE executed = 0
      ORDER BY timestamp DESC 
      LIMIT ${limit}
    `);

    if (rows.length > 0) {
      console.log(`Retrieved ${rows.length} arbitrage opportunities`);
      rows.forEach(opportunity => {
        console.log(`  Pair: ${opportunity.pair}`);
        console.log(`  V2 Price: ${opportunity.v2_price}`);
        console.log(`  V3 Price: ${opportunity.v3_price}`);
        console.log(`  Basis Points: ${opportunity.basis_points}`);
        console.log(`  Direction: ${opportunity.direction}`);
        console.log('---');
      });
    } else {
      console.log("No arbitrage opportunities found.");
    }

    return rows;
  } catch (error) {
    console.error("Error fetching arbitrage opportunities:", error);
    logError(error);
    return [];
  } finally {
    await connection.end();
  }
}

async function markOpportunityAsExecuted(opportunityId) {
  const connection = await mysql.createConnection(DB_CONFIG);
  await connection.execute(
    'UPDATE arbitrage_opportunities SET executed = 1, execution_timestamp = NOW() WHERE id = ?',
    [opportunityId]
  );
  await connection.end();
}

async function isGasPriceAcceptable() {
  const provider = new ethers.JsonRpcProvider(RPC_URL);
  try {
    let gasPrice;

    // Try to get feeData first
    const feeData = await provider.getFeeData();
    if (feeData && feeData.gasPrice) {
      gasPrice = feeData.gasPrice;
    } else {
      // Fallback to getGasPrice if feeData.gasPrice is not available
      gasPrice = await provider.getGasPrice();
    }

    const maxGasPrice = ethers.parseUnits("50", "gwei");
    console.log(`Current gas price: ${ethers.formatUnits(gasPrice, "gwei")} gwei`);
    console.log(`Max acceptable gas price: ${ethers.formatUnits(maxGasPrice, "gwei")} gwei`);
    return gasPrice <= maxGasPrice;
  } catch (error) {
    console.error("Error fetching gas price:", error);
    logError(error);
    // Return false if we can't determine the gas price
    return false;
  }
}

async function calculatePotentialProfit(opportunity, flashLoanAmount) {
  try {
    const v2Price = ethers.parseUnits(opportunity.v2_price, 18);
    const v3Price = ethers.parseUnits(opportunity.v3_price, 18);
    const amount = BigInt(flashLoanAmount);

    let profit;
    if (opportunity.direction.startsWith('Buy on V2')) {
      profit = (v3Price * amount * BigInt(1e18)) / v2Price - amount;
    } else {
      profit = (v2Price * amount * BigInt(1e18)) / v3Price - amount;
    }
    return profit;
  } catch (error) {
    console.error("Error calculating potential profit:", error);
    logError(error);
    return BigInt(0);
  }
}
async function getWalletBalance(wallet, tokenAddress) {
  if (tokenAddress === ethers.ZeroAddress) {
    return await wallet.provider.getBalance(wallet.address);
  } else {
    const token = new ethers.Contract(
      tokenAddress,
      ["function balanceOf(address) view returns (uint256)"],
      wallet
    );
    return await token.balanceOf(wallet.address);
  }
}

async function logLegitOpportunity(connection, opportunity, txHash, startBalance, endBalance, profit) {
  const query = `
    INSERT INTO legit_opportunities 
    (pair, v2_pair, v3_pool, v2_price, v3_price, basis_points, direction, 
     transaction_hash, start_balance, end_balance, profit, timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
  `;

  const values = [
    opportunity.pair,
    opportunity.v2_pair,
    opportunity.v3_pool,
    opportunity.v2_price,
    opportunity.v3_price,
    opportunity.basis_points,
    opportunity.direction,
    txHash,
    startBalance.toString(),
    endBalance.toString(),
    profit.toString()
  ];

  await connection.execute(query, values);
  console.log("Logged legitimate opportunity to database.");
}

async function executeArbitrage(opportunity, arbitrageContract, signer) {
  console.log("Executing arbitrage for opportunity:", opportunity);

  const flashLoanAmount = ethers.parseUnits("1", 18);
  console.log("Flash loan amount:", ethers.formatUnits(flashLoanAmount, 18), "ETH");

  try {
    if (!arbitrageContract || typeof arbitrageContract.initiateArbitrage !== 'function') {
      throw new Error("Arbitrage contract is not properly initialized");
    }

    const params = {
      tokenIn: opportunity.v2_pair,
      tokenOut: opportunity.v3_pool,
      amount: flashLoanAmount,
      minOutV2: flashLoanAmount * 99n / 100n,
      minOutV3: flashLoanAmount * 99n / 100n,
      v3Fee: 3000
    };

    const tokens = [ethers.getAddress(opportunity.v2_pair)];
    const amounts = [flashLoanAmount];

    console.log("Arbitrage parameters:", JSON.stringify(params, (_, v) => typeof v === 'bigint' ? v.toString() : v));
    console.log("Tokens:", tokens);
    console.log("Amounts:", amounts.map(a => a.toString()));

    // Check account balance
    const balance = await signer.provider.getBalance(signer.address);
    console.log("Account balance:", ethers.formatEther(balance), "ETH");

    const estimatedGas = await arbitrageContract.estimateGas.initiateArbitrage(tokens, amounts, params);
    console.log("Estimated gas:", estimatedGas.toString());

    const tx = await arbitrageContract.initiateArbitrage(tokens, amounts, params, {
      gasLimit: estimatedGas * 120n / 100n // Add 20% buffer to gas limit
    });
    console.log("Transaction sent:", tx.hash);
    const receipt = await tx.wait();
    console.log("Transaction confirmed in block:", receipt.blockNumber);
    console.log("Gas used:", receipt.gasUsed.toString());

    return true;
  } catch (error) {
    console.error("Error in arbitrage execution:", error);
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
    return false;
  }
}

async function main() {
  console.log("Starting arbitrage monitoring...");
  const provider = new ethers.JsonRpcProvider(RPC_URL);
  const signer = new ethers.Wallet(process.env.PRIVATE_KEY, provider);
  console.log("Using account:", signer.address);

  const DynamicFlashLoanArbitrage = await hre.ethers.getContractFactory("DynamicFlashLoanArbitrage");
  const arbitrageContract = DynamicFlashLoanArbitrage.attach(ARBITRAGE_CONTRACT_ADDRESS).connect(signer);

  while (true) {
    try {
      console.log("Checking for new arbitrage opportunities...");
      const opportunities = await getLatestArbitrageOpportunities(10);
      if (opportunities.length > 0) {
        console.log(`Found ${opportunities.length} opportunities, checking gas price...`);
        if (await isGasPriceAcceptable()) {
          console.log("Gas price is acceptable, evaluating opportunities...");
          for (const opportunity of opportunities) {
            const flashLoanAmount = ethers.parseUnits("1", 18);
            const profit = await calculatePotentialProfit(opportunity, flashLoanAmount);
            const formattedProfit = ethers.formatUnits(profit, 18);
            console.log(`Calculated profit for ${opportunity.pair}: ${formattedProfit} ETH`);
            
            if (profit > ethers.parseUnits("0.01", 18)) {  // Minimum profit threshold
              console.log("Profitable opportunity found. Executing...");
              try {
                const success = await executeArbitrage(opportunity, arbitrageContract, signer);
                if (success) {
                  console.log("Arbitrage execution successful!");
                  await markOpportunityAsExecuted(opportunity.id);
                } else {
                  console.log("Arbitrage execution failed.");
                }
              } catch (error) {
                console.error("Error during arbitrage execution:", error);
                logError(error);
              }
            } else {
              console.log("Opportunity not profitable, skipping execution.");
              await markOpportunityAsExecuted(opportunity.id);
            }
          }
        } else {
          console.log("Gas price is too high, skipping these opportunities.");
          for (const opportunity of opportunities) {
            await markOpportunityAsExecuted(opportunity.id);
          }
        }
      } else {
        console.log("No new arbitrage opportunities found.");
      }
      console.log("Waiting for 5 seconds before next check...");
      await new Promise(resolve => setTimeout(resolve, 5000));
    } catch (error) {
      console.error("Error in arbitrage loop:", error);
      logError(error);
      console.log("Waiting for 10 seconds before retrying...");
      await new Promise(resolve => setTimeout(resolve, 10000));
    }
  }
}
main().then(() => process.exit(0)).catch(error => {
  console.error("Unhandled error:", error);
  logError(error);
  process.exit(1);
});

async function calculatePotentialProfit(opportunity, flashLoanAmount) {
  try {
    const v2Price = ethers.parseUnits(opportunity.v2_price, 18);
    const v3Price = ethers.parseUnits(opportunity.v3_price, 18);
    const amount = BigInt(flashLoanAmount);

    let profit;
    if (opportunity.direction.startsWith('Buy on V2')) {
      profit = (v3Price * amount) / v2Price - amount;
    } else {
      profit = (v2Price * amount) / v3Price - amount;
    }
    return profit;
  } catch (error) {
    console.error("Error calculating potential profit:", error);
    logError(error);
    return BigInt(0);  // Return 0 as BigInt in case of error
  }
}


async function testCalculatePotentialProfit() {
  console.log("Fetching latest arbitrage opportunities from database...");
  const opportunities = await getLatestArbitrageOpportunities(10);

  if (opportunities.length === 0) {
    console.log("No arbitrage opportunities found in the database.");
    return;
  }

  for (const opportunity of opportunities) {
    console.log(`Testing opportunity: ${opportunity.direction}`);
    console.log(`Pair: ${opportunity.pair}`);
    console.log(`V2 Price: ${opportunity.v2_price}, V3 Price: ${opportunity.v3_price}`);
    
    const flashLoanAmount = ethers.parseUnits("1", 18).toString();
    const profit = await calculatePotentialProfit(opportunity, flashLoanAmount);
    const formattedProfit = ethers.formatUnits(profit, 18);
    console.log(`Calculated profit: ${formattedProfit} ETH`);
    
    const calculatedProfitNumber = parseFloat(formattedProfit);
    
    if (calculatedProfitNumber > 0) {
      console.log("Profitable opportunity found. Simulating execution...");
      try {
        const executionSuccess = await simulateArbitrageExecution(opportunity, flashLoanAmount);
        if (executionSuccess) {
          console.log("Arbitrage execution simulation successful!");
        } else {
          console.log("Arbitrage execution simulation failed.");
        }
      } catch (error) {
        console.error("Error during arbitrage execution simulation:", error);
      }
    } else {
      console.log("Opportunity not profitable, skipping execution simulation.");
    }

    console.log("---");  // Separator between opportunities
  }

  console.log("All tests completed.");
}
// Helper function to simulate arbitrage execution
async function simulateArbitrageExecution(opportunity, flashLoanAmount) {
  console.log("Simulating arbitrage execution on Tenderly...");
  const provider = new ethers.JsonRpcProvider(RPC_URL);
  const signer = new ethers.Wallet(process.env.PRIVATE_KEY, provider);
  
  const DynamicFlashLoanArbitrage = await hre.ethers.getContractFactory("DynamicFlashLoanArbitrage");
  const arbitrageContract = DynamicFlashLoanArbitrage.attach(ARBITRAGE_CONTRACT_ADDRESS).connect(signer);

  try {
    const tokenIn = ethers.getAddress(opportunity.v2_pair);
    const tokenOut = ethers.getAddress(opportunity.v3_pool);

    const params = {
      tokenIn: tokenIn,
      tokenOut: tokenOut,
      amount: BigInt(flashLoanAmount),
      minOutV2: BigInt(flashLoanAmount) * 99n / 100n,
      minOutV3: BigInt(flashLoanAmount) * 99n / 100n,
      v3Fee: 3000
    };

    const tokens = [tokenIn];
    const amounts = [BigInt(flashLoanAmount)];

    console.log("Arbitrage parameters:", JSON.stringify(params, (_, v) => typeof v === 'bigint' ? v.toString() : v));
    console.log("Tokens:", tokens);
    console.log("Amounts:", amounts.map(a => a.toString()));

    const tx = await arbitrageContract.initiateArbitrage(tokens, amounts, params, {
      gasLimit: 500000
    });
    console.log("Simulation transaction sent:", tx.hash);
    const receipt = await tx.wait();
    console.log("Simulation transaction confirmed in block:", receipt.blockNumber);
    console.log("Gas used:", receipt.gasUsed.toString());
    return true;
  } catch (error) {
    console.error("Error in arbitrage simulation:", error);
    if (error.reason) console.error("Error reason:", error.reason);
    if (error.data) {
      try {
        const decodedError = arbitrageContract.interface.parseError(error.data);
        console.error("Decoded error:", decodedError);
      } catch (e) {
        console.error("Failed to decode error data");
      }
    }
    return false;
  }
}
// Run the test function
testCalculatePotentialProfit().then(() => {
  console.log("Test script completed.");
  process.exit(0);
}).catch(error => {
  console.error("Unhandled error in test script:", error);
  process.exit(1);
});
