// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.7.0;
pragma experimental ABIEncoderV2;

import {IVault, IFlashLoanRecipient, IERC20} from "@balancer-labs/v2-interfaces/contracts/vault/IVault.sol";

contract FlashLoanBundleExecutor is IFlashLoanRecipient {
    IVault private constant VAULT = IVault(0xBA12222222228d8Ba445958a75a0704d566BF2C8);
    address public owner;
    address public executor;

    constructor(address _executor) {
        owner = msg.sender;
        executor = _executor;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this function");
        _;
    }

    modifier onlyExecutor() {
        require(msg.sender == executor, "Only executor can call this function");
        _;
    }

    function initiateFlashLoanAndBundle(
        IERC20[] memory tokens,
        uint256[] memory amounts,
        address[] memory targets,
        bytes[] memory payloads
    ) external onlyExecutor {
        bytes memory userData = abi.encode(targets, payloads);
        VAULT.flashLoan(this, tokens, amounts, userData);
    }

    function receiveFlashLoan(
        IERC20[] memory tokens,
        uint256[] memory amounts,
        uint256[] memory feeAmounts,
        bytes memory userData
    ) external override {
        require(msg.sender == address(VAULT), "Only Balancer Vault can call this function");

        // Execute bundled transactions
        (address[] memory targets, bytes[] memory payloads) = abi.decode(userData, (address[], bytes[]));
        executeBundledTransactions(targets, payloads);

        // Ensure profitability and repay loan
        for (uint256 i = 0; i < tokens.length; i++) {
            uint256 totalRepayment = amounts[i] + feeAmounts[i];
            require(tokens[i].balanceOf(address(this)) >= totalRepayment, "Insufficient balance for repayment");
            tokens[i].transfer(address(VAULT), totalRepayment);
        }
    }

    function executeBundledTransactions(address[] memory targets, bytes[] memory payloads) internal {
        require(targets.length == payloads.length, "Mismatched targets and payloads length");
        for (uint256 i = 0; i < targets.length; i++) {
            (bool success, ) = targets[i].call(payloads[i]);
            require(success, "Transaction execution failed");
        }
    }

    // Additional utility functions (withdraw, etc.) can be added here
}