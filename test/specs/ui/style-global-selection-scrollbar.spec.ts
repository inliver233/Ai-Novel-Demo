import { test, expect } from "../../lib/ui-test";

import { bootstrapProject } from "../../lib/bootstrap";

test("ui: global ::selection + scrollbar rules exist (style guard)", async ({ page, request }) => {
  const { projectId } = await bootstrapProject(request);

  await page.goto(`/projects/${projectId}/writing`);
  await expect(page.getByRole("heading", { name: "写作", exact: true })).toBeVisible();

  const rules = await page.evaluate(() => {
    const result = {
      hasSelection: false,
      hasWebkitScrollbar: false,
      hasScrollbarColor: false,
      hasScrollbarWidth: false,
    };

    const walk = (ruleList: CSSRuleList | CSSRule[]) => {
      for (const rule of Array.from(ruleList)) {
        const anyRule = rule as unknown as { selectorText?: string; style?: CSSStyleDeclaration; cssRules?: CSSRuleList };

        const selectorText = String(anyRule.selectorText ?? "");
        if (selectorText.includes("::selection")) result.hasSelection = true;
        if (selectorText.includes("::-webkit-scrollbar")) result.hasWebkitScrollbar = true;

        const style = anyRule.style;
        if (style) {
          if (style.getPropertyValue("scrollbar-color")) result.hasScrollbarColor = true;
          if (style.getPropertyValue("scrollbar-width")) result.hasScrollbarWidth = true;
        }

        if (anyRule.cssRules) walk(anyRule.cssRules);
      }
    };

    for (const sheet of Array.from(document.styleSheets)) {
      let cssRules: CSSRuleList;
      try {
        cssRules = sheet.cssRules;
      } catch {
        continue;
      }
      walk(cssRules);
    }

    return result;
  });

  expect(rules.hasSelection).toBeTruthy();
  expect(rules.hasWebkitScrollbar || rules.hasScrollbarColor || rules.hasScrollbarWidth).toBeTruthy();
});

