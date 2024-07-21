const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Using account:", deployer.address);

  // Address of the deployed FlashLoanRecipient contract
  const flashLoanRecipientAddress = "0xD71F03bC9C99B7437002102BA44E77f82755A6DD";
  
  // Get the contract instance
  const FlashLoanRecipient = await hre.ethers.getContractFactory("FlashLoanRecipient");
  const flashLoanRecipient = FlashLoanRecipient.attach(flashLoanRecipientAddress);

  console.log("FlashLoanRecipient address:", flashLoanRecipientAddress);

  const balancerVaultAddress = "0xBA12222222228d8Ba445958a75a0704d566BF2C8";
  const aaveAddress = "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9"; // AAVE token address on Ethereum mainnet

  // 3700 AAVE (keeping the same amount for this example)
  const borrowAmount = hre.ethers.parseUnits("1012000", 18);

  const tokens = [aaveAddress];
  const amounts = [borrowAmount];
  const userData = "0x"; // This can be left as an empty bytes string

  try {
    console.log("Attempting to execute flash loan for 3700 AAVE...");
    const tx = await flashLoanRecipient.makeFlashLoan(
      tokens,
      amounts,
      userData,
      { gasLimit: 5000000 } // Keeping the increased gas limit
    );
    console.log("Flash loan transaction sent:", tx.hash);
    const receipt = await tx.wait();
    console.log("Flash loan transaction confirmed in block:", receipt.blockNumber);
    console.log("Flash loan executed successfully");
  } catch (error) {
    console.error("Error executing flash loan:", error);
    if (error.reason) {
      console.error("Error reason:", error.reason);
    }
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });