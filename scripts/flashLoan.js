const hre = require("hardhat");
const { ethers } = require("ethers");

// Address of your newly deployed FlashLoanTest contract
const FLASH_LOAN_TEST_ADDRESS = "0x06D99EEbB099072E755F58736B3C1B34Fdb624fC";

// Uniswap V2 and V3 addresses on mainnet (these won't be used in the actual test, but we'll keep them for completeness)
const UNISWAP_V2_FACTORY = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f";
const UNISWAP_V3_FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984";

// WETH address on mainnet
const WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2";

// Amount to flash loan (1 WETH)
const FLASH_AMOUNT = ethers.parseEther("1");

async function main() {
  // Explicitly create the provider
  const provider = new ethers.JsonRpcProvider("https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c");

  // Create a wallet instance
  const privateKey = process.env.PRIVATE_KEY;
  const wallet = new ethers.Wallet(privateKey, provider);

  console.log("Using account:", await wallet.getAddress());
  console.log("Account balance:", ethers.formatEther(await provider.getBalance(wallet.getAddress())), "ETH");

  const flashLoanTest = new ethers.Contract(
    FLASH_LOAN_TEST_ADDRESS,
    [
      "function testUniswapV2FlashLoan(address factory, address token, uint256 amount) external",
      "function testUniswapV3FlashLoan(address factory, address token, uint256 amount) external",
      "event FlashLoanV2(uint amount0, uint amount1)",
      "event FlashLoanV3(uint256 fee0, uint256 fee1)"
    ],
    wallet
  );

  console.log("FlashLoanTest contract address:", FLASH_LOAN_TEST_ADDRESS);

  console.log("\nTesting Uniswap V2 Flash Loan:");
  try {
    const tx = await flashLoanTest.testUniswapV2FlashLoan(UNISWAP_V2_FACTORY, WETH, FLASH_AMOUNT);
    console.log("Transaction sent:", tx.hash);
    const receipt = await tx.wait();
    console.log("V2 Flash Loan successful. Gas used:", receipt.gasUsed.toString());
    
    // Log the FlashLoanV2 event
    for (const log of receipt.logs) {
      try {
        const parsedLog = flashLoanTest.interface.parseLog(log);
        if (parsedLog.name === 'FlashLoanV2') {
          console.log("FlashLoanV2 event:", parsedLog.args);
        }
      } catch (e) {
        // Ignore logs that don't match our events
      }
    }
  } catch (error) {
    console.error("V2 Flash Loan failed:", error.message);
  }

  console.log("\nTesting Uniswap V3 Flash Loan:");
  try {
    const tx = await flashLoanTest.testUniswapV3FlashLoan(UNISWAP_V3_FACTORY, WETH, FLASH_AMOUNT);
    console.log("Transaction sent:", tx.hash);
    const receipt = await tx.wait();
    console.log("V3 Flash Loan successful. Gas used:", receipt.gasUsed.toString());
    
    // Log the FlashLoanV3 event
    for (const log of receipt.logs) {
      try {
        const parsedLog = flashLoanTest.interface.parseLog(log);
        if (parsedLog.name === 'FlashLoanV3') {
          console.log("FlashLoanV3 event:", parsedLog.args);
        }
      } catch (e) {
        // Ignore logs that don't match our events
      }
    }
  } catch (error) {
    console.error("V3 Flash Loan failed:", error.message);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });