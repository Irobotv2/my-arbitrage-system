// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.7.0;

import {IVault} from "@balancer-labs/v2-interfaces/contracts/vault/IVault.sol";
import {IFlashLoanRecipient} from "@balancer-labs/v2-interfaces/contracts/vault/IFlashLoanRecipient.sol";
import {IERC20} from "@balancer-labs/v2-interfaces/contracts/solidity-utils/openzeppelin/IERC20.sol";

contract FlashLoanRecipient is IFlashLoanRecipient {
    IVault private constant vault = IVault(0xBA12222222228d8Ba445958a75a0704d566BF2C8);
    address public owner;

    event FlashLoanInitiated(address[] tokens, uint256[] amounts);
    event FlashLoanCompleted(address[] tokens, uint256[] amounts, uint256[] fees);
    event BalanceCheck(address token, uint256 balance);

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }

    function makeFlashLoan(IERC20[] memory tokens, uint256[] memory amounts, bytes memory /*userData*/) external onlyOwner {
        address[] memory tokenAddresses = new address[](tokens.length);
        for (uint i = 0; i < tokens.length; i++) {
            tokenAddresses[i] = address(tokens[i]);
        }
        emit FlashLoanInitiated(tokenAddresses, amounts);
        vault.flashLoan(this, tokens, amounts, "");
    }

    function receiveFlashLoan(
        IERC20[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory /*userData*/
    ) external override {
        require(msg.sender == address(vault), "Only Balancer Vault can call this function");
        
        // Log the received amounts
        for (uint256 i = 0; i < tokens.length; i++) {
            uint256 balance = tokens[i].balanceOf(address(this));
            emit BalanceCheck(address(tokens[i]), balance);
        }

        // Ensure repayment
        for (uint256 i = 0; i < tokens.length; i++) {
            uint256 totalRepayment = amounts[i] + feeAmounts[i];
            require(tokens[i].balanceOf(address(this)) >= totalRepayment, "Insufficient balance for repayment");
            tokens[i].transfer(address(vault), totalRepayment);
        }

        address[] memory tokenAddresses = new address[](tokens.length);
        for (uint i = 0; i < tokens.length; i++) {
            tokenAddresses[i] = address(tokens[i]);
        }
        emit FlashLoanCompleted(tokenAddresses, amounts, feeAmounts);
    }

    // Allow contract to receive ETH
    receive() external payable {}

    // Function to withdraw any tokens or ETH stuck in the contract
    function withdraw(address token, uint256 amount) external onlyOwner {
        if (token == address(0)) {
            payable(owner).transfer(amount);
        } else {
            IERC20(token).transfer(owner, amount);
        }
    }
}
