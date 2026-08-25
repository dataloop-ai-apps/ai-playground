// Runs lint-staged programmatically so allowEmpty is always set,
// regardless of how the pre-commit hook invokes this script.
// Fixes: lint-staged v15 does not honour --allow-empty from npm run in the
// pre-commit hook context (pre-commit pkg v1.2.2 + lint-staged v15 mismatch).
import lintStaged from 'lint-staged'
const success = await lintStaged({ allowEmpty: true })
process.exit(success ? 0 : 1)
