import assert from "node:assert/strict";
import test from "node:test";

import { cameFromEklink } from "../src/lib/eklink.ts";

test("cameFromEklink matches the EkLink origin only", () => {
  assert.equal(cameFromEklink("http://localhost:3000/", "http://localhost:3000"), true);
  assert.equal(cameFromEklink("http://localhost:3000/dashboard", "http://localhost:3000/"), true);
  assert.equal(cameFromEklink("http://localhost:5173/login", "http://localhost:3000"), false);
  assert.equal(cameFromEklink("http://localhost:3002/", "http://localhost:3000"), false);
  assert.equal(cameFromEklink("", "http://localhost:3000"), false);
  assert.equal(cameFromEklink("http://localhost:3000/", null), false);
  assert.equal(cameFromEklink("not a url", "http://localhost:3000"), false);
});
