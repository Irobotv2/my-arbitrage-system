require("@nomicfoundation/hardhat-toolbox");
require("@tenderly/hardhat-tenderly");
require('dotenv').config();
require("@nomicfoundation/hardhat-ethers");

module.exports = {
  solidity: {
    compilers: [
      {
        version: "0.5.0",
        settings: {
          optimizer: {
            enabled: true,
            runs: 200,
          },
        },
      },
      {
        version: "0.6.0",
        settings: {
          optimizer: {
            enabled: true,
            runs: 200,
          },
        },
      },
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
        version: "0.7.5",
        settings: {
          optimizer: {
            enabled: true,
            runs: 200,
          },
        },
      },
      {
        version: "0.7.6",
        settings: {
          optimizer: {
            enabled: true,
            runs: 200,
          },
        },
      },
      {
        version: "0.6.12",
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
        version: "0.8.19",
        settings: {
          optimizer: {
            enabled: true,
            runs: 200,
          },
        },
      },
      {
        version: "0.8.20",
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
    ganache: {
      url: "http://127.0.0.1:8549",
      chainId: 1337,
      forking: {
        url: "http://localhost:8545",
      },
      accounts: {
        mnemonic: "material snap escape fortune banana wage estate child van scan dial mask",
      },
    },
    sepolia: {
      url: "https://sepolia.infura.io/v3/0640f56f05a942d7a25cfeff50de344d", // Use your Infura project ID
      chainId: 11155111,
      accounts: [process.env.PRIVATE_KEY], // Use your environment variable for private key
    },
    virtual_mainnet: {
      url: "https://virtual.mainnet.rpc.tenderly.co/300a688c-e670-4eaa-a8d0-e55dc49b649c",
      chainId: 1,
      accounts: [process.env.PRIVATE_KEY],
    },
    mainnet: {
      url: "https://mainnet.infura.io/v3/0640f56f05a942d7a25cfeff50de344d",
      chainId: 1,
      accounts: [process.env.PRIVATE_KEY],
    },
  },
  tenderly: {
    project: "irobotv2",
    username: "Irobotv2noip",
  },
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts"
  },
};
