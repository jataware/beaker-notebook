import { test as base, expect, type Page } from '@playwright/test';

const test = base.extend<{sessionPage: Page}>(
  {
    sessionPage: async ({page}, use) => {
      await page.goto('http://localhost:8888/');
      await expect(page.locator("span.status-label")).toBeVisible();
      await expect(page.locator("span.status-label")).toHaveText("Ready", {timeout: 20_000});
      await use(page);
    }
  }
);

test.describe.configure({ mode: 'parallel' });

test('Agent: Say Hello', async ({ sessionPage }) => {
  await expect(sessionPage.getByPlaceholder("Ask the AI or request an operation.")).toBeVisible();
  await sessionPage.getByPlaceholder("Ask the AI or request an operation.").fill("say hello");
  await sessionPage.getByLabel("Submit").click();
  await expect(sessionPage.getByText("Beaker Agent")).toBeVisible({timeout: 10_000});
  await expect(sessionPage.locator(".agent-cell-content")).toBeVisible();
  await expect(sessionPage.locator(".agent-cell-content")).toContainText("hello", {ignoreCase: true});
});

test('Agent: Run Code', async ({ sessionPage }) => {
  await expect(sessionPage.getByPlaceholder("Ask the AI or request an operation.")).toBeVisible();
  await sessionPage
    .getByPlaceholder("Ask the AI or request an operation.")
    .fill("use the python tool to compute 21 + 115");
  await sessionPage.getByLabel("Submit").click();
  await expect(sessionPage.getByText("Beaker Agent")).toBeVisible({timeout: 10_000});
  await expect(sessionPage.locator(".code-cell")).toBeVisible();
  await expect(sessionPage.locator(".code-cell-output-box")).toContainText(`${21 + 115}`, {timeout: 10_000});
});

test('Code Cell: Execute Python (control+enter)', async ({ sessionPage }) => {
  const codeCell = sessionPage.locator(".beaker-notebook .code-cell .cm-content");
  const testString = "Code Cell Test String"
  await expect(codeCell).toBeVisible();
  await codeCell.click();
  await codeCell.fill(`print("${testString}")`)
  await codeCell.press("Control+Enter")
  // should NOT add new cell
  await expect(sessionPage.locator(".code-cell")).toHaveCount(1);
  await expect(sessionPage.locator(".code-cell-output-box"))
    .toContainText(testString, {timeout: 20_000});
});

test('Code Cell: Execute Python (shift+enter)', async ({ sessionPage }) => {
  const codeCell = sessionPage.locator(".beaker-notebook .code-cell .cm-content");
  const testString = "Code Cell Test String"
  await expect(codeCell).toBeVisible();
  await codeCell.click();
  await codeCell.fill(`print("${testString}")`)
  await codeCell.press("Shift+Enter")
  // should add new cell
  await expect(sessionPage.locator(".code-cell")).toHaveCount(2);
  await expect(sessionPage.locator(".code-cell-output-box"))
    .toContainText(testString, {timeout: 20_000});
});

test('Code Cell: Execute Python (Toolbar Button)', async ({ sessionPage }) => {
  const codeCell = sessionPage.locator(".beaker-notebook .code-cell .cm-content");
  const testString = "Code Cell Test String"
  await expect(codeCell).toBeVisible();
  await codeCell.click();
  await codeCell.fill(`print("${testString}")`)
  await sessionPage.locator(".notebook-toolbar > .p-toolbar-start > button:nth-child(3)").click();
  await expect(sessionPage.locator(".code-cell")).toBeVisible({timeout: 20_000});
  await expect(sessionPage.locator(".code-cell-output-box"))
    .toContainText(testString, {timeout: 20_000});
});

test('File Browser: Show README.md with metadata', async ({ sessionPage }) => {
  const filesTabButton = sessionPage.locator('.sidemenu .left .button-panel > button').nth(1);
  await expect(filesTabButton).toBeVisible();
  await filesTabButton.click();

  const filePanel = sessionPage.locator('.file-container');
  await expect(filePanel).toBeVisible({timeout: 10_000});

  const fileTable = sessionPage.locator('.file-table');
  await expect(fileTable).toBeVisible();

  const readmeRow = fileTable.getByRole('row', { name: /README\.md/ });
  await expect(readmeRow).toBeVisible();

  await expect(readmeRow).toContainText(/\d+\s+(second|minute|hour|day|month|year)s?\s+ago|just now|a (second|minute|hour|day|month|year) ago|last (week|month)/i, {timeout: 5_000});

  await expect(readmeRow).toContainText(/\d+\.?\d*\s?(B|KB|MB|GB)/i);
});
