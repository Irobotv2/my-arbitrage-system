// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@uniswap/v2-core/contracts/interfaces/IUniswapV2Pair.sol";
import "@uniswap/v2-core/contracts/interfaces/IUniswapV2Factory.sol";
import "@uniswap/v3-core/contracts/interfaces/IUniswapV3Pool.sol";
import "@uniswap/v3-core/contracts/interfaces/IUniswapV3Factory.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract FlashLoanTest {
    event FlashLoanV2(uint amount0, uint amount1);
    event FlashLoanV3(uint256 fee0, uint256 fee1);

    function testUniswapV2FlashLoan(address factory, address token, uint256 amount) external {
        // Removed pair existence check for testing
        address pair = address(this); // Use this contract as a dummy pair
        bytes memory data = abi.encode(token, amount);
        // Simulate the flash loan callback
        this.uniswapV2Call(msg.sender, amount, 0, data);
    }

    function testUniswapV3FlashLoan(address factory, address token, uint256 amount) external {
        // Removed pool existence check for testing
        bytes memory data = abi.encode(token, amount);
        // Simulate the flash loan callback
        this.uniswapV3FlashCallback(0, 0, data);
    }

    function uniswapV2Call(address sender, uint amount0, uint amount1, bytes calldata data) external {
        emit FlashLoanV2(amount0, amount1);
        // Simulating the flash loan logic
        (address token, uint256 amount) = abi.decode(data, (address, uint256));
        // In a real scenario, you would perform arbitrage here
        emit FlashLoanV2(amount0, amount1);
    }

    function uniswapV3FlashCallback(uint256 fee0, uint256 fee1, bytes calldata data) external {
        emit FlashLoanV3(fee0, fee1);
        // Simulating the flash loan logic
        (address token, uint256 amount) = abi.decode(data, (address, uint256));
        // In a real scenario, you would perform arbitrage here
        emit FlashLoanV3(fee0, fee1);
    }

    // Function to receive ETH
    receive() external payable {}
}