require("@nomicfoundation/hardhat-toolbox");
require("@tenderly/hardhat-tenderly");
require('dotenv').config();

module.exports = {
  solidity: {
    compilers: [
      {
        version: "0.7.0",
        settings: {
          optimizer: {
            enabled: true,
            runs: 200,
          },
        },
      },
      {
        version: "0.8.0",
        settings: {
          optimizer: {
            enabled: true,
            runs: 200,
          },
        },
      },
      {
        version: "0.8.24",
        settings: {
          optimizer: {
            enabled: true,
            runs: 200,
          },
        },
      },
    ],
  },
  networks: {
    virtual_mainnet: {
      url: "https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c",
      chainId: 1,
      accounts: [process.env.PRIVATE_KEY],
    },
  },
  tenderly: {
    project: "irobotv2",
    username: "Irobotv2noip",
  },
};
