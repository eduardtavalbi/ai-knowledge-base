const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const baseUrl = process.env.BASE_URL || 'http://localhost:5173';
const apiUrl = process.env.API_URL || 'http://localhost:8000';
const email = process.env.E2E_EMAIL;
const password = process.env.E2E_PASSWORD;
const registerEmail = process.env.E2E_REGISTER_EMAIL;
const documentId = Number(process.env.E2E_DOCUMENT_ID);
const chunkId = Number(process.env.E2E_CHUNK_ID);

async function main() {
  assert.ok(email && password && registerEmail, 'Full-stack E2E credentials are required');
  assert.ok(Number.isInteger(documentId) && documentId > 0, 'A seeded document id is required');
  assert.ok(Number.isInteger(chunkId) && chunkId > 0, 'A seeded chunk id is required');

  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ acceptDownloads: true });
    const page = await context.newPage();
    let mockedAskRequests = 0;

    // Keep authentication, refresh cookies, documents, deletion and export real.
    // Only the external LLM answer is mocked so CI needs no Gemini credential.
    await page.route(`${apiUrl}/documents/ask`, async (route) => {
      const request = route.request();
      if (request.method() !== 'POST') return route.continue();

      const body = request.postDataJSON();
      assert.equal(body.question, 'What does the seeded document say?');
      assert.ok(request.headers().authorization?.startsWith('Bearer '));
      mockedAskRequests += 1;

      return route.fulfill({
        status: 200,
        headers: {
          'Access-Control-Allow-Origin': baseUrl,
          'Access-Control-Allow-Credentials': 'true',
          'Vary': 'Origin',
        },
        contentType: 'application/json',
        body: JSON.stringify({
          answer: 'The full-stack E2E document is available.',
          sources: [{
            document_id: documentId,
            title: 'E2E Seed Document',
            content: 'A seeded full-stack E2E document.',
            score: 0.99,
            chunk_id: chunkId,
            chunk_index: 0,
            source_page: null,
            source_section: 'CI smoke test',
          }],
        }),
      });
    });

    await page.goto(baseUrl);
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Пароль').fill(password);
    await page.getByRole('button', { name: 'Войти' }).click();
    await page.getByRole('button', { name: 'Семантический поиск' }).waitFor();
    await page.getByRole('button', { name: /Моя база знаний/ }).click();
    await page.getByText('E2E Seed Document', { exact: true }).waitFor();

    // The refresh cookie and token must survive a full browser reload.
    await page.reload();
    await page.getByRole('button', { name: 'Семантический поиск' }).waitFor();
    await page.getByRole('button', { name: /Моя база знаний/ }).click();
    await page.getByText('E2E Seed Document', { exact: true }).waitFor();

    await page.getByRole('button', { name: 'Семантический поиск' }).click();
    await page.getByLabel('Поисковый запрос').fill('What does the seeded document say?');
    await page.getByRole('button', { name: 'Найти' }).click();
    await page.getByText('The full-stack E2E document is available.').waitFor();
    assert.equal(mockedAskRequests, 1);

    await page.getByRole('button', { name: /Моя база знаний/ }).click();
    await page.getByRole('button', { name: 'Открыть документ E2E Seed Document' }).click();
    await page.locator('#document-modal-title').waitFor();
    await page.getByText('A seeded full-stack E2E document.', { exact: true }).waitFor();

    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: 'Удалить документ E2E Seed Document' }).click();
    await page.getByText('E2E Seed Document', { exact: true }).waitFor({ state: 'detached' });

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Экспорт данных' }).click();
    const download = await downloadPromise;
    assert.equal(download.suggestedFilename(), 'mindbase-account-export.json');

    await page.getByRole('button', { name: 'Выйти' }).click();
    await page.getByLabel('Email').waitFor();

    // Exercise the real registration UI as a second, separate account.
    await page.getByRole('button', { name: 'Нет аккаунта? Зарегистрироваться' }).click();
    await page.getByLabel('Email').fill(registerEmail);
    await page.getByLabel('Пароль').fill(password);
    await page.getByRole('button', { name: 'Создать аккаунт' }).click();
    await page.getByRole('button', { name: 'Семантический поиск' }).waitFor();
    await page.getByRole('button', { name: /Моя база знаний/ }).click();
    assert.equal(await page.getByText('E2E Seed Document', { exact: true }).count(), 0);

    await page.getByRole('button', { name: 'Выйти' }).click();
    await page.getByLabel('Email').waitFor();

    console.log('Full-stack E2E passed: real FastAPI/PostgreSQL registration, login, refresh, document read/delete and export; only AI answer generation is mocked.');
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
