import {expect, test, type Page} from '@playwright/test';


type BrowserFile = {
  name: string;
  type: string;
  bytes: number[];
};

async function dropFiles(page: Page, files: BrowserFile[]) {
  const transfer = await page.evaluateHandle((items) => {
    const dataTransfer = new DataTransfer();
    for (const item of items) {
      dataTransfer.items.add(new File([new Uint8Array(item.bytes)], item.name, {type: item.type}));
    }
    return dataTransfer;
  }, files);
  const composer = page.locator('#agent-input');
  await composer.dispatchEvent('dragenter', {dataTransfer: transfer});
  await expect(composer.getByText('Drop files to attach them to this message')).toBeVisible();
  await composer.dispatchEvent('drop', {dataTransfer: transfer});
}

test('notebook chat attachments upload, remove, extract ZIPs, and send without text', async ({page}) => {
  const baseUrl = process.env.BEAKER_E2E_URL ?? 'http://localhost:8888';
  const sessionId = `attachment-e2e-${Date.now()}`;
  await page.goto(`${baseUrl}/?session=${sessionId}`);
  await expect(page.locator('span.status-label')).toHaveText('Ready', {timeout: 30_000});

  await dropFiles(page, [
    {
      name: 'sales.csv',
      type: 'text/csv',
      bytes: Array.from(new TextEncoder().encode('region,revenue\nwest,42\neast,35\n')),
    },
    {
      name: 'notes.txt',
      type: 'text/plain',
      bytes: Array.from(new TextEncoder().encode('temporary notes')),
    },
  ]);

  const drafts = page.getByTestId('attachment-draft');
  await expect(drafts).toHaveCount(2);
  await expect(drafts.filter({hasText: 'sales.csv'}).locator('.pi-spinner')).toHaveCount(0, {timeout: 15_000});
  await expect(drafts.filter({hasText: 'notes.txt'}).locator('.pi-spinner')).toHaveCount(0, {timeout: 15_000});

  const deleteRequest = page.waitForResponse(
    (response) => response.request().method() === 'DELETE' && response.url().includes('/beaker/attachments/'),
  );
  await drafts.filter({hasText: 'notes.txt'}).getByRole('button', {name: 'Remove notes.txt'}).click();
  expect((await deleteRequest).status()).toBe(204);
  await expect(drafts).toHaveCount(1);
  await expect(drafts).toContainText('sales.csv');

  const zipBytes = Uint8Array.from(atob(
    'UEsDBBQAAAAIANpc7lxygqJGHwAAAB8AAAAOAAAAZGF0YS9zYWxlcy5jc3YrSk3PzM/TKUotS80rTeUqTy0u0TEx4kpNBNLGplwAUEsDBBQAAAAIANpc7lx6D5rSEAAAAA4AAAAKAAAAUkVBRE1FLnR4dCtOzC3ISVVISSxJLE4tAQBQSwECFAMUAAAACADaXO5ccoKiRh8AAAAfAAAADgAAAAAAAAAAAAAAgAEAAAAAZGF0YS9zYWxlcy5jc3ZQSwECFAMUAAAACADaXO5ceg+a0hAAAAAOAAAACgAAAAAAAAAAAAAAgAFLAAAAUkVBRE1FLnR4dFBLBQYAAAAAAgACAHQAAACDAAAAAAA=',
  ), (character) => character.charCodeAt(0));
  await dropFiles(page, [{name: 'dataset.zip', type: 'application/zip', bytes: Array.from(zipBytes)}]);
  await expect(drafts).toHaveCount(2);
  await expect(drafts.filter({hasText: 'dataset.zip'})).toContainText('2 files', {timeout: 15_000});

  await drafts.filter({hasText: 'sales.csv'}).getByRole('button', {name: 'Remove sales.csv'}).click();
  await expect(drafts).toHaveCount(1);
  await expect(drafts).toContainText('dataset.zip');

  await page.getByRole('button', {name: 'Submit'}).click();
  await expect(drafts).toHaveCount(0);
  const queryCell = page.locator('.next-query-cell').last();
  await expect(queryCell).toContainText('dataset.zip');
  await expect(queryCell).toContainText('Please inspect the attached file(s).');

  await expect.poll(async () => {
    const response = await page.request.get(`${baseUrl}/beaker/attachments/${sessionId}`);
    if (!response.ok()) return [];
    const attachments = await response.json();
    return attachments.map((attachment: {name: string; committed: boolean; archive_status?: string}) => ({
      name: attachment.name,
      committed: attachment.committed,
      archiveStatus: attachment.archive_status,
    }));
  }).toEqual([{name: 'dataset.zip', committed: true, archiveStatus: 'extracted'}]);

  const xsrfCookie = (await page.context().cookies()).find((cookie) => cookie.name === '_xsrf');
  expect(xsrfCookie).toBeDefined();
  const clearResponse = await page.request.delete(`${baseUrl}/beaker/attachments/${sessionId}`, {
    headers: {'X-XSRFToken': xsrfCookie!.value},
  });
  expect(clearResponse.status()).toBe(204);
  const remainingResponse = await page.request.get(`${baseUrl}/beaker/attachments/${sessionId}`);
  expect(await remainingResponse.json()).toEqual([]);
});
