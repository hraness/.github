import { runAction } from './index.mjs';

runAction().catch(error => {
  console.error(`npm-visible: ${error.message}`);
  process.exitCode = 1;
});
