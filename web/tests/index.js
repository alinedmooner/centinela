// `node --test tests/` runs this file: since Node 22 a folder given to --test is resolved like a
// module (tests/index.js), not searched for tests. It loads every *.test.mjs of the folder, so a
// new test file needs no change here. `node --test` and `pnpm test` find the files themselves.
import { readdirSync } from 'node:fs';

const folder = new URL('./', import.meta.url);
for (const file of readdirSync(folder).filter((name) => name.endsWith('.test.mjs')).sort()) {
  await import(new URL(file, folder).href);
}
