import { test as base, expect } from "@playwright/test";

import { installNetworkEgressGuard } from "./network-guard";

export const test = base.extend({});
export { expect };

test.beforeEach(async ({ context }) => {
  await installNetworkEgressGuard(context);
});

