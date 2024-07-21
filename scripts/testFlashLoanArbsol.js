const hre = require("hardhat");
const { expect } = require("chai");
const { ethers } = require("ethers");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Using account:", deployer.address);

  const flashLoanArbitrageAddress = "0xC2EBE45652906DF9209ca97da3d7C9cc8d0D6B70";
  
  // Get the contract instance
  const FlashLoanArbitrage = await hre.ethers.getContractFactory("FlashLoanArbitrage");
  const flashLoanArbitrage = FlashLoanArbitrage.attach(flashLoanArbitrageAddress);

  console.log("FlashLoanArbitrage address:", flashLoanArbitrageAddress);

  // Test parameters
  const wethAddress = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";
  const daiAddress = "0x6B175474E89094C44Da98b954EedeAC495271d0F";
  const usdcAddress = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48";
  const borrowAmount = ethers.parseUnits("1", 18); // 1 WETH

  // Test executeArbitrage function
  async function testExecuteArbitrage() {
    console.log("Testing executeArbitrage function...");
    const tokens = [wethAddress];
    const amounts = [borrowAmount];
    const path = [wethAddress, daiAddress, usdcAddress, wethAddress];
    const pools = [
      "0xC2e9F25Be6257c210d7Adf0D4Cd6E3E881ba25f8", // WETH/DAI V3 pool
      "0x5777d92f208679DB4b9778590Fa3CAB3aC9e2168", // DAI/USDC V3 pool
      "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640"  // USDC/WETH V3 pool
    ];
    const isV3 = [true, true, true];
    const fees = [3000, 100, 500]; // 0.3%, 0.01%, 0.05% fees

    try {
      // Simulate arbitrage first
      console.log("Simulating arbitrage...");
      const estimatedProfit = await flashLoanArbitrage.simulateArbitrage(tokens, amounts, path, pools, isV3, fees);
      console.log("Estimated profit:", ethers.formatUnits(estimatedProfit, 18), "ETH");

      // Define a minimum profit threshold (e.g., 0.01 ETH)
      const minProfitThreshold = ethers.parseUnits("0.01", 18);

      if (estimatedProfit > minProfitThreshold) {
        console.log("Estimated profit above threshold. Executing arbitrage...");
        const tx = await flashLoanArbitrage.executeArbitrage(tokens, amounts, path, pools, isV3, fees, {
          gasLimit: 5000000
        });
        console.log("Arbitrage transaction sent:", tx.hash);
        
        // Wait for transaction and log events
        const receipt = await tx.wait();
        console.log("Arbitrage transaction confirmed in block:", receipt.blockNumber);
        
        // Log events
        for (const event of receipt.logs) {
          try {
            const decodedEvent = flashLoanArbitrage.interface.parseLog(event);
            console.log("Event:", decodedEvent.name);
            console.log("Event args:", decodedEvent.args);
          } catch (error) {
            console.log("Could not decode log:", event);
          }
        }
        
        console.log("Arbitrage executed successfully");
      } else {
        console.log("Estimated profit too low, skipping arbitrage");
      }
    } catch (error) {
      console.error("Error executing arbitrage:", error);
      if (error.transaction) {
        const tx = error.transaction;
        console.log("Failed transaction details:");
        console.log("From:", tx.from);
        console.log("To:", tx.to);
        console.log("Value:", ethers.formatEther(tx.value), "ETH");
        console.log("Gas price:", ethers.formatUnits(tx.gasPrice, "gwei"), "Gwei");
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
            const decodedLog = flashLoanArbitrage.interface.parseLog(log);
            console.log("Event:", decodedLog.name);
            console.log("Event args:", decodedLog.args);
          } catch (decodeError) {
            console.log("Could not decode log:", log);
          }
        }
      }
    }
  }

  // Test withdraw function
  async function testWithdraw() {
    console.log("Testing withdraw function...");
    const withdrawAmount = ethers.parseUnits("0.1", 18); // 0.1 ETH
    try {
      // Check balance before withdrawal
      const balanceBefore = await ethers.provider.getBalance(flashLoanArbitrageAddress);
      console.log("Contract balance before withdrawal:", ethers.formatEther(balanceBefore), "ETH");

      const tx = await flashLoanArbitrage.withdraw(ethers.ZeroAddress, withdrawAmount);
      console.log("Withdraw transaction sent:", tx.hash);
      const receipt = await tx.wait();
      console.log("Withdraw transaction confirmed in block:", receipt.blockNumber);

      // Check balance after withdrawal
      const balanceAfter = await ethers.provider.getBalance(flashLoanArbitrageAddress);
      console.log("Contract balance after withdrawal:", ethers.formatEther(balanceAfter), "ETH");

      console.log("Withdraw executed successfully");
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
        console.log("Value:", ethers.formatEther(tx.value), "ETH");
        console.log("Gas price:", ethers.formatUnits(tx.gasPrice, "gwei"), "Gwei");
        console.log("Gas limit:", tx.gasLimit.toString());
      }
    }
  }

  // Run tests
  await testExecuteArbitrage();
  await testWithdraw();
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });