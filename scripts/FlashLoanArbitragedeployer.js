const hre = require("hardhat");

async function main() {
  const FlashLoanArbitrage = await hre.ethers.getContractFactory("FlashLoanArbitrage");
  console.log("Deploying FlashLoanArbitrage...");
  const flashLoanArbitrage = await FlashLoanArbitrage.deploy();
  console.log("FlashLoanArbitrage deployed to:", await flashLoanArbitrage.getAddress());
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });