import { test as base, expect, type Locator, type Page } from "@playwright/test";

import { installNetworkEgressGuard } from "./network-guard";

export const test = base.extend({});
export { expect };

export async function waitForWorldbookPageReady(page: Page) {
  await expect(page.getByLabel("worldbook_search", { exact: true })).toBeVisible();
}

export function getWorldbookEntryCards(page: Page): Locator {
  return page.locator("button.panel-interactive");
}

export async function waitForWorldbookEntryCardsLoaded(
  page: Page,
  opts?: { minCount?: number; exactCount?: number },
): Promise<Locator> {
  await waitForWorldbookPageReady(page);
  const cards = getWorldbookEntryCards(page);

  if (opts?.exactCount !== undefined) {
    await expect.poll(() => cards.count()).toBe(opts.exactCount);
    return cards;
  }

  const minCount = opts?.minCount ?? 1;
  if (minCount > 0) {
    await expect.poll(() => cards.count()).toBeGreaterThanOrEqual(minCount);
  }

  return cards;
}

export async function waitForWorldbookBulkSelectedCount(page: Page, count: number) {
  await expect(page.getByText(new RegExp(`已选\\s*${count}\\s*条`))).toBeVisible();
}

test.beforeEach(async ({ context }) => {
  await installNetworkEgressGuard(context);
});
