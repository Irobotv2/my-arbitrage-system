const hre = require("hardhat");

async function main() {
  const FlashLoanRecipient = await hre.ethers.getContractAt("FlashLoanRecipient", "0x9A01ed07FB959ac5d19fe3A02d3EAb4Fc15e0C82");
  const owner = await FlashLoanRecipient.owner();
  console.log("Contract owner is:", owner);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
