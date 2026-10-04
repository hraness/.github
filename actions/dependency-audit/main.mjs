import { runAction } from './index.mjs';

runAction().then(result => {
  if (result.failed) process.exitCode = 1;
}).catch(error => {
  console.error(`dependency-audit: ${error.message}`);
  process.exitCode = 1;
});
