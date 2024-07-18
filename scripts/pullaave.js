const hre = require("hardhat");
const { ethers } = hre;

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Using account:", deployer.address);

  const flashLoanArbitrageAddress = "0x781ef60721785a8307f40a2e6863f338a8844698";
  
  const FlashLoanArbitrage = await ethers.getContractFactory("DynamicFlashLoanArbitrage");
  const flashLoanArbitrage = await FlashLoanArbitrage.attach(flashLoanArbitrageAddress);

  const aaveAddress = "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9";
  const wethAddress = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";
  const balancerVaultAddress = "0xBA12222222228d8Ba445958a75a0704d566BF2C8";

  const AAVE = await ethers.getContractAt("@balancer-labs/v2-interfaces/contracts/solidity-utils/openzeppelin/IERC20.sol:IERC20", aaveAddress);

  // Use a smaller amount for testing, e.g., 1 AAVE
  const aaveAmount = ethers.parseUnits("1", 18);
  console.log("AAVE amount for flash loan:", ethers.formatUnits(aaveAmount, 18));

  const tokens = [aaveAddress];
  const amounts = [aaveAmount];

  // Set more realistic minOut values (e.g., 99% of input considering fees)
  const minOut = aaveAmount * 99n / 100n; // Using BigInt operations

  const params = {
    tokenIn: aaveAddress,
    tokenOut: wethAddress,
    amount: aaveAmount,
    minOutV2: minOut,
    minOutV3: minOut,
    v3Fee: 3000 // 0.3% fee tier
  };

  console.log("Initiating flash loan...");
  
  try {
    const tx = await flashLoanArbitrage.initiateArbitrage(tokens, amounts, params, { gasLimit: 10000000n });
    console.log("Transaction sent:", tx.hash);
    const receipt = await tx.wait();
    console.log("Transaction confirmed in block:", receipt.blockNumber);
    
    for (const log of receipt.logs) {
      try {
        const parsedLog = flashLoanArbitrage.interface.parseLog(log);
        console.log("Event:", parsedLog.name, parsedLog.args);
      } catch (e) {
        // Ignore logs that don't match the contract's events
      }
    }
  } catch (error) {
    console.error("Error initiating flash loan:", error);
    if (error.data) {
      console.error("Error data:", error.data);
    }
  }
}

main()
  .then(() => process.exit(0))
  .catch(error => {
    console.error("Unhandled error:", error);
    process.exit(1);
  });