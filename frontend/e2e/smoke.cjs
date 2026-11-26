const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const baseUrl = process.env.BASE_URL || 'http://localhost:4173';

async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ acceptDownloads: true });
    const page = await context.newPage();
    let authenticated = false;
    let documents = [
      { id: 1, title: 'Security policy', content: 'MFA is required for administrator accounts.' },
    ];
    const apiRequests = [];

    await page.route(`${baseUrl}/**`, async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const method = request.method();
      const headers = request.headers();
      apiRequests.push({
        path: url.pathname,
        method,
        authorization: headers.authorization || '',
      });

      if (url.pathname === '/health' && method === 'GET') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"ok"}' });
      }

      if (url.pathname === '/auth/refresh' && method === 'POST') {
        if (!authenticated) {
          return route.fulfill({
            status: 401,
            contentType: 'application/json',
            body: '{"detail":"No active session"}',
          });
        }
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ access_token: 'e2e-refreshed-token', token_type: 'bearer' }),
        });
      }

      if (url.pathname === '/auth/login' && method === 'POST') {
        authenticated = true;
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ access_token: 'e2e-access-token', token_type: 'bearer' }),
        });
      }

      if (url.pathname === '/documents/' && method === 'GET') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(documents) });
      }

      if (url.pathname === '/documents/ask' && method === 'POST') {
        const body = request.postDataJSON();
        assert.equal(body.question, 'What is the MFA requirement?');
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            answer: 'MFA is mandatory for all administrators.',
            sources: [{
              document_id: 1,
              title: 'Security policy',
              content: 'MFA is required for administrator accounts.',
              score: 0.94,
              chunk_id: 11,
              chunk_index: 0,
              source_page: 1,
              source_section: 'Access control',
            }],
          }),
        });
      }

      if (url.pathname === '/documents/upload' && method === 'POST') {
        const uploaded = { id: 2, title: 'e2e-notes.txt', content: 'Notes uploaded by the browser smoke test.' };
        documents = [uploaded, ...documents];
        return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(uploaded) });
      }

      if (url.pathname === '/documents/1' && method === 'GET') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(documents.find((item) => item.id === 1)) });
      }

      if (url.pathname === '/documents/1' && method === 'PUT') {
        const body = request.postDataJSON();
        documents = documents.map((item) => item.id === 1 ? { ...item, ...body } : item);
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(documents.find((item) => item.id === 1)) });
      }

      if (url.pathname === '/auth/me/export' && method === 'GET') {
        return route.fulfill({
          status: 200,
          headers: {
            'Content-Type': 'application/json',
            'Content-Disposition': 'attachment; filename="mindbase-account-export.json"',
          },
          body: JSON.stringify({ documents }),
        });
      }

      if (url.pathname === '/auth/logout' && method === 'POST') {
        authenticated = false;
        return route.fulfill({ status: 204 });
      }

      return route.continue();
    });

    await page.goto(baseUrl);
    await page.getByLabel('Email').fill('e2e@example.com');
    await page.getByLabel('Пароль').fill('long-password-for-e2e');
    await page.getByRole('button', { name: 'Войти' }).click();
    await page.getByRole('button', { name: 'Семантический поиск' }).waitFor();
    await page.getByRole('button', { name: /Моя база знаний/ }).click();
    await page.getByText('Security policy', { exact: true }).waitFor();

    assert(apiRequests.some((item) => item.path === '/documents/' && item.authorization === 'Bearer e2e-access-token'));

    // A reload exercises the refresh-cookie path and rehydrates the workspace.
    await page.reload();
    await page.getByRole('button', { name: 'Семантический поиск' }).waitFor();
    await page.getByRole('button', { name: /Моя база знаний/ }).click();
    await page.getByText('Security policy', { exact: true }).waitFor();
    assert(apiRequests.some((item) => item.path === '/documents/' && item.authorization === 'Bearer e2e-refreshed-token'));

    await page.getByRole('button', { name: 'Семантический поиск' }).click();
    await page.getByLabel('Поисковый запрос').fill('What is the MFA requirement?');
    await page.getByRole('button', { name: 'Найти' }).click();
    await page.getByText('MFA is mandatory for all administrators.').waitFor();
    await page.getByText('Security policy').last().waitFor();

    await page.getByRole('button', { name: 'Добавить документ' }).click();
    await page.locator('input[type="file"]').setInputFiles({
      name: 'e2e-notes.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('Notes uploaded by the browser smoke test.'),
    });
    await page.getByText('Документ «e2e-notes.txt» загружен.').waitFor();

    await page.getByRole('button', { name: /Моя база знаний/ }).click();
    await page.getByRole('button', { name: 'Редактировать Security policy' }).click();
    await page.locator('#edit-title').fill('Security policy — updated');
    await page.locator('#edit-content').fill('MFA is mandatory for all administrators and privileged users.');
    await page.getByRole('button', { name: 'Сохранить' }).click();
    await page.getByRole('heading', { name: 'Security policy — updated' }).waitFor();
    await page.getByRole('button', { name: 'Закрыть документ' }).click();
    await page.getByText('Security policy — updated', { exact: true }).waitFor();

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Экспорт данных' }).click();
    const download = await downloadPromise;
    assert.equal(download.suggestedFilename(), 'mindbase-account-export.json');

    await page.getByRole('button', { name: 'Выйти' }).click();
    await page.getByLabel('Email').waitFor();

    console.log('Frontend E2E passed: login, refresh, authenticated document load, hybrid-search UI, upload, edit, export and logout.');
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
