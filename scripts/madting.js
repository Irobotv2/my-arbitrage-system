const hre = require("hardhat");
const { ethers } = require("ethers");
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

// DynamicFlashLoanArbitrage contract address
const ARBITRAGE_CONTRACT_ADDRESS = "0x781ef60721785a8307f40a2e6863f338a8844698";

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
  const feeData = await provider.getFeeData();
  const gasPrice = feeData.gasPrice;
  const maxGasPrice = ethers.parseUnits("50", "gwei");
  console.log(`Current gas price: ${ethers.formatUnits(gasPrice, "gwei")} gwei`);
  console.log(`Max acceptable gas price: ${ethers.formatUnits(maxGasPrice, "gwei")} gwei`);
  return gasPrice <= maxGasPrice;
}

async function calculatePotentialProfit(opportunity, flashLoanAmount) {
  try {
    const v2Price = ethers.parseUnits(opportunity.v2_price, 18);
    const v3Price = ethers.parseUnits(opportunity.v3_price, 18);

    let profit;
    if (opportunity.direction.startsWith('Buy on V2')) {
      profit = v3Price - v2Price * flashLoanAmount / ethers.parseUnits("1", 18);
    } else {
      profit = v2Price - v3Price * flashLoanAmount / ethers.parseUnits("1", 18);
    }
    return profit;
  } catch (error) {
    console.error("Error calculating potential profit:", error);
    return ethers.parseUnits("0", 18);
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

  const flashLoanAmount = ethers.parseEther("1");
  console.log("Flash loan amount:", ethers.formatEther(flashLoanAmount), "ETH");

  try {
    const potentialProfit = await calculatePotentialProfit(opportunity, flashLoanAmount);
    console.log("Calculated potential profit:", ethers.formatEther(potentialProfit), "ETH");

    const MINIMUM_PROFIT_THRESHOLD_ETH = ethers.parseEther("0.01");

    if (potentialProfit > MINIMUM_PROFIT_THRESHOLD_ETH) {
      console.log("Potential profit exceeds threshold, executing arbitrage...");

      const startBalance = await getWalletBalance(signer, ethers.ZeroAddress);

      const params = {
        tokenIn: opportunity.v2_pair,
        tokenOut: opportunity.v3_pool,
        amount: flashLoanAmount,
        minOutV2: flashLoanAmount * 99n / 100n,
        minOutV3: flashLoanAmount * 99n / 100n,
        v3Fee: 3000
      };

      console.log("Initiating arbitrage with params:", params);

      const tx = await arbitrageContract.initiateArbitrage(
        [ethers.getAddress(opportunity.v2_pair)],
        [flashLoanAmount],
        params
      );

      console.log("Transaction sent:", tx.hash);
      console.log("Waiting for transaction confirmation...");
      const receipt = await tx.wait();
      console.log("Transaction confirmed in block:", receipt.blockNumber);
      console.log("Gas used:", receipt.gasUsed.toString());

      let totalGasCost = receipt.gasUsed * receipt.gasPrice;
      console.log("Total gas cost:", ethers.formatEther(totalGasCost), "ETH");

      const endBalance = await getWalletBalance(signer, ethers.ZeroAddress);
      const profit = endBalance - startBalance + totalGasCost;

      if (profit > 0) {
        console.log("Profitable arbitrage! Logging to database...");
        const connection = await mysql.createConnection(DB_CONFIG);
        await logLegitOpportunity(connection, opportunity, tx.hash, startBalance, endBalance, profit);
        await connection.end();
      }

      for (const log of receipt.logs) {
        try {
          const parsedLog = arbitrageContract.interface.parseLog(log);
          console.log("Event:", parsedLog.name, parsedLog.args);
        } catch (e) {
          // Ignore logs that don't match the contract's events
        }
      }
    } else {
      console.log("Potential profit below threshold, skipping this opportunity.");
    }

    // Mark the opportunity as executed regardless of profit
    await markOpportunityAsExecuted(opportunity.id);
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
  }
}
async function main() {
  console.log("Starting arbitrage monitoring...");
  const provider = new ethers.JsonRpcProvider(RPC_URL);
  const signer = new ethers.Wallet(process.env.PRIVATE_KEY, provider);
  console.log("Using account:", signer.address);

  const DynamicFlashLoanArbitrage = await hre.ethers.getContractFactory("DynamicFlashLoanArbitrage");
  const arbitrageContract = DynamicFlashLoanArbitrage.attach(ARBITRAGE_CONTRACT_ADDRESS).connect(signer);


  async function monitorAndExecuteArbitrage() {
    console.log("Entering arbitrage monitoring loop...");
    while (true) {
      try {
        console.log("Checking for new arbitrage opportunities...");
        const opportunities = await getLatestArbitrageOpportunities(10);  // Fetch up to 10 opportunities
        if (opportunities.length > 0) {
          console.log(`Found ${opportunities.length} opportunities, checking gas price...`);
          if (await isGasPriceAcceptable()) {
            console.log("Gas price is acceptable, executing arbitrage...");
            for (const opportunity of opportunities) {
              await executeArbitrage(opportunity, arbitrageContract, signer);
            }
          } else {
            console.log("Gas price is too high, skipping these opportunities.");
          }
        } else {
          console.log("No new arbitrage opportunities found.");
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
