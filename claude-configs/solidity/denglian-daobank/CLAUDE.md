# DAO Bank System Implementation Guide

## Project Overview
Implement a DAO-managed bank system with voting tokens for fund management.

## Implementation Order

### Phase 1: VotingToken Contract
Create `contracts/VotingToken.sol`:
- Implement ERC20 with voting capabilities
- Add delegate functionality for vote delegation
- Implement checkpoint system for historical vote tracking
- Include `getCurrentVotes()` and `getPriorVotes()` functions
- Use OpenZeppelin's ERC20Votes or implement custom voting logic

### Phase 2: Bank Contract
Create `contracts/Bank.sol`:
- Simple vault contract with admin-only withdrawal
- Functions: `deposit()`, `withdraw(address,uint256)`, `getBalance()`
- Admin modifier: `onlyAdmin`
- Set admin in constructor
- Emit events for deposits and withdrawals

### Phase 3: Gov Contract
Create `contracts/Gov.sol`:
- Core DAO functionality
- Proposal struct with all necessary fields
- Functions: `propose()`, `castVote()`, `queue()`, `execute()`, `cancel()`
- Implement proposal states: Pending, Active, Canceled, Defeated, Succeeded, Queued, Executed
- Parameters:
  - Voting delay: 1 day
  - Voting period: 3 days
  - Execution delay: 2 days
  - Proposal threshold: 1% of total supply
  - Quorum: 4% of total supply

### Phase 4: Tests
Create test files in `test/`:
- `VotingToken.test.js`: Test token transfers, delegation, voting power
- `Bank.test.js`: Test deposits, admin-only withdrawals
- `Gov.test.js`: Test full proposal lifecycle
- `Integration.test.js`: End-to-end flow testing

### Phase 5: Deployment Scripts
Create `scripts/deploy.js`:
1. Deploy VotingToken
2. Deploy Bank
3. Deploy Gov with VotingToken address
4. Set Gov as Bank admin
5. Distribute initial tokens

## Key Implementation Notes

### Security Requirements
- Use ReentrancyGuard for Bank withdrawal
- Validate all proposal parameters
- Implement proper access controls
- Use latest Solidity version (0.8.x)

### Gas Optimization
- Pack struct variables efficiently
- Use events instead of storage where possible
- Minimize external calls

### Code Structure
```
contracts/
├── VotingToken.sol
├── Bank.sol
├── Gov.sol
└── interfaces/
    ├── IVotingToken.sol
    └── IBank.sol

test/
├── VotingToken.test.js
├── Bank.test.js
├── Gov.test.js
└── Integration.test.js

scripts/
└── deploy.js
```

## Testing Checklist
- [ ] Token transfers and balances work correctly
- [ ] Vote delegation updates voting power
- [ ] Only admin can withdraw from Bank
- [ ] Proposals go through all states correctly
- [ ] Votes are counted accurately
- [ ] Executed proposals call Bank.withdraw successfully
- [ ] Time-based transitions work (voting period, execution delay)
- [ ] Edge cases: double voting, proposal cancellation, insufficient quorum

## Example Proposal Flow
```javascript
// In tests, demonstrate:
// 1. Alice creates proposal to withdraw 10 ETH to Bob
// 2. Token holders vote
// 3. Proposal passes quorum
// 4. After timelock, proposal is executed
// 5. Bob receives 10 ETH from Bank
```

## Dependencies
- OpenZeppelin Contracts (for ERC20, security utilities)
- Hardhat for development environment
- Ethers.js for testing

## Success Criteria
- All tests pass
- Gas costs are reasonable
- No security vulnerabilities in audit tools
- Clean, documented code
- Deployment script works on testnet